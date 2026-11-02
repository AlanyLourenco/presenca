#!/usr/bin/env python3
"""
Projeto Presenca - Marco 3
SONDA: quantas mensagens por segundo o broker entrega de UMA conexao para outra?

Sem servidor no meio: um cliente publica TAXA mensagens/s num topico de teste e
outro conta quantas chegam. Foi assim que se achou o limite de ~11 msg/s por
conexao do EMQX Cloud Serverless gratuito.

    python sonda.py          # 60 msg/s por 10 s
    python sonda.py 20       # 20 msg/s
"""

import sys
import time

from ataques import BASE, cloud, conectar

TOPICO = f"{BASE}/sonda"
DURACAO_S = 10


def main():
    taxa = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else 60
    recebidos = []
    pub, sub = cloud(), cloud()
    for c in (pub, sub):
        ok, motivo = conectar(c)
        if not ok:
            sys.exit(f"não conectou: {motivo}")
    sub.on_message = lambda c, u, msg: recebidos.append(time.time())
    sub.subscribe(TOPICO, qos=0)
    time.sleep(1)
    inicio, n = time.time(), 0
    while time.time() - inicio < DURACAO_S:
        pub.publish(TOPICO, "x" * 900, qos=0)
        n += 1
        time.sleep(max(0, inicio + n / taxa - time.time()))
    time.sleep(5)
    dentro = [t for t in recebidos if t - inicio <= DURACAO_S]
    print(f"enviadas {n} ({n / DURACAO_S:.0f}/s) · recebidas {len(recebidos)} · "
          f"nos {DURACAO_S} s: {len(dentro) / DURACAO_S:.1f}/s")
    for c in (pub, sub):
        c.loop_stop()
        c.disconnect()


if __name__ == "__main__":
    main()
