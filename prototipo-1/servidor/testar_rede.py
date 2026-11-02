#!/usr/bin/env python3
"""
Diz se esta rede alcança o broker MQTT, e qual comando usar.

    python testar_rede.py

Funciona em qualquer terminal (Git Bash, PowerShell, cmd). Tenta abrir uma
conexao com o broker nas duas portas:
  1883 - MQTT comum            -> python servidor.py
  8884 - MQTT sobre WebSocket  -> python servidor.py --ws
"""

import socket
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BROKER = "broker.hivemq.com"
VERDE, VERMELHO, RESET = "\033[32m", "\033[31m", "\033[0m"


def alcanca(porta, espera=5):
    try:
        with socket.create_connection((BROKER, porta), timeout=espera):
            return True
    except OSError:
        return False


def main():
    print(f"\nTestando {BROKER} ...\n")
    tcp = alcanca(1883)
    ws = alcanca(8884)
    for porta, ok, nome in ((1883, tcp, "MQTT comum"), (8884, ws, "MQTT sobre WebSocket seguro")):
        cor, txt = (VERDE, "LIBERADA") if ok else (VERMELHO, "BLOQUEADA")
        print(f"  porta {porta} ({nome}): {cor}{txt}{RESET}")

    print()
    if tcp:
        print(f"{VERDE}Use:  python servidor.py{RESET}")
    elif ws:
        print(f"{VERDE}Use:  python servidor.py --ws{RESET}   (a 1883 esta bloqueada nesta rede)")
    else:
        print(f"{VERMELHO}As duas portas estao bloqueadas. Troque para o 4G do celular e rode de novo.{RESET}")
    print()
    sys.exit(0 if (tcp or ws) else 1)


if __name__ == "__main__":
    main()
