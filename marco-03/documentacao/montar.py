#!/usr/bin/env python3
"""
Monta a explicacao do Marco 3 em HTML e PDF.

    python montar.py

Le fontes/documento.html e troca os marcadores:

    {{codigo:<arquivo relativo a marco-03>|<texto da 1a linha>|<texto da ultima linha>}}
    {{terminal:<arquivo em capturas/>|<titulo da janela>}}
    {{img:<arquivo em imagens/>|<legenda>}}       (sem o arquivo: a figura some)

Os trechos de codigo saem do arquivo de verdade, com o numero da linha; as
saidas de terminal sao as capturadas rodando o sistema (capturas/). Assim o
documento nunca fica diferente do codigo.

Sai: Marco3-Seguranca.html e Marco3-Seguranca.pdf (Chrome sem janela).
"""

import base64
import html
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def codigo(arquivo, de, ate):
    caminho = os.path.join(RAIZ, arquivo)
    with open(caminho, encoding="utf-8") as f:
        linhas = f.read().split("\n")
    ini = next((i for i, l in enumerate(linhas) if de in l), None)
    if ini is None:
        raise SystemExit(f"{arquivo}: não achei {de!r}")
    fim = next((i for i in range(ini, len(linhas)) if ate in linhas[i]), None)
    if fim is None:
        raise SystemExit(f"{arquivo}: não achei {ate!r} depois de {de!r}")
    corpo = "\n".join(
        f'<span class="ln">{n + 1:>4}</span>{html.escape(linhas[n])}' for n in range(ini, fim + 1))
    return (f'<figure class="codigo"><figcaption><span class="arq">{html.escape(arquivo)}</span>'
            f'<span class="lin">linhas {ini + 1}–{fim + 1}</span></figcaption><pre>{corpo}</pre></figure>')


CORES = {"31": "vermelho", "32": "verde", "33": "amarelo", "35": "magenta", "36": "ciano",
         "90": "cinza", "1": "negrito"}


def ansi_para_html(texto):
    saida, abertos = [], 0
    for parte in re.split(r"(\x1b\[[0-9;]*m)", texto):
        m = re.fullmatch(r"\x1b\[([0-9;]*)m", parte)
        if not m:
            saida.append(html.escape(parte))
            continue
        for cod in (m.group(1) or "0").split(";"):
            if cod == "0":
                saida.append("</span>" * abertos)
                abertos = 0
            elif cod in CORES:
                saida.append(f'<span class="{CORES[cod]}">')
                abertos += 1
    saida.append("</span>" * abertos)
    return "".join(saida)


def terminal(arquivo, titulo):
    with open(os.path.join(AQUI, "capturas", arquivo), encoding="utf-8", errors="replace") as f:
        texto = f.read().strip("\n")
    return (f'<figure class="terminal"><figcaption><i></i><i></i><i></i>'
            f'<span>{html.escape(titulo)}</span></figcaption>'
            f'<pre>{ansi_para_html(texto)}</pre></figure>')


def img(arquivo, legenda):
    caminho = os.path.join(AQUI, "imagens", arquivo)
    if not os.path.exists(caminho):
        print(f"  (sem {arquivo}: figura omitida)")
        return ""
    tipo = "png" if arquivo.lower().endswith(".png") else "jpeg"
    with open(caminho, "rb") as f:
        dado = base64.b64encode(f.read()).decode()
    return (f'<figure class="print"><img src="data:image/{tipo};base64,{dado}" alt="{html.escape(legenda)}">'
            f'<figcaption>{legenda}</figcaption></figure>')


def montar():
    with open(os.path.join(AQUI, "fontes", "documento.html"), encoding="utf-8") as f:
        doc = f.read()

    def trocar(m):
        tipo, args = m.group(1), m.group(2).split("|")
        return {"codigo": codigo, "terminal": terminal, "img": img}[tipo](*args)

    doc = re.sub(r"\{\{(codigo|terminal|img):(.*?)\}\}", trocar, doc, flags=re.S)
    destino = os.path.join(AQUI, "Marco3-Seguranca.html")
    with open(destino, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"HTML: {destino}")

    chrome = next((c for c in CHROME if os.path.exists(c)), None)
    if not chrome:
        print("Chrome/Edge não encontrado: só o HTML foi gerado.")
        return
    pdf = os.path.join(AQUI, "Marco3-Seguranca.pdf")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", "file:///" + destino.replace("\\", "/")],
                   check=True, capture_output=True, timeout=180)
    print(f"PDF:  {pdf}")


if __name__ == "__main__":
    montar()
