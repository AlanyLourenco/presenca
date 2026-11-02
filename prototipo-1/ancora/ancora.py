#!/usr/bin/env python3
"""
Projeto Presenca - Prototipo 1
ANCORA: o notebook vira um farol Bluetooth Low Energy.

Como as ancoras ESP32 do projeto, ele so TRANSMITE e nunca escuta: anuncia
um identificador e um token que se renova a cada TOKEN_S segundos. Quem mede
a intensidade do sinal (RSSI) e o celular do estudante. O notebook nunca
sabe quem esta perto.

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
import secrets
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

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EMPRESA = 0xFFFF            # reservado para testes
PREFIXO = b"PRS1"           # o app so considera anuncios com este prefixo
ANCORA = 1                  # numero desta ancora (o app mostra "anc-pc-1")
TOKEN_S = 12                # o projeto pede de 10 a 15 s

NOME_STATUS = {
    Status.CREATED: "criado", Status.WAITING: "esperando o rádio",
    Status.STARTED: "TRANSMITINDO", Status.STOPPING: "parando",
    Status.STOPPED: "parado", Status.ABORTED: "interrompido (Bluetooth desligado?)",
}


def novo_publicador(token):
    escritor = DataWriter()
    escritor.write_bytes(PREFIXO + bytes([ANCORA]) + token)
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

    print("══ Presença · protótipo 1 · âncora (este notebook) ══")
    print(f"Anunciando por Bluetooth como anc-pc-{ANCORA}. Token novo a cada {TOKEN_S} s.")
    print("Deixe esta janela aberta. Ctrl+C para parar.\n")

    pub = None
    ultimo_status = None
    try:
        while True:
            token = secrets.token_bytes(4)
            if pub is not None:
                pub.stop()
            pub = novo_publicador(token)
            pub.start()
            inicio = time.time()
            print(f"{time.strftime('%H:%M:%S')}  token {token.hex()}")
            while time.time() - inicio < TOKEN_S:
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
