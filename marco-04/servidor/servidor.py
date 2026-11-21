#!/usr/bin/env python3
"""
Projeto Presenca - Marco 4 (fluxo completo, persistencia e recuperacao)
SERVIDOR DE PERMANENCIA

Recebe do celular do estudante, por MQTT sobre TLS, tudo assinado (Ed25519):
  - heartbeat (presenca.heartbeat.v3, a cada 5 s): RSSI das ancoras + token
  - sensor    (presenca.sensor.v1): acelerometro e bateria do celular
  - cadastro  (presenca.cadastro.v1): nome e matricula, uma vez por turma
  - confirmacao do atuador (presenca.comando.ack.v1)
e:
  0. SEGURANCA (Marco 3): abre o envelope, confere quem mandou e o token
  1. valida contra o contrato versionado em contrato/v1/
  2. deduplica, detecta repeticao, fora de ordem e salto
  3. decide dentro/fora e refaz a permanencia da sessao sobre o log
  4. devolve ao celular o estado e os avisos, assinados
  5. PERSISTE (Marco 4) tudo no PostgreSQL/TimescaleDB (banco.py); com o
     banco fora, guarda numa fila e grava quando ele voltar
  6. RECUPERA (Marco 4) a aula em andamento quando reinicia: rele os eventos
     da sessao aberta e refaz o estado - o acumulador e derivado do log
  7. ATUA (Marco 4): manda comandos ao celular (vibrar, chamar, lanterna) e
     registra a confirmacao
  8. publica o RELATORIO da turma para o app do professor e serve a API HTTP
  9. torna visivel o silencio de cada aparelho (com o motivo provavel, pela
     bateria) e a ancora que parou de ser ouvida por todos

Uso:
    docker compose up -d banco  # uma vez (na pasta marco-04)
    python servidor.py          # MQTT sobre WebSocket com TLS (porta 8084)
    python servidor.py --tls    # MQTT sobre TLS (porta 8883)
    python servidor.py --sem-banco   # sem PostgreSQL: guarda em memoria
    python servidor.py --quieto      # teste de carga

Durante a execucao (sempre com Enter):
    p                       resumo da aula
    r                       relatorio de cada turma
    c <aluno|todos> <tipo> [texto]   ATUADOR: tipo = vibrar, chamar ou lanterna
    b                       banco: fila, tamanho e compressao
    n                       aula nova (esquece as sessoes abertas)
    q                       encerra
"""

import json
import os
import secrets
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

import relatorio
from banco import abrir_banco
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

MUDANCA = {
    "sinal na sala sustentado": "entrou na sala",
    "sinal fora da sala sustentado": "saiu da sala → começou a usar a tolerância",
    "retornou dentro do orcamento": "voltou a tempo → nada foi descontado",
    "orcamento de ausencia esgotado": "a tolerância acabou → o tempo fora não conta",
    "saiu sem orcamento restante": "saiu, e a tolerância já tinha acabado",
}
ONDE = {"dentro": "na sala", "fora": "fora da sala", "neutro": "incerto"}
HEARTBEATS = ("presenca.heartbeat.v2", "presenca.heartbeat.v3")
TIPOS_COMANDO = ("vibrar", "chamar", "lanterna")
TEXTO_COMANDO = {
    "vibrar": "O professor pediu sua atenção.",
    "chamar": "Chamada: toque em \"Estou aqui\".",
    "lanterna": "Mostre que está na sala: a lanterna do celular vai piscar.",
}


def num(x, casas=1):
    """12.3 -> '12,3' (numero em portugues)."""
    return f"{x:.{casas}f}".replace(".", ",")


def carregar_config():
    for nome in ("config.json", "config.exemplo.json"):
        caminho = os.path.join(AQUI, nome)
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                cfg = json.load(f)
            if os.environ.get("PRESENCA_DSN"):
                cfg.setdefault("banco", {})["dsn"] = os.environ["PRESENCA_DSN"]
            return cfg
    raise SystemExit("Nenhum config.json ou config.exemplo.json encontrado.")


def usar_websocket(cfg):
    """--ws na linha de comando, ou "transporte": "websockets" no config."""
    if "--tls" in sys.argv:
        return False
    return "--ws" in sys.argv or cfg.get("transporte") == "websockets"


def descrever_transporte(cfg):
    return "MQTT sobre WebSocket com TLS" if usar_websocket(cfg) else "MQTT sobre TLS"


def criar_cliente(segredos, papel, client_id, websocket):
    """Cliente MQTT do papel ("servidor", "app") no EMQX Cloud: so TLS, com senha."""
    transporte = "websockets" if websocket else "tcp"
    try:                                    # paho-mqtt 2.x
        cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                              client_id=client_id, transport=transporte)
    except (AttributeError, TypeError):     # paho-mqtt 1.x
        cliente = mqtt.Client(client_id=client_id, transport=transporte)
    cliente.tls_set()
    cred = segredos[papel]
    cliente.username_pw_set(cred["usuario"], cred["senha"])
    # Fila de saida limitada e reconexao com espera crescente (broker fora)
    cliente.max_queued_messages_set(2000)
    cliente.reconnect_delay_set(min_delay=1, max_delay=30)
    if websocket:
        cliente.ws_set_options(path=segredos.get("caminho_ws", "/mqtt"))
        return cliente, segredos.get("porta_wss", 8084)
    return cliente, segredos.get("porta_tls", 8883)


