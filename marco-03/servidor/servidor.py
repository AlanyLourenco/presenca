#!/usr/bin/env python3
"""
Projeto Presenca - Marco 3 (seguranca)
SERVIDOR DE PERMANENCIA

Recebe heartbeats presenca.heartbeat.v2 do celular do estudante, que mede o
Bluetooth do notebook (a ancora), e:
  0. SEGURANCA (Marco 3): so conversa com o broker por TLS e com usuario e
     senha; abre o envelope assinado e recusa o que nao provar quem mandou
     (assinatura Ed25519, pseudonimo = hash da chave) e que estava ouvindo a
     ancora agora (token HMAC da janela de 12 s)
  1. valida contra o contrato versionado em contrato/v1/
  2. deduplica por eventId (deviceId#bootId#sequence)
  3. detecta repeticao, chegada fora de ordem e salto pela sequencia
  4. localiza o aparelho por trilateracao e testa se o ponto esta no poligono
  5. refaz a permanencia da sessao inteira sobre o log (permanencia.py)
  6. devolve ao aparelho o estado (presenca.estado.v1, retained) e, nos quatro
     momentos previstos, o aviso (presenca.aviso.v1) - os dois ASSINADOS com
     a chave do servidor, que o app confere
  7. torna visivel o silencio: aparelho que parou de mandar heartbeat

Uso:
    pip install -r requirements.txt
    python ../configurar.py     # uma vez: segredos e chave do servidor
    python servidor.py          # MQTT sobre TLS, porta 8883
    python servidor.py --ws     # MQTT sobre WebSocket seguro, porta 8084
                                # (para redes que bloqueiam a 8883)
    python servidor.py --quieto # teste de carga: nao imprime cada mensagem,
                                # so recusas, aparelhos novos e o painel

Durante a execucao:
    p   painel da sessao (ele tambem aparece sozinho a cada `painel_a_cada`
        mensagens recebidas; 0 desliga)
    n   abre uma nova sessao (zera o log)
    q   encerra
"""

