#!/usr/bin/env python3
"""
Projeto Presenca - Marco 3
ATAQUES: o que um intruso consegue (e o que nao consegue) contra o sistema.

Cada cenario diz o que o atacante tenta, roda a tentativa de verdade contra
o broker e diz onde olhar o resultado (este terminal, o do servidor ou o
celular). Use com o servidor e o app rodando.

    python ataques.py publico     # broker.hivemq.com: sem senha, le tudo
    python ataques.py senha       # EMQX Cloud: sem TLS / sem senha / senha errada
    python ataques.py forjar      # com a senha do app vazada: tenta se passar por alguem
    python ataques.py repetir     # captura um heartbeat de verdade e reenvia depois
    python ataques.py estado      # manda "PRESENTE 100 %" falso para o celular
    python ataques.py turma       # publica uma turma falsa com limiar -100 dBm
    python ataques.py todos       # senha, forjar, estado e turma em sequencia

--ws usa WebSocket com TLS (porta 8084 no EMQX), para a rede da faculdade.
"""

import json
import os
import socket
import ssl
import sys
import threading
import time

import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "servidor"))
from seguranca import carregar_segredos, envelopar, identidade_da_chave, publica_hex  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VERDE, AMARELO, VERMELHO, CIANO, CINZA, NEGRITO, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[90m", "\033[1m", "\033[0m")

BASE = "ufg/ssu/presenca/alany/m3"
SALA = "sala-pc"
T_HEARTBEAT = f"{BASE}/{SALA}/heartbeat"
WS = "--ws" in sys.argv


def titulo(t):
    print(f"\n{CIANO}{NEGRITO}══ {t} ══{RESET}")


def tenta(t):
    print(f"{AMARELO}  atacante tenta:{RESET} {t}")


def resultado(ok_para_o_atacante, t):
    cor = VERMELHO if ok_para_o_atacante else VERDE
    marca = "CONSEGUIU" if ok_para_o_atacante else "BLOQUEADO"
    print(f"  {cor}{NEGRITO}{marca}{RESET} {t}")


def olhe(t):
    print(f"{CINZA}  onde olhar: {t}{RESET}")


# ---------------------------------------------------------------------------
def cliente(host, porta, tls, usuario=None, senha=None, ws=WS):
    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                        client_id=f"intruso-{os.getpid()}-{time.time_ns() % 10**6}",
                        transport="websockets" if ws else "tcp")
    except (AttributeError, TypeError):
        c = mqtt.Client(client_id=f"intruso-{os.getpid()}", transport="websockets" if ws else "tcp")
    if tls:
        c.tls_set()
    if ws:
        c.ws_set_options(path="/mqtt")
    if usuario is not None:
        c.username_pw_set(usuario, senha)
    resposta = {}
    pronto = threading.Event()

    def ao_conectar(cli, ud, flags, rc, props=None):
        resposta["rc"] = rc
        pronto.set()

    c.on_connect = ao_conectar
    c._presenca_host = (host, porta)
    c._presenca_pronto = pronto
    c._presenca_resposta = resposta
    return c


def conectar(c, espera=8):
    """Devolve (conectou?, texto do motivo)."""
    host, porta = c._presenca_host
    try:
        c.connect(host, porta, 30)
    except (OSError, ssl.SSLError, socket.timeout) as e:
        return False, (f"a conexão nem abriu ({type(e).__name__}). Ou o broker não atende nesta "
                       f"porta, ou a REDE bloqueia a porta {porta} (rede da faculdade: use o hotspot do celular)")
    c.loop_start()
    if not c._presenca_pronto.wait(espera):
        c.loop_stop()
        return False, "o broker não respondeu (fechou a conexão)"
    rc = c._presenca_resposta["rc"]
    if rc != 0:
        c.loop_stop()
        return False, f"o broker recusou: {rc}"
    return True, "conectado"


def seg():
    return carregar_segredos(os.path.join(RAIZ, "segredos.json"))


def cloud(papel="app"):
    s = seg()
    porta = s["porta_wss"] if WS else s["porta_tls"]
    return cliente(s["broker"], porta, True, s[papel]["usuario"], s[papel]["senha"])


def escutar(c, filtro, segundos, parar_em=None):
    """Assina e junta [(topico, texto)] por alguns segundos."""
    vistos = []
    chegou = threading.Event()

    def ao_receber(cli, ud, msg):
        vistos.append((msg.topic, msg.payload.decode("utf-8", "replace"), msg.retain))
        if parar_em and parar_em(msg):
            chegou.set()

    c.on_message = ao_receber
    c.subscribe(filtro, qos=1)
    chegou.wait(segundos)
    c.unsubscribe(filtro)
    return vistos


def descobrir_aluno(c, segundos=15):
    """O atacante com a senha do app escuta o heartbeat e acha um pseudonimo."""
    print(f"{CINZA}  (escutando {T_HEARTBEAT} por até {segundos} s para achar um aluno…){RESET}")
    vistos = escutar(c, T_HEARTBEAT, segundos, parar_em=lambda m: True)
    for _, texto, _ in vistos:
        try:
            env = json.loads(texto)
            carga = json.loads(env["carga"])
            return carga["aluno"], carga["deviceId"], texto, carga
        except (ValueError, KeyError, TypeError):
            continue
    return None, None, None, None


def heartbeat_falso(aluno, device, seq, token="00000000", rssi=-45.0):
    return {
        "eventType": "presenca.heartbeat.v2",
        "eventId": f"{device}#dead#{seq}",
        "deviceId": device, "entityId": SALA, "aluno": aluno, "bootId": "dead",
        "eventTimeMs": seq * 500, "medidoEmMs": int(time.time() * 1000), "sequence": seq,
        "value": rssi, "unit": "dBm", "state": "DENTRO_ALCANCE",
        "ancoras": [{"id": "anc-pc-1", "rssi": rssi, "token": token}],
        "amostrasInvalidas": 0, "bufferizado": False, "anomaliaInjetada": "nenhuma",
    }


# ---------------------------------------------------------------------------
def cenario_publico():
    titulo("1. Broker PÚBLICO (broker.hivemq.com) — como era até o Marco 2")
    porta = 8884 if WS else 1883
    tenta(f"conectar em broker.hivemq.com:{porta} SEM usuário e SEM senha")
    c = cliente("broker.hivemq.com", porta, WS)
    ok, motivo = conectar(c)
    resultado(ok, f"— {motivo}")
    if not ok:
        return
    tenta("assinar ufg/ssu/presenca/# e PUBLICAR um heartbeat falso lá dentro, sem senha")
    alvo = "ufg/ssu/presenca/alany/proto1/sala-pc/heartbeat"
    falso = json.dumps({"eventType": "presenca.heartbeat.v1", "aluno": "tok-intruso",
                        "state": "DENTRO_ALCANCE", "nota": "publicado sem senha pelo ataques.py"})
    threading.Timer(1.5, lambda: c.publish(alvo, falso, qos=1)).start()
    vistos = escutar(c, "ufg/ssu/presenca/#", 8)
    meu = [v for v in vistos if "tok-intruso" in v[1]]
    resultado(bool(meu), f"— publicou em {alvo} e o broker entregou de volta: escrever e ler, sem senha")
    outros = [v for v in vistos if "tok-intruso" not in v[1]]
    print(f"  leu também {len(outros)} mensagem(ns) de terceiros nesses 8 s")
    for t, texto, ret in outros[:4]:
        print(f"{CINZA}     {t}{' (retida)' if ret else ''}: {texto[:100]}{RESET}")
    print(f"  {AMARELO}Qualquer pessoa no mundo pode ler e também PUBLICAR nesses tópicos.{RESET}")
    c.disconnect()


def cenario_senha():
    titulo("2. EMQX Cloud — sem TLS, sem senha, senha errada")
    s = seg()
    host = s["broker"]

    tenta(f"MQTT aberto, sem TLS, em {host}:1883")
    c = cliente(host, 1883, False, ws=False)
    ok, motivo = conectar(c, espera=6)
    resultado(ok, f"— {motivo}")

    porta = s["porta_wss"] if WS else s["porta_tls"]
    tenta(f"TLS na porta {porta}, mas SEM usuário e senha")
    c = cliente(host, porta, True)
    ok, motivo = conectar(c)
    resultado(ok, f"— {motivo}")

    tenta(f"TLS com o usuário {s['app']['usuario']} e senha ERRADA")
    c = cliente(host, porta, True, s["app"]["usuario"], "chute123")
    ok, motivo = conectar(c)
    resultado(ok, f"— {motivo}")

    tenta("TLS com usuário e senha certos (para comparar)")
    c = cloud()
    ok, motivo = conectar(c)
    print(f"  {'CONECTOU' if ok else 'FALHOU'} — {motivo}")
    if ok:
        c.disconnect()


def cenario_forjar():
    titulo("3. Senha do app VAZADA — tentar falar em nome de outro aluno")
    print(f"{CINZA}  A senha do papel 'app' está dentro do APK: quem descompilar consegue.\n"
          f"  Por isso a segurança não pode parar no broker.{RESET}")
    c = cloud()
    ok, motivo = conectar(c)
    if not ok:
        print(f"  não conectou: {motivo}")
        return
    aluno, device, _, _ = descobrir_aluno(c)
    if not aluno:
        aluno, device = "tok-12345678", "cel-1234"
        print(f"{CINZA}  nenhum heartbeat no ar; usando um pseudônimo inventado: {aluno}{RESET}")
    else:
        print(f"  achou o aluno {NEGRITO}{aluno}{RESET} escutando o tópico")

    intrusa = Ed25519PrivateKey.generate()
    eu, meu_device = identidade_da_chave(publica_hex(intrusa))

    tenta(f"a) heartbeat SEM assinatura dizendo que {aluno} está na sala")
    c.publish(T_HEARTBEAT, json.dumps(heartbeat_falso(aluno, device, 1)), qos=1)
    olhe("terminal do servidor → x RECUSADA  SEM ASSINATURA")
    time.sleep(1)

    tenta(f"b) heartbeat ASSINADO com a chave do atacante, mas dizendo ser {aluno}")
    c.publish(T_HEARTBEAT, envelopar(intrusa, aluno, T_HEARTBEAT, heartbeat_falso(aluno, device, 2)), qos=1)
    olhe(f"servidor → x RECUSADA  IDENTIDADE TROCADA (a chave é de {eu}, não de {aluno})")
    time.sleep(1)

    tenta(f"c) heartbeat assinado como ele mesmo ({eu}), de casa, com token inventado")
    c.publish(T_HEARTBEAT, envelopar(intrusa, eu, T_HEARTBEAT,
                                     heartbeat_falso(eu, meu_device, 3, token="1a2b3c4d")), qos=1)
    olhe("servidor → x RECUSADA  TOKEN VENCIDO (não ouviu a âncora)")
    time.sleep(1)
    c.loop_stop()
    c.disconnect()


def cenario_repetir():
    titulo("4. Repetir (replay) um heartbeat VERDADEIRO capturado no ar")
    c = cloud()
    ok, motivo = conectar(c)
    if not ok:
        print(f"  não conectou: {motivo}")
        return
    aluno, _, texto, carga = descobrir_aluno(c, 30)
    if not texto:
        print("  nenhum heartbeat no ar: deixe o celular em aula e rode de novo.")
        return
    print(f"  capturou o heartbeat nº {carga['sequence']} de {aluno} (assinatura válida)")
    tenta("reenviar a MESMA mensagem agora")
    c.publish(T_HEARTBEAT, texto, qos=1)
    olhe("servidor → ! REPETIDA (o eventId já foi visto; não soma tempo)")
    espera = 40
    print(f"{CINZA}  esperando {espera} s para o token da âncora vencer…{RESET}")
    time.sleep(espera)
    tenta("reenviar de novo, 40 s depois (o aluno já foi embora, quer parecer presente)")
    c.publish(T_HEARTBEAT, texto, qos=1)
    olhe("servidor → ! REPETIDA ou x RECUSADA TOKEN VENCIDO. Alterar o nº para escapar quebra a assinatura.")
    time.sleep(1)
    c.loop_stop()
    c.disconnect()


def cenario_estado():
    titulo("5. Mandar ao celular um estado FALSO: 'PRESENTE, 100 %'")
    c = cloud()
    ok, motivo = conectar(c)
    if not ok:
        print(f"  não conectou: {motivo}")
        return
    aluno, _, _, _ = descobrir_aluno(c)
    if not aluno:
        print("  nenhum heartbeat no ar: deixe o celular em aula e rode de novo.")
        return
    topico = f"{BASE}/{SALA}/estado/{aluno}"
    falso = {"eventType": "presenca.estado.v1", "estadoId": "srv-204#999999", "aluno": aluno,
             "entityId": SALA, "estado": "PRESENTE", "acumuladoS": 3000, "provisorioS": 0,
             "percentual": 100, "orcamentoRestanteS": 900, "tempoAulaS": 3000, "classe": "dentro",
             "posicao": None, "dentroPoligono": None, "encerrada": False,
             "emitidoEmMs": int(time.time() * 1000)}
    tenta("a) estado sem assinatura")
    c.publish(topico, json.dumps(falso), qos=1)
    time.sleep(1)
    tenta("b) estado assinado com a chave do atacante, dizendo ser 'servidor'")
    c.publish(topico, envelopar(Ed25519PrivateKey.generate(), "servidor", topico, falso), qos=1)
    olhe("celular → cartão Segurança: 'Recusei 2 mensagem(ns) falsa(s)'. A tela NÃO mostra 100 %.")
    time.sleep(1)
    c.loop_stop()
    c.disconnect()


def cenario_turma():
    titulo("6. Turma FALSA: limiar de 1 m em −100 dBm (todo mundo 'perto', até de casa)")
    c = cloud()
    ok, motivo = conectar(c)
    if not ok:
        print(f"  não conectou: {motivo}")
        return
    vistos = escutar(c, f"{BASE}/turma/+", 5)
    alvo = None
    for t, texto, _ in vistos:
        try:
            alvo = json.loads(json.loads(texto)["carga"])
            break
        except (ValueError, KeyError, TypeError):
            continue
    if not alvo:
        print("  nenhuma turma publicada: publique uma no app (admin) e rode de novo.")
        return
    print(f"  achou a turma {alvo['codigo']} ({alvo['nome']}), limiar {alvo.get('limiar1mDbm')} dBm")
    falsa = dict(alvo, limiar1mDbm=-100, publicadoEmMs=int(time.time() * 1000))
    topico = f"{BASE}/turma/{alvo['codigo']}"
    tenta("publicar a turma com limiar −100 dBm, assinada pela chave do atacante")
    # Nao fica retida: para nao estragar a turma de verdade depois da demonstracao.
    c.publish(topico, envelopar(Ed25519PrivateKey.generate(), "admin", topico, falsa), qos=1)
    olhe("celular (tela da turma) → 'Turma recusada: turma assinada por outro administrador'")
    time.sleep(1)
    c.loop_stop()
    c.disconnect()


CENARIOS = {"publico": cenario_publico, "senha": cenario_senha, "forjar": cenario_forjar,
            "repetir": cenario_repetir, "estado": cenario_estado, "turma": cenario_turma}

if __name__ == "__main__":
    pedidos = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not pedidos:
        print(__doc__)
        sys.exit(0)
    if pedidos == ["todos"]:
        pedidos = ["senha", "forjar", "estado", "turma"]
    for p in pedidos:
        if p not in CENARIOS:
            sys.exit(f"cenário desconhecido: {p}. Opções: {', '.join(CENARIOS)} ou todos")
        CENARIOS[p]()
    print()
