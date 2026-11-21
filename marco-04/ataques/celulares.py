#!/usr/bin/env python3
"""
Projeto Presenca - Marco 4
CELULARES SIMULADOS: o fluxo completo, ponta a ponta, pelo broker de verdade.

Cada celular simulado tem a PROPRIA chave Ed25519 e faz o que o app faz:
  - manda o cadastro (nome) uma vez, RETIDO no broker (o servidor recebe mesmo
    se so ligar depois)
  - a cada 5 s manda o heartbeat v3 (com o token atual da ancora) e o sensor
    (acelerometro + bateria), tudo assinado
  - escuta o estado e os avisos do servidor (confere a assinatura)
  - escuta os COMANDOS do atuador, executa (imprime) e CONFIRMA assinado

Roteiro de cada celular (tempos em segundos desde o inicio):
  celular 1: sempre na sala, mexendo                      -> presente
  celular 2: sai aos 30 s, volta aos 60 s, celular parado -> presente com
             tolerancia; aparece "celular parado" no relatorio
  celular 3: sai aos 20 s e nao volta                     -> falta
  celular 4+: como o 1

Uso (o servidor rodando em outro terminal):
    python celulares.py 2 --ws              # 2 celulares, aula de 2 min
    python celulares.py 3 --turma ABC234 --ws
    python celulares.py 1 --bateria-acaba 40 --ws   # bateria "acaba" aos 40 s
    python celulares.py --limpar --ws       # apaga do broker cadastros simulados que sobraram

Junto com um celular de verdade: use --turma com o CODIGO da turma do app. Se o
professor ja tocou em "Iniciar aula agora", o simulado entra NA MESMA AULA (le a
turma retida no broker) e fica ate ela acabar; os dois saem juntos no relatorio.
    python celulares.py 1 --turma ABC234 --ws

No fim, cada celular simulado apaga o proprio cadastro retido (senao o
"Aluno Simulado" reapareceria toda vez que o servidor ligasse).
"""

import argparse
import json
import os
import sys
import threading
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "servidor"))
sys.path.insert(0, AQUI)
from seguranca import (  # noqa: E402
    abrir_envelope, chave_do_servidor, envelopar, identidade_da_chave, janela, publica_hex,
    token_da_ancora,
)
from ataques import BASE, SALA, cloud, conectar, escutar, seg  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

INTERVALO_S = 5
VERDE, AMARELO, CIANO, MAGENTA, CINZA, RESET = "\033[32m", "\033[33m", "\033[36m", "\033[35m", "\033[90m", "\033[0m"
T = {n: f"{BASE}/{SALA}/{n}" for n in ("heartbeat", "sensor", "estado", "aviso", "comando", "comando-ack")}
T_CADASTRO = f"{BASE}/cadastro"