import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from permanencia import (
    DENTRO, FIM_DA_AULA, Parametros, Sala, calcular, classificar, texto_aviso,
)
from seguranca import (
    ATRASO_FILA_JANELAS, JANELAS_AO_VIVO, Recusa, abrir_envelope, carregar_segredos,
    chave_do_servidor, envelopar, identidade_da_chave, publica_hex, token_valido,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

VERDE, AMARELO, VERMELHO, CIANO, MAGENTA, CINZA, NEGRITO, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[35m", "\033[90m",
    "\033[1m", "\033[0m",
)
COR_ESTADO = {"PRESENTE": VERDE, "AUSENCIA_TOLERADA": AMARELO, "FORA": VERMELHO}

# O que aparece na tela e para ser lido por quem nao e da area.
MUDANCA = {
    "sinal na sala sustentado": "entrou na sala",
    "sinal fora da sala sustentado": "saiu da sala → começou a usar a tolerância",
    "retornou dentro do orcamento": "voltou a tempo → nada foi descontado",
    "orcamento de ausencia esgotado": "a tolerância acabou → o tempo fora não conta",
    "saiu sem orcamento restante": "saiu, e a tolerância já tinha acabado",
}
ONDE = {"dentro": "na sala", "fora": "fora da sala", "neutro": "incerto"}


def num(x, casas=1):
    """12.3 -> '12,3' (numero em portugues)."""
    return f"{x:.{casas}f}".replace(".", ",")


def carregar_config():
    for nome in ("config.json", "config.exemplo.json"):
        caminho = os.path.join(AQUI, nome)
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                return json.load(f)
    raise SystemExit("Nenhum config.json ou config.exemplo.json encontrado.")


def usar_websocket(cfg):
    """--ws na linha de comando, ou "transporte": "websockets" no config."""
    if "--tls" in sys.argv:
        return False
    return "--ws" in sys.argv or cfg.get("transporte") == "websockets"


def descrever_transporte(cfg):
    return "MQTT sobre WebSocket com TLS" if usar_websocket(cfg) else "MQTT sobre TLS"


def criar_cliente(segredos, papel, client_id, websocket):
    """Cliente MQTT do papel ("servidor", "app") no EMQX Cloud.

    Nao existe caminho sem TLS: o EMQX Cloud so aceita conexao cifrada, e o
    certificado do broker e conferido (tls_set() usa as autoridades do
    sistema). Usuario e senha vem de segredos.json, um por papel.
    Devolve (cliente, porta).
    """
    transporte = "websockets" if websocket else "tcp"
    try:                                    # paho-mqtt 2.x
        cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                              client_id=client_id, transport=transporte)
    except (AttributeError, TypeError):     # paho-mqtt 1.x
        cliente = mqtt.Client(client_id=client_id, transport=transporte)
    cliente.tls_set()
    cred = segredos[papel]
    cliente.username_pw_set(cred["usuario"], cred["senha"])
    if websocket:
        cliente.ws_set_options(path=segredos.get("caminho_ws", "/mqtt"))
        return cliente, segredos.get("porta_wss", 8084)
    return cliente, segredos.get("porta_tls", 8883)


def carregar_validador():
    caminho = os.path.join(RAIZ, "contrato", "v1", "presenca.heartbeat.v2.schema.json")
    with open(caminho, encoding="utf-8") as f:
        schema = json.load(f)
    if Draft202012Validator is None:
        print(f"{AMARELO}jsonschema ausente: validacao reduzida. pip install jsonschema{RESET}")
        return schema, None
    return schema, Draft202012Validator(schema)


# ---------------------------------------------------------------------------
class Sessao:
    """A aula de UM aluno. O log e a unica fonte de verdade; todo o resto e derivado."""

    def __init__(self, aluno=None):
        self.id = "s" + secrets.token_hex(2)
        self.aluno = aluno            # pseudonimo; None ate o primeiro heartbeat
        self.log = []                 # heartbeats aceitos: dicts com t e classe
        self.vistos = set()           # eventIds ja processados
        self.maior_seq = {}           # bootId -> maior sequencia vista
        self.lacunas = {}             # bootId -> sequencias que faltam
        self.deslocamento = {}        # bootId -> segundos somados a eventTimeMs
        self.inicio = None
        self.avisos_enviados = set()
        self.encerrada = False
        self.contagem = dict(aceitos=0, duplicados=0, fora_de_ordem=0, saltos=0,
                             perdidos=0, atrasados=0, invalidos=0, recusados=0)
        self.ingenuo_s = 0.0          # contador "ao vivo", sem dedup - so para comparar
        self.ultimo_resultado = None

    def linha_do_tempo(self, boot, event_time_ms):
        """Posicao do heartbeat na linha do tempo da sessao, em segundos.

        O relogio do aparelho nao e absoluto e recomeca a cada boot. Ele e
        usado so como DIFERENCA dentro de um mesmo boot. Um boot novo e
        encaixado logo depois do ultimo instante conhecido.
        """
        t_local = event_time_ms / 1000.0
        if boot not in self.deslocamento:
            if not self.log:
                self.deslocamento[boot] = 0.0
            else:
                ultimo = max(e["t"] for e in self.log)
                self.deslocamento[boot] = ultimo + 0.5 - t_local
        return t_local + self.deslocamento[boot]


class Servidor:
    def __init__(self, cfg, segredos=None, chave=None):
        self.cfg = cfg
        self.quieto = "--quieto" in sys.argv
        if segredos is None:
            segredos = carregar_segredos(os.path.join(RAIZ, "segredos.json"))
        self.segredos = segredos
        self.chave = chave or chave_do_servidor(os.path.join(AQUI, "chave-servidor.pem"))
        self.chaves_vistas = {}       # aluno -> chave publica (so para a tela)
        self.recusas = {}             # motivo -> quantas
        self.p = Parametros.de_config(cfg)
        self.sala = Sala.de_config(cfg)
        self.schema, self.validador = carregar_validador()
        # Uma sessao por aluno: o ESP32 e os celulares podem falar ao mesmo
        # tempo sem misturar os logs. `sessao` e a do ultimo heartbeat aceito.
        self.sessoes = {}
        self.sessao = Sessao()
        self.seq_estado = 0
        self.ultimo_hb_real = None
        self.em_silencio = False
        self.painel_a_cada = cfg.get("painel_a_cada", 24)   # mensagens; 0 = so com a tecla p
        if self.quieto:
            self.painel_a_cada = 0
        self.trava = threading.Lock()
        self.parar = threading.Event()
        self.log = open(os.path.join(AQUI, "recebidos.log"), "a", encoding="utf-8")

        self.cliente, self.porta = criar_cliente(
            segredos, "servidor", cfg.get("client_id", "presenca-servidor"), usar_websocket(cfg))
        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_message = self._ao_receber

    # -- MQTT ----------------------------------------------------------------
    def _ao_conectar(self, cliente, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"{VERMELHO}{NEGRITO}O broker RECUSOU a conexão: {rc}. "
                  f"Confira usuário e senha em segredos.json.{RESET}")
            return
        cliente.subscribe(self.cfg["topico_heartbeat"], qos=1)
        print(f"{VERDE}Conectado ao {self.segredos['broker']}, porta {self.porta} "
              f"({descrever_transporte(self.cfg)}, usuário {self.segredos['servidor']['usuario']}).{RESET}")
        print(f"{CINZA}Chave pública do servidor (o app confere o estado e os avisos com ela):\n"
              f"  {publica_hex(self.chave)}{RESET}")
        print(f"{CINZA}Esperando as mensagens do celular do estudante.{RESET}")
        self._cabecalho_sessao()

    def _ao_receber(self, cliente, userdata, msg):
        recebido_em = datetime.now(timezone.utc)      # carimbo do servidor
        with self.trava:
            self.ultimo_hb_real = time.time()
            if self.em_silencio:
                self.em_silencio = False
                self._aviso_linha(CIANO, "+ VOLTOU", "as mensagens voltaram a chegar")
            self._processar(msg.payload, recebido_em, msg.topic)

    # -- nucleo --------------------------------------------------------------
    def _validar(self, dado):
        if not isinstance(dado, dict):
            return "payload nao e um objeto JSON"
        if dado.get("eventType") != "presenca.heartbeat.v2":
            return f"eventType inesperado: {dado.get('eventType')!r}"
        if self.validador is not None:
            erros = sorted(self.validador.iter_errors(dado), key=lambda e: list(e.path))
            if erros:
                campo = ".".join(str(x) for x in erros[0].path) or "(raiz)"
                return f"{campo}: {erros[0].message}"
        else:
            faltando = [c for c in self.schema["required"] if c not in dado]
            if faltando:
                return f"campos ausentes: {faltando}"
        return None

    # -- seguranca -----------------------------------------------------------
    def _conferir(self, topico, payload):
        """Abre o envelope e confere quem mandou e se ouviu a ancora agora.

        Devolve o heartbeat (dict) ou levanta Recusa. A ordem importa: primeiro
        a assinatura (quem e), depois o contrato, depois o token (onde estava).
        """
        try:
            texto = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise Recusa("não é texto")
        de, chave, dado = abrir_envelope(topico or self.cfg["topico_heartbeat"], texto)

        motivo = self._validar(dado)
        if motivo:
            raise Recusa("FORA DO CONTRATO", motivo)

        aluno, device = identidade_da_chave(chave)
        if dado["aluno"] != aluno or dado["deviceId"] != device or de != aluno:
            raise Recusa("IDENTIDADE TROCADA",
                         f"assinou com a chave de {aluno}, mas diz ser {dado['aluno']}")

        atras = ATRASO_FILA_JANELAS if dado.get("bufferizado") else JANELAS_AO_VIVO
        for a in dado["ancoras"]:
            if a["rssi"] is None:
                continue                       # nao ouviu: nao ha o que provar
            segredo = self.segredos.get("ancoras", {}).get(a["id"])
            if segredo is None:
                raise Recusa("ÂNCORA DESCONHECIDA", f"{a['id']} não é desta sala")
            if not token_valido(segredo, a["id"], a.get("token"), atras=atras):
                raise Recusa("TOKEN VENCIDO",
                             f"o token {a.get('token')} não é o que a {a['id']} anuncia agora "
                             f"(heartbeat inventado ou requentado)")

        if aluno not in self.chaves_vistas:
            self.chaves_vistas[aluno] = chave
            self._aviso_linha(CIANO, "+ APARELHO", f"{aluno} se identificou (chave {chave[:16]}…)")
        return dado

    def _recusar(self, recusa):
        self.sessao.contagem["recusados"] += 1
        self.recusas[recusa.motivo] = self.recusas.get(recusa.motivo, 0) + 1
        detalhe = f" — {recusa.detalhe}" if recusa.detalhe else ""
        self._aviso_linha(VERMELHO, "x RECUSADA", f"{recusa.motivo}{detalhe}")

    def _processar(self, payload, recebido_em, topico=None):
        try:
            dado = self._conferir(topico, payload)
        except Recusa as r:
            self._recusar(r)
            return

        eid, seq, boot = dado["eventId"], dado["sequence"], dado["bootId"]
        s = self._sessao_do_aluno(dado["aluno"], boot)

        # contador ingenuo: soma 0,5 s a cada heartbeat "dentro", do jeito que
        # chegar, sem deduplicar e sem ordenar. Existe so para comparacao.
        classe_ingenua, _ = classificar(dado, self.sala)
        if classe_ingenua == DENTRO:
            s.ingenuo_s += 0.5

        if s.encerrada:
            return

        # 1. DUPLICATA - mesma identidade ja processada
        if eid in s.vistos:
            s.contagem["duplicados"] += 1
            self._aviso_linha(AMARELO, "! REPETIDA", f"a nº {seq} já tinha chegado; ignorada")
            self._gravar(dado, recebido_em, "duplicado", None)
            return

        maior = s.maior_seq.get(boot, 0)
        lacunas = s.lacunas.setdefault(boot, set())
        classificacao = "aceito"

        # 2. FORA DE ORDEM - aceito e inserido na posicao certa da linha do tempo
        if seq < maior:
            s.contagem["fora_de_ordem"] += 1
            classificacao = "fora-de-ordem"
            extra = ""
            if seq in lacunas:
                # o salto anterior contou este como perdido; nao estava,
                # so chegou atrasado
                lacunas.discard(seq)
                s.contagem["perdidos"] -= 1
                extra = " (não estava perdida)"
            self._aviso_linha(AMARELO, "! FORA DE ORDEM",
                              f"a nº {seq} chegou depois da nº {maior}; "
                              f"posta no lugar certo{extra}")

        # 3. SALTO - lacuna na sequencia
        elif maior and seq > maior + 1:
            faltam = seq - maior - 1
            lacunas.update(range(maior + 1, seq))
            s.contagem["saltos"] += 1
            s.contagem["perdidos"] += faltam
            self._aviso_linha(VERMELHO, "! SALTO",
                              f"esperava a nº {maior + 1}, veio a nº {seq}: "
                              f"{faltam} perdida(s)")

        if dado.get("bufferizado"):
            s.contagem["atrasados"] += 1
            classificacao = "atrasado"
            self._aviso_linha(CIANO, "~ ATRASADA",
                              f"a nº {seq} ficou guardada sem rede; entrou no passado")

        s.vistos.add(eid)
        s.maior_seq[boot] = max(maior, seq)
        s.contagem["aceitos"] += 1

        t = s.linha_do_tempo(boot, dado["eventTimeMs"])
        if s.inicio is None:
            s.inicio = t
        classe, pos = classificar(dado, self.sala)
        s.log.append({"t": t, "classe": classe})

        r = calcular([(e["t"], e["classe"]) for e in s.log], self.p, inicio=s.inicio)
        mudou = s.ultimo_resultado is None or r.estado != s.ultimo_resultado.estado
        s.ultimo_resultado = r

        dentro_pol = None if pos is None else self.sala.contem(pos)
        self._mostrar(dado, t - s.inicio, classe, pos, r, mudou)
        self._publicar_estado(dado["aluno"], r, classe, pos, dentro_pol)
        self._publicar_avisos(dado["aluno"], r)
        self._gravar(dado, recebido_em, classificacao,
                     {"t": round(t - s.inicio, 3), "classe": classe,
                      "posicao": None if pos is None else [round(pos[0], 2), round(pos[1], 2)],
                      "estado": r.estado})

        if r.encerrada and not s.encerrada:
            s.encerrada = True
            self.painel(final=True)
        elif self.painel_a_cada and s.contagem["aceitos"] % self.painel_a_cada == 0:
            self.painel()

    def _sessao_do_aluno(self, aluno, boot):
        """A sessao deste aluno. Abre uma nova quando a dele ja terminou e chega
        um boot novo: e o aparelho comecando a aula seguinte. Um boot novo no
        meio da aula (reinicio) continua a mesma sessao."""
        s = self.sessoes.get(aluno)
        if s is None and self.sessao.aluno is None and not self.sessao.log:
            s = self.sessao                      # a sessao aberta ao conectar
            s.aluno = aluno
        elif s is None or (s.encerrada and boot not in s.deslocamento):
            s = Sessao(aluno)
            self.sessao = s
            self._cabecalho_sessao()
        self.sessoes[aluno] = s
        self.sessao = s
        return s

    # -- retorno ao aparelho -------------------------------------------------
    def _publicar_estado(self, aluno, r, classe, pos, dentro_pol):
        self.seq_estado += 1
        msg = {
            "eventType": "presenca.estado.v1",
            "estadoId": f"srv-204#{self.seq_estado}",
            "aluno": aluno,
            "entityId": self.cfg.get("entity_id", "sala-204"),
            "estado": r.estado,
            "acumuladoS": round(r.acumulado_s, 1),
            "provisorioS": round(r.provisorio_s, 1),
            "percentual": round(min(100.0, r.percentual(self.p)), 1),
            "orcamentoRestanteS": round(r.orcamento_restante_s, 1),
            "tempoAulaS": round(r.agora, 1),
            "classe": classe,
            "posicao": None if pos is None else [round(pos[0], 1), round(pos[1], 1)],
            "dentroPoligono": dentro_pol,
            "encerrada": r.encerrada,
            "emitidoEmMs": int(time.time() * 1000),
        }
        topico = f"{self.cfg['topico_estado']}/{aluno}"
        self.cliente.publish(topico, envelopar(self.chave, "servidor", topico, msg), qos=0, retain=True)

    def _publicar_avisos(self, aluno, r):
        s = self.sessao
        for aviso in r.avisos:
            if aviso.tipo in s.avisos_enviados:
                continue
            s.avisos_enviados.add(aviso.tipo)
            texto = texto_aviso(aviso, r, self.p)
            msg = {
                "eventType": "presenca.aviso.v1",
                "avisoId": f"{s.id}#{aviso.tipo}",
                "aluno": aluno,
                "tipo": aviso.tipo,
                "texto": texto,
                "percentual": round(min(100.0, r.percentual(self.p)), 1),
                "emitidoEmMs": int(time.time() * 1000),
            }
            topico = f"{self.cfg['topico_aviso']}/{aluno}"
            self.cliente.publish(topico, envelopar(self.chave, "servidor", topico, msg), qos=1)
            cor = VERMELHO if aviso.tipo != FIM_DA_AULA else CIANO
            print(f"\n{cor}{NEGRITO}  ┌─ AVISO ENVIADO AO ESTUDANTE, aos {num(aviso.em)} s ─────────")
            print(f"  │ {texto}")
            print(f"  └──────────────────────────────────────────────────{RESET}\n")

    # -- silencio ------------------------------------------------------------
    def _vigiar_silencio(self):
        limite = self.cfg.get("silencio_s", 6)
        while not self.parar.wait(1):
            with self.trava:
                if (self.ultimo_hb_real and not self.em_silencio
                        and not self.sessao.encerrada
                        and time.time() - self.ultimo_hb_real > limite):
                    self.em_silencio = True
                    self._aviso_linha(MAGENTA, "… SILÊNCIO",
                                      f"nada chega há {limite} s (rede, bateria ou app); "
                                      f"nada é decidido sem mensagem")

    # -- saida ---------------------------------------------------------------
    def _aviso_linha(self, cor, rotulo, texto):
        print(f"  {cor}{rotulo:<15}{RESET} {texto}")

    def _mostrar(self, dado, t, classe, pos, r, mudou):
        if self.quieto:
            return
        onde = ONDE.get(classe, classe)
        if dado.get("state") == "FORA_ALCANCE" and all(a["rssi"] is None for a in dado["ancoras"]):
            onde = "sem sinal"
        if r.estado == "AUSENCIA_TOLERADA":
            situacao = f"SAIU - restam {num(r.orcamento_restante_s)} s"
        elif r.estado == "FORA":
            situacao = "FORA - não conta"
        else:
            situacao = r.estado
        cor = COR_ESTADO.get(r.estado, RESET)
        if len(self.sessoes) > 1:
            print(f"{CINZA}{self.sessao.aluno}{RESET}", end=" ")
        print(f"{CINZA}{num(t) + ' s':>8}  {'nº ' + str(dado['sequence']):<10}{RESET}{onde:<14}"
              f"{cor}{situacao:<24}{RESET}{num(r.acumulado_s)} s")
        if mudou and r.transicoes:
            tt, de, para, porque = r.transicoes[-1]
            print(f"{cor}{NEGRITO}  >>> {num(tt)} s: {MUDANCA.get(porque, porque)}{RESET}")

    def _gravar(self, dado, recebido_em, classificacao, derivado):
        self.log.write(json.dumps({
            "recebidoEm": recebido_em.isoformat(),     # carimbo do servidor
            "sessao": self.sessao.id,
            "classificacao": classificacao,
            "derivado": derivado,
            "evento": dado,
        }, ensure_ascii=False) + "\n")
        self.log.flush()

    def _cabecalho_sessao(self):
        p = self.p
        quem = f" · aluno {self.sessao.aluno}" if self.sessao.aluno else ""
        print(f"\n{CIANO}{NEGRITO}── AULA {self.sessao.id}{quem} COMEÇOU ──────────────────────────────{RESET}")
        print(f"{CINZA}  dura {num(p.duracao_aula, 0)} s · pode sair por até {num(p.orcamento, 0)} s no total · "
              f"avisos aos {num(p.aviso_1, 0)} s e {num(p.aviso_2, 0)} s fora")
        print(f"  (na demonstração, 1 s = {num(p.escala, 0)} s de uma aula de verdade)")
        print(f"\n{'tempo':>8}  {'mensagem':<10}{'onde':<14}{'situação':<24}tempo que contou{RESET}")

    def painel(self, final=False):
        s, r = self.sessao, self.sessao.ultimo_resultado
        c = s.contagem
        p = self.p
        titulo = "RESULTADO FINAL DA AULA" if final else "RESUMO DA AULA"
        quem = f" · {s.aluno}" if s.aluno else ""
        print(f"\n{CIANO}{NEGRITO}  ══ {titulo} {s.id}{quem} ══════════════════════════{RESET}{CIANO}")
        if r:
            situacao = {"PRESENTE": "PRESENTE", "AUSENCIA_TOLERADA": "FORA, ainda na tolerância",
                        "FORA": "FORA, sem contar"}.get(r.estado, r.estado)
            print(f"  Situação:          {situacao}")
            print(f"  Tempo de aula:     {num(r.agora)} s de {num(p.duracao_aula, 0)} s")
            print(f"  Tempo que contou:  {num(r.acumulado_s)} s  = {num(r.percentual(p), 0)} % da aula")
            print(f"     dentro da sala: {num(r.presenca_s)} s")
            print(f"     saídas perdoadas: {num(r.ausencia_creditada_s)} s")
            if r.provisorio_s > 0.05:
                print(f"     ainda em aberto: {num(r.provisorio_s)} s (pode entrar ou sair da conta)")
            print(f"  Tolerância usada:  {num(r.ausencia_usada_s)} s de {num(p.orcamento, 0)} s")
            if final:
                ok = r.acumulado_s >= p.presenca_minima * p.duracao_aula
                print(f"  {NEGRITO}Resultado:         {'APROVADO' if ok else 'REPROVADO'} nesta aula "
                      f"(precisa de {num(p.presenca_minima * 100, 0)} %){RESET}{CIANO}")
            if r.transicoes:
                print("  O que aconteceu:")
                for tt, de, para, porque in r.transicoes:
                    print(f"     {num(tt):>5} s  {MUDANCA.get(porque, porque)}")
        print(f"  Mensagens:  recebidas: {c['aceitos']} · repetidas: {c['duplicados']} · "
              f"fora de ordem: {c['fora_de_ordem']}")
        print(f"              perdidas: {c['perdidos']} · atrasadas: {c['atrasados']} · "
              f"inválidas: {c['invalidos']}")
        print(f"  Segurança:  recusadas nesta aula: {c['recusados']}"
              + (" · desde que ligou: " + ", ".join(f"{m} {n}" for m, n in self.recusas.items())
                 if self.recusas else ""))
        if r:
            print(f"  Um contador simples, sem estas regras, teria somado {num(s.ingenuo_s)} s.")
        print(f"  ══════════════════════════════════════════════════{RESET}\n")

    # -- terminal ------------------------------------------------------------
    def _laco_teclado(self):
        for linha in sys.stdin:
            t = linha.strip().lower()
            if t == "q":
                self.parar.set()
                break
            with self.trava:
                if t == "p":
                    self.painel()
                elif t == "n":
                    self.sessoes = {}
                    self.sessao = Sessao()
                    self._cabecalho_sessao()
                elif t:
                    print(f"{CINZA}Teclas: n = aula nova · p = resumo · q = sair (sempre com Enter){RESET}")

    def executar(self):
        print(f"\n{CIANO}{NEGRITO}══ Presença · servidor de permanência ══{RESET}")
        print(f"{CINZA}Teclas: n = aula nova · p = resumo · q = sair (sempre com Enter){RESET}")
        self.cliente.connect(self.segredos["broker"], self.porta, 60)
        self.cliente.loop_start()
        threading.Thread(target=self._laco_teclado, daemon=True).start()
        threading.Thread(target=self._vigiar_silencio, daemon=True).start()
        try:
            intervalo = self.cfg.get("intervalo_painel_s", 0)   # 0 = so com a tecla p
            while not self.parar.wait(intervalo if intervalo > 0 else 3600):
                if intervalo > 0:
                    with self.trava:
                        if self.sessao.log and not self.sessao.encerrada:
                            self.painel()
        except KeyboardInterrupt:
            pass
        finally:
            self.parar.set()
            self.cliente.loop_stop()
            self.cliente.disconnect()
            self.painel()
            self.log.close()


if __name__ == "__main__":
    Servidor(carregar_config()).executar()
