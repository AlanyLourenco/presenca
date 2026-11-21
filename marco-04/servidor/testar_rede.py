#!/usr/bin/env python3
"""
Diz se esta rede alcança o broker MQTT e qual comando usar.

    python testar_rede.py

Lê o endereço do broker em ../segredos.json e tenta abrir uma conexão nas
duas portas cifradas do EMQX Cloud:
  8883 - MQTT sobre TLS               -> python servidor.py --tls
  8084 - MQTT sobre WebSocket com TLS -> python servidor.py   (padrão)
Redes que bloqueiam as duas (como algumas de faculdade): use o hotspot do celular.
"""

import json
import os
import socket
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def aberta(host, porta, espera=5):
    try:
        with socket.create_connection((host, porta), espera):
            return True
    except OSError:
        return False


def main():
    caminho = os.path.join(os.path.dirname(AQUI), "segredos.json")
    if not os.path.exists(caminho):
        sys.exit("Falta segredos.json (rode python ../configurar.py).")
    with open(caminho, encoding="utf-8") as f:
        seg = json.load(f)
    host = seg["broker"]
    tls, wss = aberta(host, seg.get("porta_tls", 8883)), aberta(host, seg.get("porta_wss", 8084))
    print(f"Broker {host}")
    print(f"  8883 (MQTT sobre TLS):        {'ABERTA' if tls else 'bloqueada'}")
    print(f"  8084 (WebSocket com TLS):     {'ABERTA' if wss else 'bloqueada'}")
    if wss:
        print("Use: python servidor.py")
    elif tls:
        print("Use: python servidor.py --tls")
    else:
        print("Esta rede bloqueia o broker. Conecte o notebook no hotspot do celular.")


if __name__ == "__main__":
    main()
