#!/usr/bin/env python3
"""
Projeto Presenca - Marco 3
Ajusta o modelo de distancia com as SUAS medicoes reais.

Hoje o app estima a distancia pelo modelo log-distancia com um expoente
chutado (n = 2,2, EXPOENTE_PERDA em app/src/lib/config.ts):

    RSSI(d) = RSSI(1 m) - 10 * n * log10(d)

Depois de medir (afaste-se 0,5 / 1 / 2 / 3 / 4 / 5 m do notebook, parada,
uns 10 s em cada ponto, e anote o dBm que o app mostra), preencha
distancia.csv e rode:

    python ajustar_distancia.py

Sai o n que melhor explica as suas medidas (minimos quadrados), o erro de
cada ponto em metros e a faixa real em que "1 m" pode cair.
"""

import csv
import math
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def ler(caminho):
    pontos = []
    with open(caminho, encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            if linha["rssi_dbm"].strip():
                pontos.append((float(linha["distancia_m"]), float(linha["rssi_dbm"])))
    return pontos


def ajustar(pontos):
    """Reta RSSI = A - 10 n log10(d): devolve (A = RSSI a 1 m, n)."""
    xs = [-10 * math.log10(d) for d, _ in pontos]
    ys = [r for _, r in pontos]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    n = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - n * mx, n


def main():
    pontos = ler(os.path.join(AQUI, "distancia.csv"))
    if len(pontos) < 3:
        sys.exit("Preencha pelo menos 3 linhas de distancia.csv com o dBm medido.")
    a, n = ajustar(pontos)
    print(f"Modelo ajustado: RSSI(d) = {a:.1f} − 10 × {n:.2f} × log10(d)")
    print(f"  RSSI a 1 m ≈ {a:.1f} dBm · expoente n ≈ {n:.2f}  (o app usa 2,2)")
    print(f"\n  {'medido':>8} {'RSSI':>6} {'estimado':>9} {'erro':>7}")
    for d, r in pontos:
        est = 10 ** ((a - r) / (10 * n))
        print(f"  {d:>6.1f} m {r:>6.0f} {est:>7.2f} m {est - d:>+6.2f} m")
    resid = [r - (a - 10 * n * math.log10(d)) for d, r in pontos]
    desvio = (sum(x * x for x in resid) / max(1, len(resid) - 2)) ** 0.5
    lo, hi = 10 ** (-desvio / (10 * n)), 10 ** (desvio / (10 * n))
    print(f"\n  Oscilação do sinal em volta da reta: ±{desvio:.1f} dB")
    print(f"  ⇒ quando o app diz '1 m', a distância real fica entre ~{lo:.2f} m e ~{hi:.2f} m")
    print(f"\nPara usar: EXPOENTE_PERDA = {n:.1f} em app/src/lib/config.ts (só muda a distância "
          f"mostrada; perto/longe continua vindo da calibração a 1 m).")


if __name__ == "__main__":
    main()
