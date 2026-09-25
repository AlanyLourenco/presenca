#!/usr/bin/env python3
"""
Monta a apresentacao do Marco 2 a partir das fontes e gera o PDF.

    python montar.py            # HTML + PDF
    python montar.py --sem-pdf  # so o HTML

Fontes:
    fontes/presenca.html   Parte I  - fronteira aparelho <-> servidor
    fontes/co2.html        Parte II - fronteira ancora de CO2 <-> gateway (versao anterior)
    fontes/extra.css       estilos acrescentados

As imagens {{img:caminho}} sao embutidas em base64, e o arquivo final abre sem
internet. O grafico {{grafico}} e desenhado a partir de
evidencias/presenca/log-servidor.txt - sao os valores publicados pelo servidor.
"""

import base64
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "fontes"))
from anotacoes import DEFS, figura  # noqa: E402
from figuras import F  # noqa: E402
MARCO = os.path.dirname(AQUI)
SAIDA_HTML = os.path.join(AQUI, "apresentacao-marco-02.html")
SAIDA_PDF = os.path.join(AQUI, "apresentacao-marco-02.pdf")


def ler(nome):
    with open(os.path.join(AQUI, "fontes", nome), encoding="utf-8") as f:
        return f.read()


def embutir(html):
    def troca(m):
        caminho = os.path.join(MARCO, m.group(1))
        tipo = "image/png" if caminho.endswith(".png") else "image/jpeg"
        with open(caminho, "rb") as f:
            return f"data:{tipo};base64," + base64.b64encode(f.read()).decode()
    return re.sub(r"\{\{img:([^}]+)\}\}", troca, html)


# ---------------------------------------------------------------------------
def grafico():
    """Acumulado garantido publicado pelo servidor na sessao s31a2."""
    with open(os.path.join(MARCO, "evidencias", "presenca", "log-servidor.txt"), encoding="utf-8") as f:
        linhas = f.read().split("\n")
    ini = next(i for i, l in enumerate(linhas) if "sessao s31a2 aberta" in l)
    fim = next(i for i, l in enumerate(linhas) if "RELATORIO FINAL DA SESSAO s31a2" in l)
    pts = {}
    for l in linhas[ini:fim]:
        m = re.search(r"t=\s*([\d.]+)s\s+seq=\d+.*acum\s+([\d.]+)s", l)
        if m:
            pts[float(m.group(1))] = float(m.group(2))
    serie = sorted(pts.items())

    W, H = 760, 330
    x0, x1, y0, y1 = 52, 740, 280, 58      # area de plotagem
    X = lambda t: x0 + (x1 - x0) * t / 100
    Y = lambda v: y0 - (y0 - y1) * v / 100
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Acumulado garantido da sessão '
         f's31a2 ao longo dos 100 s de aula: sobe durante a presença, fica parado na ausência '
         f'tolerada entre 8,8 e 36,3 s, atravessa a queda de rede sem buraco e salta de 67 para 95 s '
         f'em 96,3 s, quando a requalificação credita a ausência. Termina em 98,6 s.">']
    # grade e eixos
    for v in (0, 25, 50, 75, 100):
        s.append(f'<line class="grade" x1="{x0}" x2="{x1}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>')
        s.append(f'<text x="{x0 - 8}" y="{Y(v) + 4:.1f}" text-anchor="end">{v} s</text>')
    for t in (0, 20, 40, 60, 80, 100):
        s.append(f'<text x="{X(t):.1f}" y="{y0 + 18}" text-anchor="middle">{t}</text>')
    s.append(f'<text x="{x1}" y="{y0 + 34}" text-anchor="end">t da aula (s)</text>')
    s.append(f'<line class="eixo" x1="{x0}" x2="{x1}" y1="{y0}" y2="{y0}"/>')
    # linha de 75 %
    s.append(f'<line class="marca" x1="{x0}" x2="{x1}" y1="{Y(75):.1f}" y2="{Y(75):.1f}" style="stroke:var(--verde)"/>')
    s.append(f'<text x="{x0 + 4}" y="{Y(75) - 5:.1f}">mínimo para aprovação: 75 %</text>')
    # janela da queda de rede (heartbeats retidos)
    s.append(f'<rect class="rede" x="{X(68.8):.1f}" y="{y1}" width="{X(88.8) - X(68.8):.1f}" height="{y0 - y1}"/>')
    s.append(f'<text class="rot" x="{X(78.8):.1f}" y="{Y(92):.1f}" text-anchor="middle">rede fora</text>')
    s.append(f'<text x="{X(78.8):.1f}" y="{Y(92) + 14:.1f}" text-anchor="middle">41 retidos, entregues depois</text>')
    # faixa de estados
    faixas = [(0, 1.4, "b-verm", ""), (1.4, 8.8, "b-verde", ""), (8.8, 36.3, "b-ambar", "AUSÊNCIA TOLERADA"),
              (36.3, 100, "b-verde", "PRESENTE")]
    for a, b, cls, rot in faixas:
        s.append(f'<rect class="{cls}" x="{X(a):.1f}" y="18" width="{X(b) - X(a) - 2:.1f}" height="18" rx="3"/>')
        if rot:
            s.append(f'<text class="rot" x="{X((a + b) / 2):.1f}" y="31" text-anchor="middle">{rot}</text>')
    # marcos
    for t, rot, y in ((28.8, "aviso 10 min", y1 + 12), (34.8, "aviso 13 min", y1 + 26)):
        s.append(f'<line class="marca" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y1}" y2="{y0}"/>')
        s.append(f'<text class="rot" x="{X(t) + 5:.1f}" y="{y}">{rot}</text>')
    s.append(f'<line class="marca" x1="{X(96.3):.1f}" x2="{X(96.3):.1f}" y1="{Y(70):.1f}" y2="{y0}"/>')
    s.append(f'<text class="rot" x="{X(96.3) - 6:.1f}" y="{Y(33):.1f}" text-anchor="end">requalificou:</text>')
    s.append(f'<text x="{X(96.3) - 6:.1f}" y="{Y(33) + 13:.1f}" text-anchor="end">+27,5 s de ausência creditados</text>')
    s.append(f'<text x="{X(54.6):.1f}" y="{Y(60):.1f}" text-anchor="middle">T3: repetido,</text>')
    s.append(f'<text x="{X(54.6):.1f}" y="{Y(60) + 13:.1f}" text-anchor="middle">fora de ordem, salto</text>')
    s.append(f'<line class="marca" x1="{X(54.6):.1f}" x2="{X(54.6):.1f}" y1="{Y(60) + 18:.1f}" y2="{Y(30):.1f}"/>')
    # a serie
    caminho = " ".join(f"{'M' if i == 0 else 'L'}{X(t):.1f},{Y(v):.1f}" for i, (t, v) in enumerate(serie))
    s.append(f'<path class="linha" d="{caminho}"/>')
    t_fim, v_fim = serie[-1]
    s.append(f'<circle cx="{X(min(t_fim, 100)):.1f}" cy="{Y(v_fim):.1f}" r="5"><title>{v_fim:.1f} s ao fim da aula</title></circle>')
    s.append(f'<text class="rot" x="{X(100) - 10:.1f}" y="{Y(v_fim) - 8:.1f}" text-anchor="end">{f"{v_fim:.1f}".replace(".", ",")} s · aprovado</text>')
    s.append("</svg>")
    return "\n".join(s)


