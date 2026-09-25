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
RAIZ = os.path.dirname(AQUI)

VERDE, AMARELO, VERMELHO, CIANO, CINZA, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[90m", "\033[0m",
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
            print(f"{CINZA}configuracao: {nome}{RESET}")
            return cfg
    raise SystemExit("Nenhum config.json ou config.exemplo.json encontrado.")


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

        try:                                    # paho-mqtt 2.x
            self.cliente = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=cfg.get("client_id", "gateway-204"),
            )
        except (AttributeError, TypeError):     # paho-mqtt 1.x
            self.cliente = mqtt.Client(client_id=cfg.get("client_id", "gateway-204"))

        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_message = self._ao_receber

    # -- MQTT ---------------------------------------------------------------
    def _ao_conectar(self, cliente, userdata, flags, rc, properties=None):
        print(f"{VERDE}[MQTT] conectado a {self.cfg['broker']}:{self.cfg['porta']}{RESET}")
        cliente.subscribe(self.cfg["topico_ambiente"], qos=1)
        print(f"{CINZA}[MQTT] assinando {self.cfg['topico_ambiente']}{RESET}\n")
        self._publicar_contagem()

    def _ao_receber(self, cliente, userdata, msg):
        recebido_em = datetime.now(timezone.utc)   # CARIMBO AUTORITATIVO
        e = self.estado

        try:
            dado = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as erro:
            e.total_invalidos += 1
            self._linha(VERMELHO, "INVALIDO", f"payload ilegivel: {erro}")
            return

        ok, motivo = self.validador.validar(dado)
        if not ok:
            e.total_invalidos += 1
            self._linha(VERMELHO, "INVALIDO", motivo)
            return

        event_id = dado["eventId"]
        seq = dado["sequence"]
        bufferizado = dado.get("bufferizado", False)

        # ---- 1. DUPLICATA: mesma identidade ja processada ----
        if e.ja_visto(event_id):
            e.total_duplicados += 1
            self._linha(AMARELO, "DUPLICADO",
                        f"{event_id} ja processado - descartado sem efeito no estado")
            return

        # ---- 2. FORA DE ORDEM: sequencia menor que a maior ja vista ----
        if seq < e.maior_sequencia:
            e.total_fora_de_ordem += 1
            atraso = e.maior_sequencia - seq
            self._linha(AMARELO, "FORA DE ORDEM",
                        f"seq={seq} chegou depois de {e.maior_sequencia} "
                        f"({atraso} atras) - aceito, nao retrocede o estado")
            e.registrar(event_id)
            self._gravar(dado, recebido_em, "fora-de-ordem")
            return

        # ---- 3. SALTO: lacuna na sequencia ----
        if e.maior_sequencia and seq > e.maior_sequencia + 1:
            faltando = seq - e.maior_sequencia - 1
            e.total_saltos += 1
            e.total_perdidos += faltando
            self._linha(VERMELHO, "SALTO",
                        f"esperado {e.maior_sequencia + 1}, recebido {seq} - "
                        f"{faltando} evento(s) perdido(s)")

        if bufferizado:
            e.total_atrasados += 1
            self._linha(CIANO, "ATRASADO",
                        f"{event_id} retido na fila local, "
                        f"tempo original {dado['eventTimeMs']} ms - recalculando")

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
        self._linha(cor, f"seq={seq:<4}",
                    f"{dado['value']:7.1f} {dado['unit']}  "
                    f"co2={dado.get('ocupacaoCo2', '?'):<13} "
                    f"radio={dado.get('contagemRadio', '?'):<3} "
                    f"{estado_novo}")

        # ---- ATUACAO do consumidor ----
        if estado_novo == "INCOERENTE" and mudou:
            e.alertas += 1
            print(f"\n{VERMELHO}{'=' * 70}")
            print("  ALERTA DE INCOERENCIA DE OCUPACAO")
            print(f"  O radio declara {dado.get('contagemRadio')} estudantes,")
            print(f"  mas o CO2 em {dado['value']:.0f} ppm indica sala {dado.get('ocupacaoCo2')}.")
            print("  Sessao marcada para revisao do professor.")
            print(f"{'=' * 70}{RESET}\n")

        self._gravar(dado, recebido_em, "aceito")

    # -- Comando para a ancora ----------------------------------------------
    def _publicar_contagem(self):
        self.sequencia_comando += 1
        comando = {
            "commandType": "gateway.contagem.v1",
            "commandId": f"gw-204#{self.sequencia_comando}",
            "entityId": self.cfg.get("entity_id", "sala-204"),
            "contagem": self.contagem_radio,
            "issuedAtMs": int(time.time() * 1000),
        }
        self.cliente.publish(self.cfg["topico_comando"], json.dumps(comando), qos=1)
        print(f"{CINZA}[COMANDO] {comando['commandId']} -> contagem do radio = "
              f"{self.contagem_radio}{RESET}")

    def _laco_comando(self):
        while not self.parar.wait(self.cfg.get("intervalo_comando_s", 10)):
            self._publicar_contagem()

    # -- Saida --------------------------------------------------------------
    def _linha(self, cor, rotulo, texto):
        agora = datetime.now().strftime("%H:%M:%S")
        print(f"{CINZA}{agora}{RESET} {cor}{rotulo:<14}{RESET} {texto}")

    def _gravar(self, dado, recebido_em, classificacao):
        self.log.write(json.dumps({
            "recebidoEm": recebido_em.isoformat(),   # carimbo do gateway
            "classificacao": classificacao,
            "evento": dado,
        }, ensure_ascii=False) + "\n")
        self.log.flush()

    def painel(self):
        e = self.estado
        print(f"\n{CIANO}{'-' * 70}")
        print(f"  estado da sala: {e.estado_sala}    "
              f"ultimo CO2: {e.ultimo_ppm if e.ultimo_ppm is None else f'{e.ultimo_ppm:.0f} ppm'}")
        print(f"  contagem declarada pelo radio: {self.contagem_radio}")
        print(f"  aceitos={e.total_aceitos}  duplicados={e.total_duplicados}  "
              f"fora de ordem={e.total_fora_de_ordem}")
        print(f"  saltos={e.total_saltos} ({e.total_perdidos} eventos perdidos)  "
              f"atrasados={e.total_atrasados}  invalidos={e.total_invalidos}")
        print(f"  alertas de incoerencia: {e.alertas}   "
              f"maior sequencia vista: {e.maior_sequencia}")
        print(f"{'-' * 70}{RESET}\n")

    # -- Terminal -----------------------------------------------------------
    def _laco_teclado(self):
        for linha in sys.stdin:
            t = linha.strip().lower()
            if t == "q":
                self.parar.set()
                break
            if t == "r":
                self.estado.reiniciar()
                print(f"{CINZA}contadores reiniciados{RESET}")
            elif t == "p":
                self.painel()
            elif t.isdigit():
                self.contagem_radio = int(t)
                self._publicar_contagem()
            elif t:
                print(f"{CINZA}comandos: <numero> | p (painel) | r (reiniciar) | q (sair){RESET}")

    def executar(self):
        print(f"\n{CIANO}=== Presenca / gateway da sala - consumidor ==={RESET}")
        if not TEM_JSONSCHEMA:
            print(f"{AMARELO}jsonschema ausente: validacao reduzida. "
                  f"pip install jsonschema{RESET}")
        print(f"{CINZA}digite um numero para mudar a contagem do radio, "
              f"p para painel, q para sair{RESET}\n")

        self.cliente.connect(self.cfg["broker"], self.cfg["porta"], 60)
        self.cliente.loop_start()

        threading.Thread(target=self._laco_comando, daemon=True).start()
        threading.Thread(target=self._laco_teclado, daemon=True).start()

        try:
            while not self.parar.is_set():
                time.sleep(self.cfg.get("intervalo_painel_s", 20))
                if not self.parar.is_set():
                    self.painel()
        except KeyboardInterrupt:
            pass
        finally:
            self.parar.set()
            self.cliente.loop_stop()
            self.cliente.disconnect()
            self.painel()
            self.log.close()
            print(f"{CINZA}log gravado em recebidos.log{RESET}")


if __name__ == "__main__":
    Gateway(carregar_config(), carregar_schema()).executar()
