#!/usr/bin/env python3
"""
Projeto Presenca - Marco 2
CONSUMIDOR: gateway da sala

Recebe eventos sala.ambiente.v1 publicados pela ancora (ESP32 no Wokwi) e:
  1. valida contra o contrato versionado em contrato/v1/
  2. deduplica por eventId
  3. detecta salto, repeticao e chegada fora de ordem pela sequencia
  4. aplica o carimbo de tempo autoritativo (o do ESP32 nao e confiavel)
  5. mantem estado da sala e dispara alerta de incoerencia
  6. publica gateway.contagem.v1 - a contagem declarada pelo radio, que
     alimenta a regra executada na ancora

Uso:
    pip install -r requirements.txt
    python consumidor.py                 # usa config.json, ou config.exemplo.json
    python consumidor.py --ws            # MQTT sobre WebSocket seguro (porta 8884)

Durante a execucao, digite no terminal:
    <numero>   define a contagem de estudantes declarada pelo radio
    r          reinicia os contadores da sessao
    q          encerra
"""

import json
import os
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

try:
    from jsonschema import Draft202012Validator
    TEM_JSONSCHEMA = True
except ImportError:
    TEM_JSONSCHEMA = False

# Windows: garante que acentos nao quebrem a saida
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))

# O que aparece na tela e para ser lido por quem nao e da area.
CO2_DIZ = {"VAZIA": "sala vazia", "OCUPADA": "sala ocupada", "INDETERMINADA": "indefinido"}
SITUACAO = {"COERENTE": "COERENTE", "ATENCAO": "ATENÇÃO", "INCOERENTE": "INCOERENTE"}
RAIZ = os.path.dirname(AQUI)