# ---------------------------------------------------------------------------
def montar():
    co2 = ler("co2.html")
    estilo = co2[co2.index("<style>") + 7: co2.index("</style>")]
    ini = co2.index("<!-- ============ 1 ============ -->")
    fim = co2.index("<!-- ============ 9 ============ -->")
    parte2 = co2[ini:fim]
    # renumera a Parte II e ajusta os nomes das pastas
    for n in range(1, 9):
        parte2 = parte2.replace(f'<section id="s{n}">', f'<section id="co2-{n}">')
        parte2 = parte2.replace(f'<span class="sec-n">0{n}</span>', f'<span class="sec-n">II.{n}</span>')
        parte2 = parte2.replace(f'href="#s{n}"', f'href="#co2-{n}"')
    parte2 = (parte2.replace("produtor/", "co2-ancora/").replace("consumidor/", "co2-gateway/")
                    .replace("├── README.md              ← a entrega: documentação da fronteira\n", "")
                    .replace("├── GUIA.md                ← a versão deste guia em Markdown\n", "├── GUIA.md                ← este guia em Markdown\n"))

    parte1 = ler("presenca.html").replace("{{grafico}}", grafico())
    guia = re.sub(r"\{\{anot:([\w-]+)\}\}", lambda m: figura(F[m.group(1)]), ler("guia.html"))

    toc = """
  <nav class="toc">
    <div class="toc-h">Guia do dia</div>
    <ol>
      <li><a href="#g0"><span class="n">0</span> Como ler</a></li>
      <li><a href="#ea"><span class="n">A</span> Preparar o PC</a></li>
      <li><a href="#eb"><span class="n">B</span> No dia, antes</a></li>
      <li><a href="#ec"><span class="n">C</span> A apresentação</a></li>
      <li><a href="#c3"><span class="n">C3</span> As pastas</a></li>
      <li><a href="#c4"><span class="n">C4</span> Circuito e código</a></li>
      <li><a href="#mexer"><span class="n">·</span> Potenciômetros</a></li>
      <li><a href="#cenarios"><span class="n">C5</span> Os 7 cenários</a></li>
      <li><a href="#c10"><span class="n">C10</span> Contrato</a></li>
      <li><a href="#c12"><span class="n">C12</span> Gateway de CO₂</a></li>
      <li><a href="#ed"><span class="n">D</span> Se der errado</a></li>
      <li><a href="#g14"><span class="n">G14</span> Rede e WebSocket</a></li>
    </ol>
    <div class="toc-h" style="margin-top:22px">Parte I · presença</div>
    <ol>
      <li><a href="#p1"><span class="n">1</span> O que entrega</a></li>
      <li><a href="#p2"><span class="n">2</span> A fronteira</a></li>
      <li><a href="#p3"><span class="n">3</span> Os arquivos</a></li>
      <li><a href="#p4"><span class="n">4</span> O circuito</a></li>
      <li><a href="#p5"><span class="n">5</span> O aparelho</a></li>
      <li><a href="#p6"><span class="n">6</span> O servidor</a></li>
      <li><a href="#p7"><span class="n">7</span> Os contratos</a></li>
      <li><a href="#p8"><span class="n">8</span> Testes no Wokwi</a></li>
      <li><a href="#p9"><span class="n">9</span> Testes automáticos</a></li>
      <li><a href="#p10"><span class="n">10</span> Achados</a></li>
      <li><a href="#p11"><span class="n">11</span> Limites</a></li>
      <li><a href="#p12"><span class="n">12</span> Roteiro ao vivo</a></li>
      <li><a href="#p13"><span class="n">13</span> Perguntas</a></li>
    </ol>
    <div class="toc-h" style="margin-top:22px">Parte II · CO₂</div>
    <ol>
      <li><a href="#co2-1"><span class="n">II.1</span> O problema</a></li>
      <li><a href="#co2-2"><span class="n">II.2</span> A fronteira</a></li>
      <li><a href="#co2-4"><span class="n">II.4</span> O circuito</a></li>
      <li><a href="#co2-5"><span class="n">II.5</span> O programa</a></li>
      <li><a href="#co2-6"><span class="n">II.6</span> O gateway</a></li>
      <li><a href="#co2-8"><span class="n">II.8</span> Perguntas</a></li>
    </ol>
  </nav>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Guia do Marco 2</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{estilo}
{ler("extra.css")}
</style>
</head>
<body>
{DEFS}
<div class="topbar"><div class="topbar-in">
  <span class="brand">Presença <span>/ Marco 2</span></span>
  <span class="spacer"></span>
  <a href="#c5">Testes ao vivo</a>
  <a href="https://wokwi.com/projects/476110187626906625">Wokwi do aparelho</a>
  <a href="https://github.com/AlanyLourenco/presenca">Repositório</a>
</div></div>

<header class="hero">
  <div class="kicker"><b>Software para Sistemas Ubíquos</b> · Instituto de Informática, UFG · Prof. Dr. Otávio Calaça Xavier</div>
  <h1>Guia para apresentar o Marco 2</h1>
  <p class="dek">Permanência medida, não presença num instante. Um ESP32 no papel do celular do
  estudante ouve as três âncoras da sala; um servidor transforma esses heartbeats em minutos de
  permanência, avisa antes de punir e devolve a decisão ao aparelho. Primeiro o roteiro do dia,
  passo a passo e com prints anotados; depois a referência técnica completa.</p>
  <div class="meta">
    <span><span class="lbl">Aluna</span> <b>Alany Gabrielly</b> · 202105018</span>
    <span><span class="lbl">Responsabilidade</span> <b>comunicação e resiliência</b></span>
    <span><span class="lbl">Teste adversarial</span> <b>sequência</b>, matrícula terminada em 8</span>
    <span><span class="lbl">Wokwi</span> <a href="https://wokwi.com/projects/476110187626906625">aparelho ↗</a> · <a href="https://wokwi.com/projects/476001394839038977">CO₂ ↗</a></span>
  </div>
</header>

<div class="shell">
{toc}
  <main>
{guia}
{parte1}
{parte2}
  </main>
</div>

<footer>
  Projeto <strong>Presença</strong> · Marco 2 e Atividade 03 · Software para Sistemas Ubíquos ·
  Instituto de Informática, UFG · Prof. Dr. Otávio Calaça Xavier<br>
  Alany Gabrielly, matrícula 202105018 · capturas e logs da execução real em <code>marco-02/evidencias/</code>
</footer>
</body>
</html>
"""
    html = embutir(html)
    with open(SAIDA_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML: {SAIDA_HTML} ({len(html) // 1024} KB)")


def chrome():
    for c in (shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("msedge"),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if c and os.path.exists(c):
            return c
    raise SystemExit("Chrome ou Edge nao encontrado para gerar o PDF.")


def pdf():
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=15000", f"--print-to-pdf={SAIDA_PDF}",
                    "file:///" + SAIDA_HTML.replace("\\", "/")], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"PDF:  {SAIDA_PDF} ({os.path.getsize(SAIDA_PDF) // 1024} KB)")


if __name__ == "__main__":
    montar()
    if "--sem-pdf" not in sys.argv:
        pdf()