class Celular:
    def __init__(self, n, turma, aula, segredo, bateria_acaba=None):
        self.n = n
        self.chave = Ed25519PrivateKey.generate()
        self.aluno, self.device = identidade_da_chave(publica_hex(self.chave))
        self.boot = f"{(n * 4099) & 0xffff:04x}"
        self.turma, self.aula, self.segredo = turma, aula, segredo
        self.seq = 0
        self.bateria_acaba = bateria_acaba

    def na_sala(self, t):
        if self.n == 2:
            return not (30 <= t < 60)
        if self.n == 3:
            return t < 20
        return True

    def assinar(self, topico, dado):
        return envelopar(self.chave, self.aluno, topico, dado)

    def heartbeat(self, t):
        self.seq += 1
        dentro = self.na_sala(t)
        rssi = -55.0 if dentro else None
        tok = token_da_ancora(self.segredo, "anc-pc-1", janela()) if dentro else None
        return {
            "eventType": "presenca.heartbeat.v3", "eventId": f"{self.device}#{self.boot}#{self.seq}",
            "deviceId": self.device, "entityId": SALA, "aluno": self.aluno, "turma": self.turma,
            "aulaId": self.aula, "bootId": self.boot, "eventTimeMs": int(t * 1000),
            "medidoEmMs": int(time.time() * 1000), "sequence": self.seq,
            "value": rssi, "unit": "dBm", "state": "DENTRO_ALCANCE" if dentro else "FORA_ALCANCE",
            "ancoras": [{"id": "anc-pc-1", "rssi": rssi, "token": tok}],
            "amostrasInvalidas": 0, "bufferizado": False, "anomaliaInjetada": "nenhuma",
        }

    def sensor(self, t):
        parado = self.n == 2
        nivel = max(0.02, 0.81 - t / 400)
        if self.bateria_acaba and t >= self.bateria_acaba - 10:
            nivel = 0.03
        return {
            "eventType": "presenca.sensor.v1", "sensorId": f"{self.device}#{self.boot}#{self.seq}",
            "aluno": self.aluno, "deviceId": self.device, "turma": self.turma,
            "medidoEmMs": int(time.time() * 1000),
            "acelerometro": {"movimento": 0.002 if parado else 0.06, "amostras": 50, "parado": parado},
            "bateria": {"nivel": round(nivel, 2), "carregando": False},
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int, nargs="?", default=2)
    ap.add_argument("--turma", default="SIM234")
    ap.add_argument("--tempo", type=int, default=130, help="segundos (a aula de demonstração tem 120)")
    ap.add_argument("--bateria-acaba", type=int, default=None, help="o celular 1 para de mandar neste segundo")
    ap.add_argument("--ws", action="store_true")
    ap.add_argument("--limpar", action="store_true", help="só apaga cadastros simulados retidos")
    a = ap.parse_args()
    if a.limpar:
        return limpar()

    s = seg()
    segredo = s["ancoras"]["anc-pc-1"]
    chave_srv = publica_hex(chave_do_servidor(os.path.join(RAIZ, "servidor", "chave-servidor.pem")))
    cli = cloud("app")
    trava = threading.Lock()
    ok, motivo = conectar(cli)
    if not ok:
        raise SystemExit(f"Não conectou: {motivo}")

    # A aula que o professor iniciou no app (turma retida), se houver: entra nela.
    aula, tempo = f"demo-{int(time.time() * 1000)}", a.tempo
    for _, texto, _ in escutar(cli, f"{BASE}/turma/{a.turma}", 3, parar_em=lambda m: True):
        try:
            agora_aula = abrir_envelope(f"{BASE}/turma/{a.turma}", texto)[2].get("aulaAgora")
        except Exception:  # noqa: BLE001
            agora_aula = None
        if agora_aula:
            fim_ms = agora_aula["inicioMs"] + agora_aula["duracaoS"] * 1000
            if fim_ms > time.time() * 1000:
                aula = f"demo-{agora_aula['inicioMs']}"
                tempo = min(a.tempo, int(fim_ms / 1000 - time.time()) + 10)
                print(f"{CIANO}Entrando na aula que o professor iniciou: {aula} (faltam {tempo - 10} s){RESET}")
    cels = [Celular(i + 1, a.turma, aula, segredo, a.bateria_acaba if i == 0 else None) for i in range(a.n)]
    por_aluno = {c.aluno: c for c in cels}

    def ao_receber(_c, _u, msg):
        try:
            de, chave, dado = abrir_envelope(msg.topic, msg.payload.decode())
        except Exception:  # noqa: BLE001
            return
        aluno = msg.topic.rsplit("/", 1)[-1]
        c = por_aluno.get(aluno)
        if c is None or chave != chave_srv and "/comando/" not in msg.topic:
            return
        with trava:
            if "/estado/" in msg.topic:
                print(f"{CINZA}  celular {c.n} ← estado: {dado['estado']}, {dado['percentual']} %{RESET}")
            elif "/aviso/" in msg.topic:
                print(f"{AMARELO}  celular {c.n} ← AVISO: {dado['texto']}{RESET}")
            elif "/comando/" in msg.topic:
                quem = "servidor" if chave == chave_srv else "professor (admin)"
                print(f"{MAGENTA}  celular {c.n} ← COMANDO de {quem}: {dado['tipo']} — \"{dado['texto']}\" "
                      f"→ vibrou{RESET}")
                ack_t = f"{T['comando-ack']}/{c.aluno}"
                ack = {"eventType": "presenca.comando.ack.v1", "comandoId": dado["comandoId"], "aluno": c.aluno,
                       "resultado": "executado", "emMs": int(time.time() * 1000), "detalhe": "simulado: vibrou"}
                cli.publish(ack_t, c.assinar(ack_t, ack), qos=1)
                if dado["tipo"] == "chamar":
                    def responder():
                        time.sleep(2)
                        r = {**ack, "resultado": "respondido", "detalhe": "simulado: tocou em Estou aqui",
                             "emMs": int(time.time() * 1000)}
                        cli.publish(ack_t, c.assinar(ack_t, r), qos=1)
                        print(f"{MAGENTA}  celular {c.n} → \"Estou aqui\"{RESET}")
                    threading.Thread(target=responder, daemon=True).start()

    cli.on_message = ao_receber
    for c in cels:
        for nome in ("estado", "aviso", "comando"):
            cli.subscribe(f"{T[nome]}/{c.aluno}", qos=1)
    cli.loop_start()
    time.sleep(1)

    print(f"{CIANO}══ {a.n} celular(es) simulado(s) · turma {a.turma} · aula {aula} ══{RESET}")
    for c in cels:
        cad = {"eventType": "presenca.cadastro.v1", "aluno": c.aluno, "turma": a.turma,
               "nome": f"Aluno Simulado {c.n}", "matricula": f"20260{c.n:04d}", "emMs": int(time.time() * 1000)}
        t_cad = f"{T_CADASTRO}/{c.aluno}"
        cli.publish(t_cad, c.assinar(t_cad, cad), qos=1, retain=True)
        print(f"  celular {c.n} = {c.aluno} ({cad['nome']})")

    inicio = time.time()
    while (t := time.time() - inicio) < tempo:
        for c in cels:
            if c.bateria_acaba and t >= c.bateria_acaba:
                continue                                   # bateria acabou: silêncio
            hb = c.heartbeat(t)
            cli.publish(T["heartbeat"], c.assinar(T["heartbeat"], hb), qos=0)
            sn = c.sensor(t)
            cli.publish(T["sensor"], c.assinar(T["sensor"], sn), qos=0)
        with trava:
            print(f"{VERDE}  {t:5.0f} s  →  " + "  ".join(
                f"cel {c.n}: {'na sala' if c.na_sala(t) else 'fora'}" for c in cels) + RESET)
        time.sleep(max(0, INTERVALO_S - ((time.time() - inicio) % INTERVALO_S)))
    for c in cels:                                         # nao deixa lixo retido no broker
        cli.publish(f"{T_CADASTRO}/{c.aluno}", b"", qos=1, retain=True)
    time.sleep(1)
    cli.loop_stop()
    cli.disconnect()
    print(f"{CIANO}Fim. Relatório: http://127.0.0.1:8090/api/turmas/{a.turma}/relatorio.csv{RESET}")


def limpar():
    """Apaga os cadastros retidos de 'Aluno Simulado N'. Os de alunos de verdade ficam."""
    cli = cloud("app")
    ok, motivo = conectar(cli)
    if not ok:
        raise SystemExit(f"Não conectou: {motivo}")
    apagados = 0
    for topico, texto, retido in escutar(cli, f"{T_CADASTRO}/+", 4):
        try:
            _, _, dado = abrir_envelope(topico, texto)
        except Exception:  # noqa: BLE001
            continue
        if retido and str(dado.get("nome", "")).startswith("Aluno Simulado"):
            cli.publish(topico, b"", qos=1, retain=True)
            apagados += 1
            print(f"  apagado: {dado['nome']} ({dado['aluno']})")
    time.sleep(1)
    cli.loop_stop()
    cli.disconnect()
    print(f"{CIANO}{apagados} cadastro(s) simulado(s) apagado(s) do broker.{RESET}")


if __name__ == "__main__":
    main()
