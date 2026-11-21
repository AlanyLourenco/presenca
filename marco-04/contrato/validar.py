#!/usr/bin/env python3
"""
Valida os exemplos do contrato contra os schemas.

    python validar.py                 # todos os exemplos de v1/exemplos/
    python validar.py arquivo.json    # um arquivo qualquer

O schema e escolhido pelo campo eventType (ou commandType) da mensagem.
No fim, mostra de proposito um heartbeat com um campo a mais sendo
rejeitado - e o que o servidor faz com uma mensagem assim.
"""

import glob
import json
import os
import sys

from jsonschema import Draft202012Validator

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.join(AQUI, "v1")


def validador(tipo):
    caminho = os.path.join(V1, f"{tipo}.schema.json")
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))


def checar(nome, msg):
    tipo = msg.get("eventType") or msg.get("commandType")
    v = validador(tipo) if tipo else None
    if v is None:
        print(f"  ??  {nome:<34} tipo desconhecido: {tipo!r}")
        return False
    erros = sorted(v.iter_errors(msg), key=lambda e: list(e.path))
    if erros:
        campo = ".".join(str(p) for p in erros[0].path) or "(raiz)"
        print(f"  NAO {nome:<34} {tipo} -> {campo}: {erros[0].message}")
        return False
    print(f"  OK  {nome:<34} {tipo}")
    return True


def main():
    arquivos = sys.argv[1:] or sorted(glob.glob(os.path.join(V1, "exemplos", "*.json")))
    print(f"\nValidando {len(arquivos)} mensagem(ns) contra contrato/v1/\n")
    ok = all([checar(os.path.basename(a), json.load(open(a, encoding="utf-8"))) for a in arquivos])

    if not sys.argv[1:]:
        print("\nAgora de proposito: o mesmo heartbeat com um campo que o contrato nao preve\n")
        with open(os.path.join(V1, "exemplos", "heartbeat-dentro.json"), encoding="utf-8") as f:
            hb = json.load(f)
        hb["bateria"] = 63
        checar("heartbeat-com-bateria (inventado)", hb)
        print("\n  -> o servidor faz o mesmo: responde INVALIDO e descarta. Para aceitar")
        print("     'bateria' seria preciso criar presenca.heartbeat.v2.\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
