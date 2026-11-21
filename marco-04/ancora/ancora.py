#!/usr/bin/env python3
"""
Projeto Presenca - Marco 3
ANCORA: o notebook vira um farol Bluetooth Low Energy.

Como as ancoras ESP32 do projeto, ele so TRANSMITE e nunca escuta: anuncia
um identificador e um token que se renova a cada TOKEN_S segundos. Quem mede
a intensidade do sinal (RSSI) e o celular do estudante. O notebook nunca
sabe quem esta perto.

Marco 3: o token deixou de ser sorteado. E HMAC-SHA256(segredo da ancora,
"anc-pc-1|<janela de 12 s>"), cortado em 4 bytes. So a ancora e o servidor
tem o segredo (segredos.json); o celular so repassa o que ouviu. Assim o
servidor sabe que quem mandou o heartbeat estava ouvindo esta ancora AGORA.

O anuncio leva "manufacturer data" com o codigo de empresa 0xFFFF, que a
especificacao Bluetooth reserva para testes e prototipos:

    50 52 53 31 | 01      | t t t t
    "PRS1"      | ancora  | token (4 bytes, muda a cada TOKEN_S s)

Uso (Windows 10/11, Bluetooth ligado):
    pip install -r requirements.txt
    python ancora.py
Ctrl+C para parar.
"""

import asyncio
import os
import sys
import time

from winrt.windows.devices.bluetooth import BluetoothAdapter
from winrt.windows.devices.bluetooth.advertisement import (
    BluetoothLEAdvertisementPublisher,
    BluetoothLEAdvertisementPublisherStatus as Status,
    BluetoothLEManufacturerData,
)
from winrt.windows.devices.radios import RadioState
from winrt.windows.storage.streams import DataWriter

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "servidor"))
from seguranca import TOKEN_S, carregar_segredos, janela, token_da_ancora  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EMPRESA = 0xFFFF            # reservado para testes
PREFIXO = b"PRS1"           # o app so considera anuncios com este prefixo
ANCORA = 1                  # numero desta ancora (o app mostra "anc-pc-1")
NOME = f"anc-pc-{ANCORA}"

NOME_STATUS = {
    Status.CREATED: "criado", Status.WAITING: "esperando o rádio",
    Status.STARTED: "TRANSMITINDO", Status.STOPPING: "parando",
    Status.STOPPED: "parado", Status.ABORTED: "interrompido (Bluetooth desligado?)",
}


def novo_publicador(token):
    escritor = DataWriter()
    escritor.write_bytes(PREFIXO + bytes([ANCORA]) + bytes.fromhex(token))
    dado = BluetoothLEManufacturerData()
    dado.company_id = EMPRESA
    dado.data = escritor.detach_buffer()
    pub = BluetoothLEAdvertisementPublisher()
    pub.advertisement.manufacturer_data.append(dado)
    return pub


def sair(msg):
    print(msg)           # stdout ja esta em UTF-8; o stderr do Windows nao
    sys.exit(1)


async def principal():
    adaptador = await BluetoothAdapter.get_default_async()
    if adaptador is None:
        sair("Nenhum Bluetooth encontrado. Ligue o Bluetooth do Windows.")
    if not adaptador.is_peripheral_role_supported:
        sair("Este Bluetooth não consegue transmitir como farol (modo periférico).")
    radio = await adaptador.get_radio_async()
    if radio.state != RadioState.ON:
        sair("O Bluetooth do notebook está DESLIGADO. Ligue em Configurações > "
                         "Bluetooth e dispositivos (ou na central de ações) e rode de novo.")

    segredos = carregar_segredos(os.path.join(os.path.dirname(AQUI), "segredos.json"))
    segredo = segredos.get("ancoras", {}).get(NOME)
    if not segredo:
        sair(f"segredos.json não tem o segredo de {NOME}. Rode: python configurar.py")

    print("══ Presença · Marco 3 · âncora (este notebook) ══")
    print(f"Anunciando por Bluetooth como {NOME}. Token novo a cada {TOKEN_S} s, "
          f"assinado com o segredo da âncora (HMAC).")
    print("Deixe esta janela aberta. Ctrl+C para parar.\n")

    pub = None
    ultimo_status = None
    try:
        while True:
            # A janela segue o relogio (como no servidor), nao o momento em que
            # a ancora ligou: os dois calculam o mesmo token sem conversar.
            j = janela()
            token = token_da_ancora(segredo, NOME, j)
            if pub is not None:
                pub.stop()
            pub = novo_publicador(token)
            pub.start()
            print(f"{time.strftime('%H:%M:%S')}  janela {j}  token {token}")
            while janela() == j:
                if pub.status != ultimo_status:
                    ultimo_status = pub.status
                    print(f"           rádio: {NOME_STATUS.get(pub.status, pub.status)}")
                await asyncio.sleep(0.5)
    finally:
        if pub is not None:
            pub.stop()
        print("\nÂncora parada.")


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except KeyboardInterrupt:
        pass