def carregar_validadores():
    """Um validador por eventType, a partir de contrato/v1/*.schema.json."""
    pasta = os.path.join(RAIZ, "contrato", "v1")
    v = {}
    for nome in HEARTBEATS + ("presenca.sensor.v1", "presenca.cadastro.v1",
                              "presenca.comando.v1", "presenca.comando.ack.v1"):
        with open(os.path.join(pasta, f"{nome}.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        v[nome] = (schema, Draft202012Validator(schema) if Draft202012Validator else None)
    if Draft202012Validator is None:
        print(f"{AMARELO}jsonschema ausente: validação reduzida. pip install jsonschema{RESET}")
    return v


def agora_ms():
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
class Sessao:
    """A aula de UM aluno. O log e a unica fonte de verdade; todo o resto e derivado."""

    def __init__(self, aluno=None, turma=None, aula_id=None, id=None):
        self.id = id or "s" + secrets.token_hex(4)
        self.aluno = aluno            # pseudonimo; None ate o primeiro heartbeat
        self.turma = turma            # codigo da turma (heartbeat v3)
        self.aula_id = aula_id        # qual aula da turma
        self.log = []                 # heartbeats aceitos: dicts com t e classe
        self.vistos = set()           # eventIds ja processados
        self.maior_seq = {}           # bootId -> maior sequencia vista
        self.lacunas = {}             # bootId -> sequencias que faltam
        self.deslocamento = {}        # bootId -> segundos somados a eventTimeMs
        self.inicio = None
        self.avisos_enviados = set()
        self.encerrada = False
        self.recuperada = False
        self.contagem = dict(aceitos=0, duplicados=0, fora_de_ordem=0, saltos=0,
                             perdidos=0, atrasados=0, invalidos=0, recusados=0)
        self.ingenuo_s = 0.0          # contador "ao vivo", sem dedup - so para comparar
        self.ultimo_resultado = None

    def linha_do_tempo(self, boot, event_time_ms):
        """Posicao do heartbeat na linha do tempo da sessao, em segundos.

        O relogio do aparelho recomeca a cada boot: e usado so como DIFERENCA
        dentro de um mesmo boot. Um boot novo e encaixado logo depois do ultimo
        instante conhecido.
        """
        t_local = event_time_ms / 1000.0
        if boot not in self.deslocamento:
            if not self.log:
                self.deslocamento[boot] = 0.0
            else:
                ultimo = max(e["t"] for e in self.log)
                self.deslocamento[boot] = ultimo + 0.5 - t_local
        return t_local + self.deslocamento[boot]

    def para_banco(self, sala, p):
        """A linha de `sessoes`: o resultado e o que precisa para recuperar."""
        d = {"id": self.id, "aluno": self.aluno, "turma": self.turma, "aula_id": self.aula_id,
             "sala": sala, "inicio_t": self.inicio, "avisos": sorted(self.avisos_enviados),
             "contagem": dict(self.contagem)}
        r = self.ultimo_resultado
        if r is not None:
            d.update(estado=r.estado, acumulado_s=r.acumulado_s, presenca_s=r.presenca_s,
                     ausencia_creditada_s=r.ausencia_creditada_s, tempo_aula_s=r.agora,
                     percentual=min(100.0, r.percentual(p)))
            if self.encerrada:
                d["encerrada_em"] = datetime.now(timezone.utc)
                d["aprovado"] = r.acumulado_s >= p.presenca_minima * p.duracao_aula
        return d


def reconstruir(linha, eventos, p):
    """Refaz uma Sessao a partir do banco (recuperacao depois de reiniciar).

    Nao precisa de nenhum estado "ao vivo" salvo: o resultado sai de novo do
    log, como a cada heartbeat (decisao 7 do projeto). Sobra restaurar o que
    impede contar duas vezes: os eventIds vistos, a maior sequencia e o
    encaixe de cada boot na linha do tempo.
    """
    s = Sessao(linha["aluno"], linha.get("turma"), linha.get("aula_id"), id=linha["id"])
    s.inicio = linha.get("inicio_t")
    s.avisos_enviados = set(linha.get("avisos") or [])
    s.contagem.update(linha.get("contagem") or {})
    s.recuperada = True
    for e in eventos:
        s.vistos.add(e["event_id"])
        if e["classificacao"] == "duplicado" or e.get("t_linha") is None:
            continue
        carga = e["carga"] if isinstance(e["carga"], dict) else json.loads(e["carga"])
        boot = e["boot_id"]
        s.maior_seq[boot] = max(s.maior_seq.get(boot, 0), e["sequencia"])
        s.deslocamento[boot] = e["t_linha"] - carga["eventTimeMs"] / 1000.0
        s.log.append({"t": e["t_linha"], "classe": e["classe"]})
    if not s.log:
        return None
    if s.inicio is None:
        s.inicio = min(x["t"] for x in s.log)
    s.ultimo_resultado = calcular([(x["t"], x["classe"]) for x in s.log], p, inicio=s.inicio)
    s.encerrada = s.ultimo_resultado.encerrada
    return s


class Servidor:
    def __init__(self, cfg, segredos=None, chave=None, banco=None, conectar_mqtt=True):
        self.cfg = cfg
        self.quieto = "--quieto" in sys.argv
        if segredos is None:
            segredos = carregar_segredos(os.path.join(RAIZ, "segredos.json"))
        self.segredos = segredos
        self.chave = chave or chave_do_servidor(os.path.join(AQUI, "chave-servidor.pem"))
        self.chaves_vistas = {}       # aluno -> chave publica
        self.recusas = {}             # motivo -> quantas
        self.p = Parametros.de_config(cfg)
        self.sala = Sala.de_config(cfg)
        self.validadores = carregar_validadores()
        self.banco = banco or abrir_banco(cfg, self._aviso_banco, "--sem-banco" in sys.argv)
        self.sessoes = {}             # aluno -> Sessao
        self.sessao = Sessao()
        self.seq_estado = 0
        # Silencio por aparelho (Marco 4): cada celular tem o seu relogio de contato
        self.ultimo_contato = {}      # aluno -> time.time()
        self.silenciosos = set()
        self.bateria = {}             # aluno -> (nivel, carregando)
        self.sensores_vistos = deque(maxlen=5000)
        self.ancora_ouvida = {}       # ancora -> time.time() em que alguem a ouviu
        self.ancoras_mudas = set()
        self.comandos = {}            # comandoId -> dict (enviados por este servidor)
        self.turmas_sujas = set()     # relatorio a republicar
        self.painel_a_cada = 0 if self.quieto else cfg.get("painel_a_cada", 12)
        self.trava = threading.RLock()
        self.parar = threading.Event()
        self.log = open(os.path.join(AQUI, "recebidos.log"), "a", encoding="utf-8")
        self.recuperar()

        self.cliente = None
        if conectar_mqtt:
            self.cliente, self.porta = criar_cliente(
                segredos, "servidor", cfg.get("client_id", "presenca-servidor"), usar_websocket(cfg))
            self.cliente.on_connect = self._ao_conectar
            self.cliente.on_disconnect = self._ao_desconectar
            self.cliente.on_message = self._ao_receber

    def topico(self, nome):
        return self.cfg[f"topico_{nome}"]

    # -- recuperacao ---------------------------------------------------------
    def recuperar(self):
        """Volta a aula que estava em andamento quando o servidor caiu."""
        linhas = self.banco.sessoes_abertas(self.cfg.get("recuperar_horas", 3))
        for l in linhas:
            s = reconstruir(l, self.banco.eventos_da_sessao(l["id"]), self.p)
            if s is None:
                continue
            self.sessoes[s.aluno] = s
            self.sessao = s
            r = s.ultimo_resultado
            self._aviso_linha(CIANO, "↺ RECUPERADA",
                              f"aula {s.id} de {s.aluno}: {len(s.log)} mensagens relidas do banco, "
                              f"{r.estado}, {num(r.percentual(self.p), 0)} %"
                              + (" (já tinha terminado)" if s.encerrada else ""))
            if s.turma:
                self.turmas_sujas.add(s.turma)

    # -- MQTT ----------------------------------------------------------------
    def _ao_conectar(self, cliente, userdata, flags, rc, properties=None):
        if rc != 0:
            print(f"{VERMELHO}{NEGRITO}O broker RECUSOU a conexão: {rc}. "
                  f"Confira usuário e senha em segredos.json.{RESET}")
            return
        for nome in ("heartbeat", "sensor"):
            cliente.subscribe(self.topico(nome), qos=1)
        # Cadastro RETIDO, um topico por aluno: ao (re)conectar o broker reentrega
        # todos. Assim o nome nao se perde se o servidor estava fora quando o
        # aluno se cadastrou.
        cliente.subscribe(self.topico("cadastro") + "/+", qos=1)
        cliente.subscribe(self.topico("comando") + "/+", qos=1)
        cliente.subscribe(self.topico("comando_ack") + "/+", qos=1)
        print(f"{VERDE}Conectado ao {self.segredos['broker']}, porta {self.porta} "
              f"({descrever_transporte(self.cfg)}, usuário {self.segredos['servidor']['usuario']}).{RESET}")
        print(f"{CINZA}Chave pública do servidor (o app confere estado, avisos, comandos e relatório):\n"
              f"  {publica_hex(self.chave)}{RESET}")
        banco = "PostgreSQL/TimescaleDB" if type(self.banco).__name__ == "Banco" else "MEMÓRIA (sem banco)"
        print(f"{CINZA}Gravando em: {banco}. Heartbeat esperado a cada "
              f"{self.cfg.get('intervalo_heartbeat_s', 5)} s.{RESET}")
        self._cabecalho_sessao()

    def _ao_desconectar(self, cliente, userdata, *args):
        self._aviso_linha(MAGENTA, "… BROKER", "conexão com o broker caiu; tentando de novo sozinho")

    def _ao_receber(self, cliente, userdata, msg):
        recebido_em = datetime.now(timezone.utc)      # carimbo do servidor
        topico = msg.topic
        with self.trava:
            if topico == self.topico("heartbeat"):
                self._processar(msg.payload, recebido_em, topico)
            elif topico == self.topico("sensor"):
                self._processar_sensor(msg.payload, recebido_em, topico)
            elif topico.startswith(self.topico("cadastro") + "/"):
                self._processar_cadastro(msg.payload, recebido_em, topico,
                                         retido=bool(getattr(msg, "retain", False)))
            elif topico.startswith(self.topico("comando_ack") + "/"):
                self._processar_confirmacao(msg.payload, recebido_em, topico)
            elif topico.startswith(self.topico("comando") + "/"):
                self._registrar_comando_do_admin(msg.payload, topico)

    # -- validacao e seguranca -----------------------------------------------
    def _validar(self, dado, tipos):
        if not isinstance(dado, dict):
            return "payload nao e um objeto JSON"
        tipo = dado.get("eventType")
        if tipo not in tipos:
            return f"eventType inesperado: {tipo!r}"
        schema, validador = self.validadores[tipo]
        if validador is not None:
            erros = sorted(validador.iter_errors(dado), key=lambda e: list(e.path))
            if erros:
                campo = ".".join(str(x) for x in erros[0].path) or "(raiz)"
                return f"{campo}: {erros[0].message}"
        else:
            faltando = [c for c in schema["required"] if c not in dado]
            if faltando:
                return f"campos ausentes: {faltando}"
        return None

    def _abrir_do_aluno(self, topico, payload, tipos, contato=True):
        """Envelope + contrato + "a chave e mesmo deste aluno". Devolve (dado, chave).

        contato=False: mensagem retida reentregue pelo broker; nao e sinal de vida."""
        try:
            texto = payload.decode("utf-8")
        except UnicodeDecodeError:
            raise Recusa("não é texto")
        de, chave, dado = abrir_envelope(topico, texto)
        motivo = self._validar(dado, tipos)
        if motivo:
            raise Recusa("FORA DO CONTRATO", motivo)
        aluno, device = identidade_da_chave(chave)
        if dado["aluno"] != aluno or dado.get("deviceId", device) != device or de != aluno:
            raise Recusa("IDENTIDADE TROCADA",
                         f"assinou com a chave de {aluno}, mas diz ser {dado['aluno']}")
        if aluno not in self.chaves_vistas:
            self.chaves_vistas[aluno] = chave
            self.banco.aluno_visto(aluno, chave, device)
            self._aviso_linha(CIANO, "+ APARELHO", f"{aluno} se identificou (chave {chave[:16]}…)")
        if contato:
            self._contato(aluno)
        return dado, chave

    def _conferir(self, topico, payload):
        """Heartbeat: identidade e, depois, se ouviu a ancora AGORA (token)."""
        dado, _ = self._abrir_do_aluno(topico or self.topico("heartbeat"), payload, HEARTBEATS)
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
        return dado

    def _recusar(self, recusa, topico, recebido_em):
        self.sessao.contagem["recusados"] += 1
        self.recusas[recusa.motivo] = self.recusas.get(recusa.motivo, 0) + 1
        detalhe = f" — {recusa.detalhe}" if recusa.detalhe else ""
        self._aviso_linha(VERMELHO, "x RECUSADA", f"{recusa.motivo}{detalhe}")
        self.banco.recusa(recebido_em, topico, recusa.motivo, recusa.detalhe)

    def _contato(self, aluno):
        self.ultimo_contato[aluno] = time.time()
        if aluno in self.silenciosos:
            self.silenciosos.discard(aluno)
            self._aviso_linha(CIANO, "+ VOLTOU", f"{aluno}: as mensagens voltaram a chegar")

    # -- heartbeat -----------------------------------------------------------
    def _processar(self, payload, recebido_em, topico=None):
        try:
            dado = self._conferir(topico, payload)
        except Recusa as r:
            self._recusar(r, topico, recebido_em)
            return

        for a in dado["ancoras"]:
            if a["rssi"] is not None:
                self.ancora_ouvida[a["id"]] = time.time()
                if a["id"] in self.ancoras_mudas:
                    self.ancoras_mudas.discard(a["id"])
                    self._aviso_linha(CIANO, "+ ÂNCORA", f"{a['id']} voltou a ser ouvida")

        eid, seq, boot = dado["eventId"], dado["sequence"], dado["bootId"]
        s = self._sessao_do_aluno(dado["aluno"], boot, dado.get("turma"), dado.get("aulaId"))

        classe_ingenua, _ = classificar(dado, self.sala)
        if classe_ingenua == DENTRO:
            s.ingenuo_s += self.cfg.get("intervalo_heartbeat_s", 0.5)   # segundos de relogio

        if s.encerrada:
            return

        # 1. DUPLICATA - mesma identidade ja processada
        if eid in s.vistos:
            s.contagem["duplicados"] += 1
            self._aviso_linha(AMARELO, "! REPETIDA", f"a nº {seq} já tinha chegado; ignorada")
            self._gravar(dado, recebido_em, "duplicado", None, s)
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
                lacunas.discard(seq)
                s.contagem["perdidos"] -= 1
                extra = " (não estava perdida)"
            self._aviso_linha(AMARELO, "! FORA DE ORDEM",
                              f"a nº {seq} chegou depois da nº {maior}; posta no lugar certo{extra}")

        # 3. SALTO - lacuna na sequencia
        elif maior and seq > maior + 1:
            faltam = seq - maior - 1
            lacunas.update(range(maior + 1, seq))
            s.contagem["saltos"] += 1
            s.contagem["perdidos"] += faltam
            self._aviso_linha(VERMELHO, "! SALTO",
                              f"esperava a nº {maior + 1}, veio a nº {seq}: {faltam} perdida(s)")

        if dado.get("bufferizado"):
            s.contagem["atrasados"] += 1
            classificacao = "atrasado"
            self._aviso_linha(CIANO, "~ ATRASADA",
                              f"a nº {seq} ficou guardada no celular sem rede; entrou no passado")

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
        if r.encerrada:
            s.encerrada = True

        dentro_pol = None if pos is None else self.sala.contem(pos)
        self._mostrar(dado, t - s.inicio, classe, pos, r, mudou, s)
        self._publicar_estado(dado["aluno"], r, classe, pos, dentro_pol)
        self._publicar_avisos(dado["aluno"], r, s)
        self._gravar(dado, recebido_em, classificacao,
                     {"t": round(t - s.inicio, 3), "t_linha": t, "classe": classe,
                      "posicao": None if pos is None else [round(pos[0], 2), round(pos[1], 2)],
                      "estado": r.estado}, s)
        self.banco.salvar_sessao(s.para_banco(self.cfg.get("entity_id"), self.p))
        if s.turma:
            self.turmas_sujas.add(s.turma)

        if s.encerrada:
            self.painel(final=True, s=s)
        elif self.painel_a_cada and s.contagem["aceitos"] % self.painel_a_cada == 0:
            self.painel(s=s)

    def _sessao_do_aluno(self, aluno, boot, turma=None, aula_id=None):
        """A sessao deste aluno nesta aula. Aula nova (aulaId diferente, ou boot
        novo depois da aula ter terminado) abre uma sessao nova."""
        s = self.sessoes.get(aluno)
        nova_aula = s is not None and aula_id is not None and s.aula_id not in (None, aula_id)
        if s is None and self.sessao.aluno is None and not self.sessao.log:
            s = self.sessao                      # a sessao aberta ao conectar
            s.aluno, s.turma, s.aula_id = aluno, turma, aula_id
        elif s is None or nova_aula or (s.encerrada and boot not in s.deslocamento):
            s = Sessao(aluno, turma, aula_id)
            self.sessao = s
            self._cabecalho_sessao()
        if s.turma is None and turma:
            s.turma, s.aula_id = turma, aula_id
        self.sessoes[aluno] = s
        self.sessao = s
        return s

    # -- sensores do celular (Marco 4) ---------------------------------------
    def _processar_sensor(self, payload, recebido_em, topico):
        try:
            dado, _ = self._abrir_do_aluno(topico, payload, ("presenca.sensor.v1",))
        except Recusa as r:
            self._recusar(r, topico, recebido_em)
            return
        if dado["sensorId"] in self.sensores_vistos:
            return
        self.sensores_vistos.append(dado["sensorId"])
        ac, bat = dado.get("acelerometro"), dado.get("bateria")
        if bat:
            self.bateria[dado["aluno"]] = (bat["nivel"], bat["carregando"])
        self.banco.sensor({
            "recebido_em": recebido_em, "aluno": dado["aluno"], "turma": dado["turma"],
            "sensor_id": dado["sensorId"],
            "movimento": ac["movimento"] if ac else None, "parado": ac["parado"] if ac else None,
            "bateria": bat["nivel"] if bat else None, "carregando": bat["carregando"] if bat else None,
            "carga": dado,
        })
        if not self.quieto and self.cfg.get("mostrar_sensores", True):
            mov = "sem acelerômetro" if not ac else (
                "parado" if ac["parado"] else f"mexendo ({num(ac['movimento'], 3)} g)")
            b = "" if not bat else f" · bateria {round(bat['nivel'] * 100)} %" + (" carregando" if bat["carregando"] else "")
            print(f"{CINZA}  sensor   {dado['aluno']}: {mov}{b}{RESET}")

    # -- cadastro (nome e matricula, LGPD) -----------------------------------
    def _processar_cadastro(self, payload, recebido_em, topico, retido=False):
        if not payload:
            return                                 # retido apagado (aluno eliminado)
        try:
            dado, chave = self._abrir_do_aluno(topico, payload, ("presenca.cadastro.v1",),
                                               contato=not retido)
            if topico.rsplit("/", 1)[-1] != dado["aluno"]:
                raise Recusa("IDENTIDADE TROCADA", f"cadastro de {dado['aluno']} no tópico de outro aluno")
        except Recusa as r:
            self._recusar(r, topico, recebido_em)
            return
        _, device = identidade_da_chave(chave)
        self.banco.identificacao(dado["aluno"], chave, device, dado["turma"],
                                 dado["nome"].strip(), dado.get("matricula", "").strip() or None)
        self.turmas_sujas.add(dado["turma"])
        self._aviso_linha(CIANO, "+ CADASTRO", f"{dado['aluno']} = {dado['nome']} (turma {dado['turma']})"
                          + (" (retido no broker)" if retido else ""))

    def esquecer_aluno(self, aluno):
        """LGPD art. 18, VI: apaga do banco, da memoria e o cadastro retido no broker.
        Le/apaga no banco SEM a trava (pode demorar). Devolve as linhas apagadas ou None."""
        n = self.banco.apagar_aluno(aluno)
        with self.trava:
            self.sessoes.pop(aluno, None)
            self.ultimo_contato.pop(aluno, None)
            self.chaves_vistas.pop(aluno, None)
        if self.cliente is not None:
            self.cliente.publish(f"{self.topico('cadastro')}/{aluno}", b"", qos=1, retain=True)
        return n

    # -- atuador (Marco 4) ---------------------------------------------------
    def enviar_comando(self, aluno, tipo, texto=None, validade_s=60):
        """Manda uma operacao ao celular. Devolve o comandoId ou None."""
        s = self.sessoes.get(aluno)
        if s is None or not s.turma:
            self._aviso_linha(AMARELO, "! COMANDO", f"{aluno} não está em nenhuma aula agora")
            return None
        msg = {"eventType": "presenca.comando.v1", "comandoId": "srv-" + secrets.token_hex(4),
               "aluno": aluno, "turma": s.turma, "tipo": tipo,
               "texto": (texto or TEXTO_COMANDO[tipo])[:200], "emitidoEmMs": agora_ms(),
               "validadeS": validade_s}
        topico = f"{self.topico('comando')}/{aluno}"
        self.cliente.publish(topico, envelopar(self.chave, "servidor", topico, msg), qos=1)
        self.comandos[msg["comandoId"]] = {**msg, "enviadoEm": time.time()}
        self.banco.comando({**msg, "de": "servidor"})
        self._aviso_linha(MAGENTA, "→ COMANDO", f"{tipo} para {aluno}: \"{msg['texto']}\" ({msg['comandoId']})")
        return msg["comandoId"]

    def _registrar_comando_do_admin(self, payload, topico):
        """O professor tambem manda comandos, direto do app. Aqui so se registra."""
        try:
            de, chave, dado = abrir_envelope(topico, payload.decode("utf-8"))
        except (Recusa, UnicodeDecodeError):
            return
        if chave == publica_hex(self.chave) or self._validar(dado, ("presenca.comando.v1",)):
            return                                  # o proprio servidor, ou lixo
        self.banco.comando({**dado, "de": "admin"})
        self._aviso_linha(MAGENTA, "→ COMANDO", f"o professor mandou {dado['tipo']} para {dado['aluno']}")

    def _processar_confirmacao(self, payload, recebido_em, topico):
        try:
            dado, _ = self._abrir_do_aluno(topico, payload, ("presenca.comando.ack.v1",))
        except Recusa as r:
            self._recusar(r, topico, recebido_em)
            return
        self.banco.confirmacao(dado["comandoId"], dado["resultado"])
        c = self.comandos.get(dado["comandoId"])
        demora = f" em {num(time.time() - c['enviadoEm'])} s" if c else ""
        cor = VERDE if dado["resultado"] in ("executado", "respondido") else VERMELHO
        self._aviso_linha(cor, "✓ CONFIRMOU" if cor == VERDE else "x NÃO EXECUTOU",
                          f"{dado['aluno']}: {dado['resultado']}{demora}"
                          + (f" — {dado['detalhe']}" if dado.get("detalhe") else ""))

    # -- retorno ao aparelho -------------------------------------------------
    def _publicar(self, topico, msg, qos=0, retain=False):
        if self.cliente is not None:
            self.cliente.publish(topico, envelopar(self.chave, "servidor", topico, msg), qos=qos, retain=retain)

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
            "emitidoEmMs": agora_ms(),
        }
        self._publicar(f"{self.topico('estado')}/{aluno}", msg, qos=0, retain=True)

    def _publicar_avisos(self, aluno, r, s):
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
                "emitidoEmMs": agora_ms(),
            }
            self._publicar(f"{self.topico('aviso')}/{aluno}", msg, qos=1)
            cor = VERMELHO if aviso.tipo != FIM_DA_AULA else CIANO
            print(f"\n{cor}{NEGRITO}  ┌─ AVISO ENVIADO A {aluno}, aos {num(aviso.em)} s ─────────")
            print(f"  │ {texto}")
            print(f"  └──────────────────────────────────────────────────{RESET}\n")

    # -- relatorio -----------------------------------------------------------
    def montar_relatorio(self, turma):
        linhas = self.banco.sessoes_da_turma(turma)
        if linhas is None:                         # banco fora: tenta depois
            return None
        sensores = self.banco.resumo_sensores([l["id"] for l in linhas])
        return relatorio.montar(turma, linhas, sensores, agora_ms())

    def _publicar_relatorios(self):
        """Le o banco: NUNCA chamar segurando self.trava (banco lento = mensagens paradas)."""
        with self.trava:
            turmas, self.turmas_sujas = self.turmas_sujas, set()
        for turma in turmas:
            rel = self.montar_relatorio(turma)
            if rel is None:                        # banco fora: tenta no proximo ciclo
                with self.trava:
                    self.turmas_sujas.add(turma)
                continue
            self._publicar(f"{self.topico('relatorio')}/{turma}", rel, qos=1, retain=True)

    # -- vigia: silencio, ancora muda, banco, relatorio ----------------------
    def _vigiar(self):
        limite = self.cfg.get("silencio_s", 15)
        while not self.parar.wait(1):
            with self.trava:
                agora = time.time()
                for aluno, t in self.ultimo_contato.items():
                    s = self.sessoes.get(aluno)
                    if (aluno in self.silenciosos or s is None or s.encerrada
                            or agora - t <= limite):
                        continue
                    self.silenciosos.add(aluno)
                    nivel, carregando = self.bateria.get(aluno, (None, False))
                    if nivel is not None and nivel <= self.cfg.get("bateria_baixa", 0.05) and not carregando:
                        motivo = f"provável BATERIA (a última leitura era {round(nivel * 100)} %)"
                    else:
                        motivo = "rede, app fechado ou celular desligado (motivo desconhecido)"
                    self._aviso_linha(MAGENTA, "… SILÊNCIO",
                                      f"{aluno}: nada chega há {limite} s — {motivo}; "
                                      f"nada é decidido sem mensagem")
                # Ancora que ninguem mais ouve, enquanto os celulares seguem falando
                ativos = [a for a, t in self.ultimo_contato.items() if agora - t < 10]
                for ancora, t in self.ancora_ouvida.items():
                    if ativos and ancora not in self.ancoras_mudas and agora - t > limite:
                        self.ancoras_mudas.add(ancora)
                        self._aviso_linha(VERMELHO, "! ÂNCORA MUDA",
                                          f"{ancora}: nenhum celular a ouve há {limite} s "
                                          f"(desligada ou sem energia?). Os celulares ficam 'fora'.")
                self.banco.tentar_esvaziar()
            # Fora da trava: montar o relatorio le o banco, e o banco pode estar travado.
            if int(time.time()) % self.cfg.get("relatorio_a_cada_s", 5) == 0:
                self._publicar_relatorios()

    # -- saida ---------------------------------------------------------------
    def _aviso_banco(self, texto):
        print(f"  {AMARELO}{'! BANCO':<15}{RESET} {texto}")

    def _aviso_linha(self, cor, rotulo, texto):
        print(f"  {cor}{rotulo:<15}{RESET} {texto}")

    def _mostrar(self, dado, t, classe, pos, r, mudou, s):
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
            print(f"{CINZA}{s.aluno}{RESET}", end=" ")
        print(f"{CINZA}{num(t) + ' s':>8}  {'nº ' + str(dado['sequence']):<10}{RESET}{onde:<14}"
              f"{cor}{situacao:<24}{RESET}{num(r.acumulado_s)} s")
        if mudou and r.transicoes:
            tt, de, para, porque = r.transicoes[-1]
            print(f"{cor}{NEGRITO}  >>> {num(tt)} s: {MUDANCA.get(porque, porque)}{RESET}")

    def _gravar(self, dado, recebido_em, classificacao, derivado, s):
        self.log.write(json.dumps({
            "recebidoEm": recebido_em.isoformat(),
            "sessao": s.id,
            "classificacao": classificacao,
            "derivado": derivado,
            "evento": dado,
        }, ensure_ascii=False) + "\n")
        self.log.flush()
        melhor = [a["rssi"] for a in dado["ancoras"] if a["rssi"] is not None]
        self.banco.evento({
            "recebido_em": recebido_em, "sessao": s.id, "aluno": dado["aluno"],
            "turma": dado.get("turma"), "event_id": dado["eventId"], "boot_id": dado["bootId"],
            "sequencia": dado["sequence"], "classificacao": classificacao,
            "t_linha": derivado["t_linha"] if derivado else None,
            "classe": derivado["classe"] if derivado else None,
            "estado": derivado["estado"] if derivado else None,
            "regiao": dado.get("state"), "rssi": max(melhor) if melhor else None,
            "bufferizado": bool(dado.get("bufferizado")), "carga": dado,
        })

    def _cabecalho_sessao(self):
        p = self.p
        quem = f" · aluno {self.sessao.aluno}" if self.sessao.aluno else ""
        print(f"\n{CIANO}{NEGRITO}── AULA {self.sessao.id}{quem} COMEÇOU ──────────────────────────────{RESET}")
        print(f"{CINZA}  dura {num(p.duracao_aula, 0)} s · pode sair por até {num(p.orcamento, 0)} s no total · "
              f"avisos aos {num(p.aviso_1, 0)} s e {num(p.aviso_2, 0)} s fora")
        print(f"  (na demonstração, 1 s = {num(p.escala, 0)} s de uma aula de verdade)")
        print(f"\n{'tempo':>8}  {'mensagem':<10}{'onde':<14}{'situação':<24}tempo que contou{RESET}")

    def painel(self, final=False, s=None):
        s = s or self.sessao
        r = s.ultimo_resultado
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
        fila = len(self.banco.fila)
        print(f"  Banco:      {'gravando' if self.banco.online else 'FORA DO AR'}"
              + (f" · {fila} gravação(ões) esperando" if fila else "")
              + (" · aula RECUPERADA do banco depois de reiniciar" if s.recuperada else ""))
        print(f"  ══════════════════════════════════════════════════{RESET}\n")

    def mostrar_relatorios(self):
        turmas = {s.turma for s in self.sessoes.values() if s.turma}
        if not turmas:
            print(f"{CINZA}Nenhuma turma com aula ainda.{RESET}")
        for turma in sorted(turmas):
            rel = self.montar_relatorio(turma)
            if rel is None:
                print(f"{AMARELO}Banco fora do ar: relatório indisponível.{RESET}")
                continue
            print(f"\n{CIANO}{NEGRITO}  ══ RELATÓRIO DA TURMA {turma} ══{RESET}")
            for a in rel["aulas"][:3]:
                print(f"{CIANO}  aula {a['aulaId']}{' (em andamento)' if a['emAndamento'] else ''}{RESET}")
                for x in a["alunos"]:
                    nome = x["nome"] or x["aluno"]
                    res = "…" if x["aprovado"] is None else ("presente" if x["aprovado"] else "falta")
                    parado = " · celular PARADO a aula toda" if x["celularParado"] else ""
                    print(f"    {nome:<24} {num(x['percentual'], 0):>4} %  {res}{parado}")

    # -- terminal ------------------------------------------------------------
    def _laco_teclado(self):
        for linha in sys.stdin:
            partes = linha.strip().split(maxsplit=3)
            t = partes[0].lower() if partes else ""
            if t == "q":
                self.parar.set()
                break
            with self.trava:
                if t == "p":
                    self.painel()
                elif t == "r":
                    self.mostrar_relatorios()
                elif t == "b":
                    for e in self.banco.estatisticas() or []:
                        print(f"  {e['tabela']:<10} {e['pedacos']} pedaço(s) · {e['tamanho']}")
                    print(f"  fila: {len(self.banco.fila)} · descartadas: {self.banco.descartados}")
                elif t == "c" and len(partes) >= 3 and partes[2] in TIPOS_COMANDO:
                    alvos = ([a for a, s in self.sessoes.items() if not s.encerrada]
                             if partes[1] == "todos" else [partes[1]])
                    for a in alvos:
                        self.enviar_comando(a, partes[2], partes[3] if len(partes) > 3 else None)
                elif t == "n":
                    self.sessoes = {}
                    self.sessao = Sessao()
                    self._cabecalho_sessao()
                elif t:
                    print(f"{CINZA}Teclas: p resumo · r relatório · c <aluno|todos> <vibrar|chamar|lanterna> "
                          f"[texto] · b banco · n aula nova · q sair (sempre com Enter){RESET}")

    def executar(self):
        print(f"\n{CIANO}{NEGRITO}══ Presença · Marco 4 · servidor de permanência ══{RESET}")
        print(f"{CINZA}Teclas: p resumo · r relatório · c <aluno|todos> <vibrar|chamar|lanterna> "
              f"· b banco · n aula nova · q sair (sempre com Enter){RESET}")
        if self.cfg.get("api", {}).get("ligada", True):
            from api import iniciar_api
            iniciar_api(self, self.cfg.get("api", {}))
        self.cliente.connect_async(self.segredos["broker"], self.porta, 60)
        self.cliente.loop_start()
        threading.Thread(target=self._laco_teclado, daemon=True).start()
        threading.Thread(target=self._vigiar, daemon=True).start()
        try:
            while not self.parar.wait(3600):
                pass
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
