#!/usr/bin/env python3
"""
Projeto Presenca - Marco 3
ESCUTAR: o processo inverso, so para MEDIR. O notebook ouve em vez de anunciar.

No projeto a ancora so transmite (decisao 3). Este script faz o contrario de
proposito, para responder duas perguntas do professor com numero:

  1. Quantos aparelhos Bluetooth UM radio consegue ouvir ao mesmo tempo?
     (conta os anunciantes distintos a cada janela)
  2. A que distancia esta o celular? (RSSI -> metros pelo modelo log-distancia)

    python escutar.py                     # todos os aparelhos em volta
    python escutar.py --alvo "Galaxy"     # acompanha um so (nome ou inicio do endereco)
    python escutar.py --rssi1m -62 --n 2.2

Para o celular aparecer, ele precisa ANUNCIAR: no Android, o app gratuito
"nRF Connect" > Advertiser cria um anuncio com nome. (O app Presenca nao
anuncia: o celular so escuta, por privacidade.)

Limite honesto: Android e iPhone trocam o endereco Bluetooth de tempos em
tempos (privacidade). A contagem e de ANUNCIANTES vistos na janela, nao de
pessoas: o mesmo celular pode aparecer duas vezes depois de trocar de endereco.
"""

import argparse
import asyncio
import statistics
import sys
import time

from winrt.windows.devices.bluetooth.advertisement import (
    BluetoothLEAdvertisementWatcher, BluetoothLEScanningMode,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

JANELA_S = 3.0       # quanto tempo de anuncios entra em cada linha da tabela
SUMIU_S = 10.0       # depois disso o aparelho sai da tabela
PREFIXO_ANCORA = b"PRS1"


def endereco(n):
    h = f"{n:012x}"
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))


def distancia(rssi, rssi_1m, n):
    """Modelo log-distancia: d = 10 ^ ((RSSI@1m - RSSI) / (10 n))."""
    return 10 ** ((rssi_1m - rssi) / (10 * n))


class Escuta:
    def __init__(self, args):
        self.args = args
        self.vistos = {}          # endereco -> {"nome", "amostras": [(t, rssi)], "ancora"}
        self.maximo = 0
        self.total_anuncios = 0

    def ao_anuncio(self, watcher, ev):
        agora = time.time()
        end = endereco(ev.bluetooth_address)
        adv = ev.advertisement
        nome = adv.local_name or ""
        ancora = False
        for m in adv.manufacturer_data:
            try:
                dados = bytes(memoryview(m.data))
            except TypeError:
                dados = b""
            if m.company_id == 0xFFFF and dados.startswith(PREFIXO_ANCORA):
                ancora = True
        d = self.vistos.setdefault(end, {"nome": "", "amostras": [], "ancora": False})
        d["nome"] = nome or d["nome"]
        d["ancora"] = d["ancora"] or ancora
        d["amostras"].append((agora, ev.raw_signal_strength_in_d_bm))
        self.total_anuncios += 1

    def alvo(self, end, d):
        a = self.args.alvo
        return a is None or a.lower() in d["nome"].lower() or end.startswith(a.lower())

    def quadro(self):
        agora = time.time()
        for end in [e for e, d in self.vistos.items() if agora - d["amostras"][-1][0] > SUMIU_S]:
            del self.vistos[end]
        linhas = []
        for end, d in self.vistos.items():
            d["amostras"] = [(t, r) for t, r in d["amostras"] if agora - t <= JANELA_S]
            if not d["amostras"] or not self.alvo(end, d):
                continue
            rssi = statistics.median(r for _, r in d["amostras"])
            linhas.append((rssi, end, d))
        ativos = len(linhas)
        self.maximo = max(self.maximo, ativos)
        linhas.sort(reverse=True)
        print(f"\n{time.strftime('%H:%M:%S')}  aparelhos ouvidos nos últimos {JANELA_S:.0f} s: {ativos}"
              f"  (máximo até agora: {self.maximo} · anúncios recebidos: {self.total_anuncios})")
        print(f"   {'endereço':<18} {'nome':<22} {'pacotes':>7} {'RSSI':>6}  distância*")
        for rssi, end, d in linhas[:self.args.linhas]:
            nome = ("ÂNCORA PRS1 " if d["ancora"] else "") + (d["nome"] or "—")
            dist = distancia(rssi, self.args.rssi1m, self.args.n)
            print(f"   {end:<18} {nome[:22]:<22} {len(d['amostras']):>7} {rssi:>5.0f}  ~{dist:4.1f} m")
        if ativos > self.args.linhas:
            print(f"   … e mais {ativos - self.args.linhas}")


async def principal(args):
    e = Escuta(args)
    w = BluetoothLEAdvertisementWatcher()
    w.scanning_mode = BluetoothLEScanningMode.ACTIVE
    w.add_received(e.ao_anuncio)
    try:
        w.start()
    except OSError:
        print("O Bluetooth do notebook está DESLIGADO (ou ocupado). Ligue em Configurações > "
              "Bluetooth e dispositivos e rode de novo.")
        return
    print("══ Presença · Marco 3 · notebook ESCUTANDO (medição) ══")
    print(f"*distância pelo modelo log-distância: RSSI a 1 m = {args.rssi1m} dBm, expoente n = {args.n}. "
          f"É estimativa: calibre com o teste de 1 m.")
    print("Ctrl+C para parar.")
    try:
        while True:
            await asyncio.sleep(JANELA_S)
            e.quadro()
    finally:
        w.stop()
        print(f"\nMáximo de aparelhos ouvidos ao mesmo tempo: {e.maximo}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alvo", help="parte do nome ou início do endereço do aparelho a acompanhar")
    ap.add_argument("--rssi1m", type=float, default=-60.0, help="RSSI medido a 1 m (dBm)")
    ap.add_argument("--n", type=float, default=2.2, help="expoente de perda (2 = espaço livre)")
    ap.add_argument("--linhas", type=int, default=15)
    try:
        asyncio.run(principal(ap.parse_args()))
    except KeyboardInterrupt:
        pass
