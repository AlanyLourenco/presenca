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
    p   painel da sessao
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


def carregar_config():
    for nome in ("config.json", "config.exemplo.json"):
        caminho = os.path.join(AQUI, nome)
        if os.path.exists(caminho):
            with open(caminho, encoding="utf-8") as f:
                print(f"{CINZA}configuracao: {nome}{RESET}")
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
    """Uma aula. O log e a unica fonte de verdade; todo o resto e derivado."""

    def __init__(self):
        self.id = "s" + secrets.token_hex(2)
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
        self.sessao = Sessao()
        self.seq_estado = 0
        self.ultimo_hb_real = None
        self.em_silencio = False
        self.trava = threading.Lock()
        self.parar = threading.Event()
        self.log = open(os.path.join(AQUI, "recebidos.log"), "a", encoding="utf-8")

        self.cliente, self.porta = criar_cliente(cfg, cfg.get("client_id", "presenca-servidor"))
        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_message = self._ao_receber

    # -- MQTT ----------------------------------------------------------------
    def _ao_conectar(self, cliente, userdata, flags, rc, properties=None):
        print(f"{VERDE}[MQTT] conectado a {self.cfg['broker']}:{self.porta} "
              f"({descrever_transporte(self.cfg)}){RESET}")
        cliente.subscribe(self.cfg["topico_heartbeat"], qos=1)
        print(f"{CINZA}[MQTT] assinando {self.cfg['topico_heartbeat']}{RESET}")
        self._cabecalho_sessao()

    def _ao_receber(self, cliente, userdata, msg):
        recebido_em = datetime.now(timezone.utc)      # carimbo do servidor
        with self.trava:
            self.ultimo_hb_real = time.time()
            if self.em_silencio:
                self.em_silencio = False
                self._linha(CIANO, "RETOMADO", "heartbeats voltaram a chegar")
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
            self._linha(VERMELHO, "INVALIDO", f"payload ilegivel: {erro}")
            return

        motivo = self._validar(dado)
        if motivo:
            s.contagem["invalidos"] += 1
            self._linha(VERMELHO, "INVALIDO", f"rejeitado pelo contrato - {motivo}")
            return

        # contador ingenuo: soma 0,5 s a cada heartbeat "dentro", do jeito que
        # chegar, sem deduplicar e sem ordenar. Existe so para comparacao.
        classe_ingenua, _ = classificar(dado, self.sala)
        if classe_ingenua == DENTRO:
            s.ingenuo_s += 0.5

        if s.encerrada:
            return

        eid, seq, boot = dado["eventId"], dado["sequence"], dado["bootId"]

        # 1. DUPLICATA - mesma identidade ja processada
        if eid in s.vistos:
            s.contagem["duplicados"] += 1
            self._linha(AMARELO, "DUPLICADO", f"{eid} ja processado - descartado, nada recalculado")
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
                extra = " - preenche a lacuna: nao estava perdido, so atrasado"
            self._linha(AMARELO, "FORA DE ORDEM",
                        f"seq={seq} chegou depois de {maior} - inserido na posicao "
                        f"original e sessao recalculada{extra}")

        # 3. SALTO - lacuna na sequencia
        elif maior and seq > maior + 1:
            faltam = seq - maior - 1
            lacunas.update(range(maior + 1, seq))
            s.contagem["saltos"] += 1
            s.contagem["perdidos"] += faltam
            self._linha(VERMELHO, "SALTO",
                        f"esperado {maior + 1}, recebido {seq} - {faltam} heartbeat(s) "
                        f"perdido(s); o intervalo fica sem evidencia")

        if dado.get("bufferizado"):
            s.contagem["atrasados"] += 1
            classificacao = "atrasado"
            self._linha(CIANO, "ATRASADO",
                        f"seq={seq} retido no aparelho, medido em {dado['eventTimeMs']} ms "
                        f"- entra no passado e a sessao e recalculada")

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
            print(f"\n{cor}{NEGRITO}{'=' * 72}\n  AVISO AO ESTUDANTE  [{aviso.tipo}]  "
                  f"t={aviso.em:.1f} s\n  \"{texto}\"\n{'=' * 72}{RESET}\n")

    # -- silencio ------------------------------------------------------------
    def _vigiar_silencio(self):
        limite = self.cfg.get("silencio_s", 6)
        while not self.parar.wait(1):
            with self.trava:
                if (self.ultimo_hb_real and not self.em_silencio
                        and not self.sessao.encerrada
                        and time.time() - self.ultimo_hb_real > limite):
                    self.em_silencio = True
                    self._linha(MAGENTA, "SILENCIO",
                                f"nenhum heartbeat ha {limite} s - rede, bateria ou app. "
                                f"Nada e decidido sem dado; o que chegar depois entra no passado")

    # -- saida ---------------------------------------------------------------
    def _linha(self, cor, rotulo, texto):
        agora = datetime.now().strftime("%H:%M:%S")
        print(f"{CINZA}{agora}{RESET} {cor}{rotulo:<14}{RESET} {texto}")

    def _mostrar(self, dado, t, classe, pos, r, mudou):
        rssi = " ".join(
            a["id"][-1] + ("  --" if a["rssi"] is None else f"{a['rssi']:5.0f}")
            for a in dado["ancoras"])
        onde = "sem posicao" if pos is None else f"({pos[0]:5.1f},{pos[1]:5.1f})"
        cor = COR_ESTADO.get(r.estado, RESET)
        self._linha(cor, f"t={t:6.1f}s",
                    f"seq={dado['sequence']:<4} {rssi}  {dado['state']:<14} "
                    f"{onde} {classe:<6} -> {r.estado:<17} "
                    f"acum {r.acumulado_s:5.1f}s ({r.percentual(self.p):4.1f}%) "
                    f"orc {r.orcamento_restante_s:4.1f}s")
        if mudou and r.transicoes:
            tt, de, para, porque = r.transicoes[-1]
            print(f"{cor}{NEGRITO}      >>> {de} -> {para} em t={tt:.1f} s ({porque}){RESET}")

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
        print(f"\n{CIANO}{NEGRITO}=== sessao {self.sessao.id} aberta ==={RESET}")
        print(f"{CINZA}escala 1:{p.escala:.0f}  aula {p.duracao_aula:.0f} s  "
              f"persistencia {p.persistencia:.0f} s  orcamento {p.orcamento:.0f} s  "
              f"avisos em {p.aviso_1:.0f} s e {p.aviso_2:.0f} s  "
              f"requalificacao {p.requalificacao:.0f} s{RESET}\n")

    def painel(self, final=False):
        s, r = self.sessao, self.sessao.ultimo_resultado
        c = s.contagem
        titulo = "RELATORIO FINAL DA SESSAO" if final else "painel da sessao"
        print(f"\n{CIANO}{'-' * 72}\n  {titulo} {s.id}")
        if r:
            situacao = ("APROVADO na aula" if r.acumulado_s >= self.p.presenca_minima * self.p.duracao_aula
                        else "abaixo do minimo")
            print(f"  estado: {r.estado}   t={r.agora:.1f} s de {self.p.duracao_aula:.0f} s")
            print(f"  acumulado garantido: {r.acumulado_s:.1f} s ({r.percentual(self.p):.1f}%)"
                  f"   provisorio: {r.provisorio_s:.1f} s"
                  + (f"   -> {situacao} (minimo {self.p.presenca_minima:.0%})" if final else ""))
            print(f"  presenca confirmada {r.presenca_s:.1f} s + ausencia creditada "
                  f"{r.ausencia_creditada_s:.1f} s   orcamento usado {r.ausencia_usada_s:.1f} "
                  f"de {self.p.orcamento:.0f} s")
            print(f"  contador ingenuo (ao vivo, sem dedup): {s.ingenuo_s:.1f} s")
            for tt, de, para, porque in r.transicoes:
                print(f"    t={tt:6.1f}s  {de} -> {para}  ({porque})")
        print(f"  aceitos={c['aceitos']} duplicados={c['duplicados']} "
              f"fora de ordem={c['fora_de_ordem']} saltos={c['saltos']} "
              f"({c['perdidos']} perdidos) atrasados={c['atrasados']} invalidos={c['invalidos']}")
        print(f"{'-' * 72}{RESET}\n")

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
                    self.sessao = Sessao()
                    self._cabecalho_sessao()
                elif t:
                    print(f"{CINZA}comandos: p (painel) | n (nova sessao) | q (sair){RESET}")

    def executar(self):
        print(f"\n{CIANO}=== Presenca / servidor de permanencia ==={RESET}")
        print(f"{CINZA}p painel | n nova sessao | q sair{RESET}")
        self.cliente.connect(self.cfg["broker"], self.porta, 60)
        self.cliente.loop_start()
        threading.Thread(target=self._laco_teclado, daemon=True).start()
        threading.Thread(target=self._vigiar_silencio, daemon=True).start()
        try:
            while not self.parar.wait(self.cfg.get("intervalo_painel_s", 30)):
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