VERDE, AMARELO, VERMELHO, CIANO, CINZA, NEGRITO, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[90m", "\033[1m", "\033[0m",
)


# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------
def carregar_config():
    for nome in ("config.json", "config.exemplo.json"):
        caminho = os.path.join(AQUI, nome)
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg
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


def carregar_schema():
    caminho = os.path.join(RAIZ, "contrato", "v1", "sala.ambiente.v1.schema.json")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Estado do consumidor
# ---------------------------------------------------------------------------
class Estado:
    def __init__(self, limite_dedup=500):
        self.limite_dedup = limite_dedup
        self.reiniciar()

    def reiniciar(self):
        self.vistos = OrderedDict()      # eventId -> carimbo de recepcao
        self.maior_sequencia = 0
        self.lacunas = set()             # sequencias que faltam
        self.total_aceitos = 0
        self.total_invalidos = 0
        self.total_duplicados = 0
        self.total_fora_de_ordem = 0
        self.total_saltos = 0
        self.total_perdidos = 0          # soma das lacunas
        self.total_atrasados = 0         # entregues com bufferizado=true
        self.estado_sala = "-"
        self.ultimo_ppm = None
        self.ultimo_recebido_em = None
        self.alertas = 0

    def ja_visto(self, event_id):
        return event_id in self.vistos

    def registrar(self, event_id):
        self.vistos[event_id] = time.time()
        while len(self.vistos) > self.limite_dedup:
            self.vistos.popitem(last=False)


# ---------------------------------------------------------------------------
# Validacao contra o contrato
# ---------------------------------------------------------------------------
class Validador:
    def __init__(self, schema):
        self.schema = schema
        self.validador = Draft202012Validator(schema) if TEM_JSONSCHEMA else None

    def validar(self, dado):
        """Retorna (ok, motivo). Validacao estrutural pelo schema versionado."""
        if not isinstance(dado, dict):
            return False, "payload nao e um objeto JSON"

        tipo = dado.get("eventType")
        if tipo != "sala.ambiente.v1":
            return False, f"eventType inesperado: {tipo!r} (esperado sala.ambiente.v1)"

        if self.validador is not None:
            erros = sorted(self.validador.iter_errors(dado), key=lambda e: e.path)
            if erros:
                e = erros[0]
                campo = ".".join(str(p) for p in e.path) or "(raiz)"
                return False, f"{campo}: {e.message}"
            return True, ""

        # Fallback sem jsonschema: checagem minima dos campos obrigatorios
        for campo in self.schema["required"]:
            if campo not in dado:
                return False, f"campo obrigatorio ausente: {campo}"
        valor = dado["value"]
        if not isinstance(valor, (int, float)) or not (350 <= valor <= 5000):
            return False, f"value fora da faixa valida: {valor}"
        return True, ""


# ---------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------
class Gateway:
    def __init__(self, cfg, schema):
        self.cfg = cfg
        self.estado = Estado()
        self.validador = Validador(schema)
        self.contagem_radio = cfg.get("contagem_radio_inicial", 0)
        self.sequencia_comando = 0
        self.log = open(os.path.join(AQUI, "recebidos.log"), "a", encoding="utf-8")
        self.parar = threading.Event()

        self.cliente, self.porta = criar_cliente(cfg, cfg.get("client_id", "gateway-204"))

        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_message = self._ao_receber

    # -- MQTT ---------------------------------------------------------------
    def _ao_conectar(self, cliente, userdata, flags, rc, properties=None):
        cliente.subscribe(self.cfg["topico_ambiente"], qos=1)
        print(f"{VERDE}Conectado ao {self.cfg['broker']}, porta {self.porta} "
              f"({'WebSocket seguro' if usar_websocket(self.cfg) else 'MQTT comum'}).{RESET}")
        print(f"{CINZA}Esperando as mensagens da âncora de CO₂ (o ESP32 no Wokwi).{RESET}")
        self._publicar_contagem(mostrar=True)
        print(f"\n{CINZA}  {'mensagem':<10}{'CO₂':<11}{'o CO₂ diz':<15}{'o rádio diz':<16}situação{RESET}")

    def _ao_receber(self, cliente, userdata, msg):
        recebido_em = datetime.now(timezone.utc)   # CARIMBO AUTORITATIVO
        e = self.estado

        try:
            dado = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as erro:
            e.total_invalidos += 1
            self._aviso_linha(VERMELHO, "x INVÁLIDA", "não é um JSON legível; descartada")
            return

        ok, motivo = self.validador.validar(dado)
        if not ok:
            e.total_invalidos += 1
            self._aviso_linha(VERMELHO, "x INVÁLIDA", f"fora do contrato ({motivo}); descartada")
            return

        event_id = dado["eventId"]
        seq = dado["sequence"]
        bufferizado = dado.get("bufferizado", False)

        # ---- 1. DUPLICATA: mesma identidade ja processada ----
        if e.ja_visto(event_id):
            e.total_duplicados += 1
            self._aviso_linha(AMARELO, "! REPETIDA", f"a nº {seq} já tinha chegado; ignorada")
            return

        # ---- 2. FORA DE ORDEM: sequencia menor que a maior ja vista ----
        if seq < e.maior_sequencia:
            e.total_fora_de_ordem += 1
            atraso = e.maior_sequencia - seq
            extra = ""
            if seq in e.lacunas:
                # o salto anterior contou este como perdido; so chegou atrasado
                e.lacunas.discard(seq)
                e.total_perdidos -= 1
                extra = " (não estava perdida)"
            self._aviso_linha(AMARELO, "! FORA DE ORDEM",
                              f"a nº {seq} chegou depois da nº {e.maior_sequencia}; "
                              f"guardada, sem voltar atrás{extra}")
            e.registrar(event_id)
            self._gravar(dado, recebido_em, "fora-de-ordem")
            return

        # ---- 3. SALTO: lacuna na sequencia ----
        if e.maior_sequencia and seq > e.maior_sequencia + 1:
            faltando = seq - e.maior_sequencia - 1
            e.lacunas.update(range(e.maior_sequencia + 1, seq))
            e.total_saltos += 1
            e.total_perdidos += faltando
            self._aviso_linha(VERMELHO, "! SALTO",
                              f"esperava a nº {e.maior_sequencia + 1}, veio a nº {seq}: "
                              f"{faltando} perdida(s)")

        if bufferizado:
            e.total_atrasados += 1
            self._aviso_linha(CIANO, "~ ATRASADA",
                              f"a nº {seq} ficou guardada sem rede; chegou agora")

        # ---- evento aceito ----
        e.registrar(event_id)
        e.maior_sequencia = max(e.maior_sequencia, seq)
        e.total_aceitos += 1
        e.ultimo_ppm = dado["value"]
        e.ultimo_recebido_em = recebido_em

        estado_novo = dado["state"]
        mudou = estado_novo != e.estado_sala
        e.estado_sala = estado_novo

        cor = {"COERENTE": VERDE, "ATENCAO": AMARELO, "INCOERENTE": VERMELHO}.get(
            estado_novo, RESET)
        co2_diz = CO2_DIZ.get(dado.get("ocupacaoCo2"), "?")
        radio = dado.get("contagemRadio", "?")
        print(f"{CINZA}  {'nº ' + str(seq):<10}{dado['value']:>4.0f} ppm   {RESET}{co2_diz:<15}"
              f"{str(radio) + ' estudantes':<16}{cor}{SITUACAO.get(estado_novo, estado_novo)}{RESET}")

        # ---- ATUACAO do consumidor ----
        if estado_novo == "INCOERENTE" and mudou:
            e.alertas += 1
            print(f"\n{VERMELHO}{NEGRITO}  ┌─ ALERTA: O RÁDIO E O CO₂ NÃO BATEM ───────────────")
            print(f"  │ O rádio diz que há {radio} estudantes na sala,")
            print(f"  │ mas o CO₂ ({dado['value']:.0f} ppm) diz que a sala está vazia.")
            print(f"  │ Suspeita: os celulares ficaram na sala sem os donos.")
            print(f"  │ A aula foi marcada para o professor revisar.")
            print(f"  └────────────────────────────────────────────────────{RESET}\n")

        self._gravar(dado, recebido_em, "aceito")

    # -- Comando para a ancora ----------------------------------------------
    def _publicar_contagem(self, mostrar=False):
        self.sequencia_comando += 1
        comando = {
            "commandType": "gateway.contagem.v1",
            "commandId": f"gw-204#{self.sequencia_comando}",
            "entityId": self.cfg.get("entity_id", "sala-204"),
            "contagem": self.contagem_radio,
            "issuedAtMs": int(time.time() * 1000),
        }
        self.cliente.publish(self.cfg["topico_comando"], json.dumps(comando), qos=1)
        if mostrar:     # o reenvio periodico (a cada 10 s) e silencioso
            print(f"{CIANO}  → enviado à âncora: o rádio declara {self.contagem_radio} "
                  f"estudante(s) na sala{RESET}")

    def _laco_comando(self):
        while not self.parar.wait(self.cfg.get("intervalo_comando_s", 10)):
            self._publicar_contagem()

    # -- Saida --------------------------------------------------------------
    def _aviso_linha(self, cor, rotulo, texto):
        print(f"  {cor}{rotulo:<16}{RESET} {texto}")

    def _gravar(self, dado, recebido_em, classificacao):
        self.log.write(json.dumps({
            "recebidoEm": recebido_em.isoformat(),   # carimbo do gateway
            "classificacao": classificacao,
            "evento": dado,
        }, ensure_ascii=False) + "\n")
        self.log.flush()

    def painel(self):
        e = self.estado
        situacao = {"COERENTE": "COERENTE (o rádio e o CO₂ concordam)",
                    "ATENCAO": "ATENÇÃO (ainda não dá para dizer)",
                    "INCOERENTE": "INCOERENTE (o rádio e o CO₂ discordam)"}.get(e.estado_sala, "ainda sem mensagens")
        co2 = "—" if e.ultimo_ppm is None else f"{e.ultimo_ppm:.0f} ppm"
        print(f"\n{CIANO}{NEGRITO}  ══ RESUMO DA SALA ══════════════════════════{RESET}{CIANO}")
        print(f"  Situação:          {situacao}")
        print(f"  Último CO₂:        {co2}")
        print(f"  O rádio declara:   {self.contagem_radio} estudante(s)")
        print(f"  Alertas dados:     {e.alertas}")
        print(f"  Mensagens:  recebidas: {e.total_aceitos} · repetidas: {e.total_duplicados} · "
              f"fora de ordem: {e.total_fora_de_ordem}")
        print(f"              perdidas: {e.total_perdidos} · atrasadas: {e.total_atrasados} · "
              f"inválidas: {e.total_invalidos}")
        print(f"  ════════════════════════════════════════════{RESET}\n")

    # -- Terminal -----------------------------------------------------------
    def _laco_teclado(self):
        for linha in sys.stdin:
            t = linha.strip().lower()
            if t == "q":
                self.parar.set()
                break
            if t == "r":
                self.estado.reiniciar()
                print(f"{CINZA}  contadores zerados{RESET}")
            elif t == "p":
                self.painel()
            elif t.isdigit():
                self.contagem_radio = int(t)
                self._publicar_contagem(mostrar=True)
            elif t:
                print(f"{CINZA}Teclas: um número = estudantes que o rádio declara · p = resumo · "
                      f"r = zerar · q = sair (sempre com Enter){RESET}")

    def executar(self):
        print(f"\n{CIANO}{NEGRITO}══ Presença · gateway de CO₂ da sala ══{RESET}")
        if not TEM_JSONSCHEMA:
            print(f"{AMARELO}jsonschema ausente: validacao reduzida. "
                  f"pip install jsonschema{RESET}")
        print(f"{CINZA}Teclas: um número = estudantes que o rádio declara · p = resumo · "
              f"r = zerar · q = sair (sempre com Enter){RESET}")

        self.cliente.connect(self.cfg["broker"], self.porta, 60)
        self.cliente.loop_start()

        threading.Thread(target=self._laco_comando, daemon=True).start()
        threading.Thread(target=self._laco_teclado, daemon=True).start()

        try:
            while not self.parar.wait(1):       # o resumo so aparece com a tecla p
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.parar.set()
            self.cliente.loop_stop()
            self.cliente.disconnect()
            self.painel()
            self.log.close()
            print(f"{CINZA}  registro gravado em recebidos.log{RESET}")


if __name__ == "__main__":
    Gateway(carregar_config(), carregar_schema()).executar()
