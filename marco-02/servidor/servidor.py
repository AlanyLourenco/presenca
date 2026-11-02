#!/usr/bin/env python3
"""
Projeto Presenca - Marco 2
SERVIDOR DE PERMANENCIA (consumidor da fronteira aparelho -> servidor)

Recebe heartbeats presenca.heartbeat.v1 do aparelho do estudante (ESP32 no
Wokwi) e:
  1. valida contra o contrato versionado em contrato/v1/
  2. deduplica por eventId (deviceId#bootId#sequence)
  3. detecta repeticao, chegada fora de ordem e salto pela sequencia
  4. localiza o aparelho por trilateracao e testa se o ponto esta no poligono
  5. refaz a permanencia da sessao inteira sobre o log (permanencia.py)
  6. devolve ao aparelho o estado (presenca.estado.v1, retained) e, nos quatro
     momentos previstos, o aviso (presenca.aviso.v1)
  7. torna visivel o silencio: aparelho que parou de mandar heartbeat

Uso:
    pip install -r requirements.txt
    python servidor.py          # MQTT sobre TCP, porta 1883
    python servidor.py --ws     # MQTT sobre WebSocket seguro, porta 8884
                                # (para redes que bloqueiam a 1883)

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
    return "--ws" in sys.argv or cfg.get("transporte") == "websockets"


def descrever_transporte(cfg):
    return "MQTT sobre WebSocket seguro" if usar_websocket(cfg) else "MQTT sobre TCP"


def criar_cliente(cfg, client_id):
    """Cria o cliente MQTT no transporte escolhido.

    TCP na porta 1883 e o padrao. Redes que bloqueiam a 1883 (a da faculdade)
    costumam deixar passar WebSocket com TLS: o mesmo broker aceita MQTT
    embrulhado em WebSocket na porta 8884, caminho /mqtt. So o notebook muda;
    o ESP32 roda na nuvem do Wokwi e continua na 1883. O broker entrega as
    mensagens entre os dois transportes normalmente.
    """
    ws = usar_websocket(cfg)
    transporte = "websockets" if ws else "tcp"
    try:                                    # paho-mqtt 2.x
        cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                              client_id=client_id, transport=transporte)
    except (AttributeError, TypeError):     # paho-mqtt 1.x
        cliente = mqtt.Client(client_id=client_id, transport=transporte)
    if ws:
        cliente.tls_set()                   # wss:// - certificado do broker
        cliente.ws_set_options(path=cfg.get("caminho_ws", "/mqtt"))
        return cliente, cfg.get("porta_ws", 8884)
    return cliente, cfg["porta"]


def carregar_validador():
    caminho = os.path.join(RAIZ, "contrato", "v1", "presenca.heartbeat.v1.schema.json")
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
                             perdidos=0, atrasados=0, invalidos=0)
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
    def __init__(self, cfg):
        self.cfg = cfg
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
        self.trava = threading.Lock()
        self.parar = threading.Event()
        self.log = open(os.path.join(AQUI, "recebidos.log"), "a", encoding="utf-8")

        self.cliente, self.porta = criar_cliente(cfg, cfg.get("client_id", "presenca-servidor"))
        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_message = self._ao_receber

    # -- MQTT ----------------------------------------------------------------
    def _ao_conectar(self, cliente, userdata, flags, rc, properties=None):
        cliente.subscribe(self.cfg["topico_heartbeat"], qos=1)
        print(f"{VERDE}Conectado ao {self.cfg['broker']}, porta {self.porta} "
              f"({'WebSocket seguro' if usar_websocket(self.cfg) else 'MQTT comum'}).{RESET}")
        print(f"{CINZA}Esperando as mensagens do aparelho (o ESP32 no Wokwi).{RESET}")
        self._cabecalho_sessao()

    def _ao_receber(self, cliente, userdata, msg):
        recebido_em = datetime.now(timezone.utc)      # carimbo do servidor
        with self.trava:
            self.ultimo_hb_real = time.time()
            if self.em_silencio:
                self.em_silencio = False
                self._aviso_linha(CIANO, "+ VOLTOU", "as mensagens voltaram a chegar")
            self._processar(msg.payload, recebido_em)

    # -- nucleo --------------------------------------------------------------
    def _validar(self, dado):
        if not isinstance(dado, dict):
            return "payload nao e um objeto JSON"
        if dado.get("eventType") != "presenca.heartbeat.v1":
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

    def _processar(self, payload, recebido_em):
        s = self.sessao
        try:
            dado = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as erro:
            s.contagem["invalidos"] += 1
            self._aviso_linha(VERMELHO, "x INVÁLIDA", "não é um JSON legível; descartada")
            return

        motivo = self._validar(dado)
        if motivo:
            s.contagem["invalidos"] += 1
            self._aviso_linha(VERMELHO, "x INVÁLIDA", f"fora do contrato ({motivo}); descartada")
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
        # JSON compacto: o parser do ESP32 procura "campo":valor sem espaco
        self.cliente.publish(f"{self.cfg['topico_estado']}/{aluno}",
                             json.dumps(msg, separators=(",", ":")), qos=0, retain=True)

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
            self.cliente.publish(f"{self.cfg['topico_aviso']}/{aluno}",
                                 json.dumps(msg, separators=(",", ":")), qos=1)
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
        self.cliente.connect(self.cfg["broker"], self.porta, 60)
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
