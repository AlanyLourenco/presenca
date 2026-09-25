"""
Prints anotados do guia: recorte, margem para os numeros, setas e legenda.

Cada figura e um dicionario:
    img     arquivo em fontes/imagens/
    corte   (x0, y0, x1, y1) no frame da imagem original
    margem  pixels escuros acrescentados a direita (lugar dos numeros)
    marcas  lista de marcas, cada uma:
              ("seta", n, (x, y), (bx, by))      numero em (bx,by) apontando para (x,y)
              ("linha", n, y, x_fim, depth)      linha de arvore do explorador: seta
                                                  da margem ate o fim do nome
              ("faixa", n, x, y0, y1)             colchete vertical em x de y0 a y1,
                                                  numero logo a direita
    itens   lista de (n, titulo, texto)          - a legenda embaixo
Coordenadas sempre no frame da imagem ORIGINAL; o recorte e aplicado aqui.
"""

import base64
import io
import os

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
IMGS = os.path.join(AQUI, "imagens")


def _img(fig):
    im = Image.open(os.path.join(IMGS, fig["img"])).convert("RGB")
    x0, y0, x1, y1 = fig.get("corte", (0, 0, im.width, im.height))
    im = im.crop((x0, y0, x1, y1))
    m = fig.get("margem", 0)
    if m:
        tela = Image.new("RGB", (im.width + m, im.height), (24, 24, 24))
        tela.paste(im, (0, 0))
        im = tela
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return im.size, (x0, y0), "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def figura(fig):
    (w, h), (ox, oy), uri = _img(fig)
    r = fig.get("raio", max(12, round(w / 55)))
    svg = [f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">']
    for m in fig.get("marcas", []):
        tipo, n = m[0], m[1]
        if tipo == "seta":
            (x, y), (bx, by) = m[2], m[3]
            x, y, bx, by = x - ox, y - oy, bx - ox, by - oy
            svg.append(_seta(bx, by, x, y, r))
            svg.append(_bolha(bx, by, n, r))
        elif tipo == "linha":
            y, x_fim = m[2] - oy, m[3] - ox
            bx = w - fig.get("margem", 40) / 2
            svg.append(_seta(bx, y, x_fim + 6, y, r))
            svg.append(_bolha(bx, y, n, r))
        elif tipo == "faixa":
            x, y0, y1 = m[2] - ox, m[3] - oy, m[4] - oy
            svg.append(f'<path d="M{x - 8},{y0} H{x} V{y1} H{x - 8}" class="an-faixa" stroke-width="{max(2.5, r / 5):.1f}"/>')
            svg.append(_bolha(x + r + 6, (y0 + y1) / 2, n, r))
    svg.append("</svg>")
    leg = "".join(
        f'<li><span class="an-n">{n}</span><div><b>{t}</b> {txt}</div></li>'
        for n, t, txt in fig.get("itens", []))
    cap = f'<figcaption>{fig["legenda"]}</figcaption>' if fig.get("legenda") else ""
    largura = fig.get("largura", "")
    estilo = f' style="max-width:{largura}"' if largura else ""
    lado = " lado" if fig.get("lado") else ""
    return (f'<div class="anot-wrap{lado}"><figure class="anot"{estilo}><div class="an-box">'
            f'<img src="{uri}" alt="{fig.get("alt", "")}">{"".join(svg)}</div>{cap}</figure>'
            + (f'<ol class="an-leg">{leg}</ol>' if leg else "") + "</div>")


def _bolha(x, y, n, r):
    return (f'<g class="an-b"><circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" stroke-width="{r / 6:.1f}"/>'
            f'<text x="{x:.1f}" y="{y + r * 0.36:.1f}" text-anchor="middle" '
            f'style="font-size:{r * 1.05:.1f}px">{n}</text></g>')


def _seta(x0, y0, x1, y1, r):
    import math
    d = math.hypot(x1 - x0, y1 - y0) or 1
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    sx, sy = x0 + ux * r, y0 + uy * r              # sai da borda da bolha
    return (f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
            f'class="an-l" stroke-width="{max(2.5, r / 5):.1f}" marker-end="url(#an-ponta)"/>')


DEFS = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
        '<marker id="an-ponta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
        'fill="#ffb020"/></marker></defs></svg>')


# ---------------------------------------------------------------------------
# utilitarios para a arvore do VS Code
# ---------------------------------------------------------------------------
def fim_nome(depth, nome):
    """x (frame original) do fim do nome numa linha do explorador."""
    inicio = {0: 85, 1: 91, 2: 99, 3: 107, 4: 115, 5: 123}[depth]
    return inicio + 7.1 * len(nome)


def arvore(img, corte, linhas, itens, legenda, alt, margem=70):
    """linhas: (n, y, depth, nome)."""
    return {
        "img": img, "corte": corte, "margem": margem, "alt": alt, "legenda": legenda,
        "lado": True, "largura": "380px",
        "marcas": [("linha", n, y, fim_nome(d, nome), d) for n, y, d, nome in linhas],
        "itens": itens,
    }


def codigo(img, primeira, blocos, itens, legenda, alt, y_primeira=88, passo=19,
           x_faixa=1120, corte=(0, 40, 1140, 577), margem=46):
    """blocos: (n, linha_ini, linha_fim). y de cada linha = y_primeira + passo*(L - primeira)."""
    Y = lambda L: y_primeira + passo * (L - primeira)
    marcas = [("faixa", n, x_faixa, Y(a) - 8, Y(b) + 8) for n, a, b in blocos]
    return {"img": img, "corte": corte, "margem": margem, "marcas": marcas,
            "itens": itens, "legenda": legenda, "alt": alt}
