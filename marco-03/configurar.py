#!/usr/bin/env python3
"""
Prepara os segredos do Marco 3. Rode uma vez (e de novo se trocar uma senha).

    python configurar.py

1. Cria segredos.json a partir do exemplo, se ainda nao existir.
2. Sorteia o segredo de cada ancora (HMAC do token), se faltar.
3. Cria a chave Ed25519 do servidor (servidor/chave-servidor.pem), se faltar.
4. Escreve app/src/lib/segredos.ts: o endereco do broker, a senha do papel
   "app" e a chave PUBLICA do servidor, que o celular usa para conferir que o
   estado e os avisos vieram mesmo do servidor.

Nenhum desses arquivos vai para o git (.gitignore).
"""

import json
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "servidor"))
from seguranca import chave_do_servidor, novo_segredo, publica_hex  # noqa: E402

ANCORAS = ["anc-pc-1"]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    caminho = os.path.join(AQUI, "segredos.json")
    if not os.path.exists(caminho):
        shutil.copy(os.path.join(AQUI, "segredos.exemplo.json"), caminho)
        print("Criei segredos.json. Preencha o endereço e as senhas do EMQX Cloud e rode de novo.")
    with open(caminho, encoding="utf-8") as f:
        seg = json.load(f)

    ancoras = seg.setdefault("ancoras", {})
    for a in ANCORAS:
        if not ancoras.get(a):
            ancoras[a] = novo_segredo()
            print(f"Segredo novo para a âncora {a}.")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(seg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    chave = chave_do_servidor(os.path.join(AQUI, "servidor", "chave-servidor.pem"))
    pub = publica_hex(chave)

    faltando = [n for n, v in (("broker", seg["broker"]), ("senha do servidor", seg["servidor"]["senha"]),
                               ("senha do app", seg["app"]["senha"])) if "COLE-AQUI" in v]

    ts = f"""// GERADO por configurar.py — não edite e não versione (.gitignore).
// Credencial MQTT do papel "app" e chave pública do servidor (Ed25519).
export const BROKER_URL = 'wss://{seg["broker"]}:{seg["porta_wss"]}{seg["caminho_ws"]}';
export const MQTT_USUARIO = {json.dumps(seg["app"]["usuario"])};
export const MQTT_SENHA = {json.dumps(seg["app"]["senha"])};
export const CHAVE_PUBLICA_SERVIDOR = '{pub}';
"""
    with open(os.path.join(AQUI, "app", "src", "lib", "segredos.ts"), "w", encoding="utf-8") as f:
        f.write(ts)

    print(f"Chave pública do servidor: {pub}")
    print("app/src/lib/segredos.ts escrito.")
    if faltando:
        print(f"ATENÇÃO: ainda falta preencher em segredos.json: {', '.join(faltando)}.")
    else:
        print("Tudo pronto. Se o app mudou (ou a chave/senha), gere o APK de novo.")


if __name__ == "__main__":
    main()
