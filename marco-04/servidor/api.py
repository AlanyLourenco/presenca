"""
Projeto Presenca - Marco 4
API HTTP de consulta (so leitura, mais o apagamento da LGPD e o atuador).

Sobe junto com o servidor, em http://127.0.0.1:8090 (so na propria maquina:
a API nao tem senha, entao nao fica exposta na rede).

    GET    /                                   pagina com o relatorio de cada turma
    GET    /api/saude                          banco, broker, fila, sessoes abertas
    GET    /api/turmas/<turma>/relatorio       presenca.relatorio.v1 (JSON)
    GET    /api/turmas/<turma>/relatorio.csv   lista da turma para planilha
    GET    /api/alunos/<aluno>/historico       todas as aulas de um pseudonimo
    POST   /api/alunos/<aluno>/comando         {"tipo": "vibrar", "texto": "..."}  (ATUADOR)
    DELETE /api/alunos/<aluno>                 direito de eliminacao (LGPD art. 18)
"""

import html
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import relatorio
from banco import json_seguro

TURMA = r"([A-Z0-9]{6})"
ALUNO = r"(tok-[0-9a-f]{8})"


def _pagina(srv):
    with srv.trava:
        turmas = sorted({s.turma for s in srv.sessoes.values() if s.turma})
    partes = []
    for t in turmas:
        rel = srv.montar_relatorio(t)
        if rel is None:
            partes.append(f"<p>Turma {t}: banco fora do ar.</p>")
            continue
        linhas = []
        for a in rel["aulas"]:
            for x in a["alunos"]:
                res = "em andamento" if x["aprovado"] is None else ("presente" if x["aprovado"] else "falta")
                linhas.append(
                    f"<tr><td>{html.escape(a['aulaId'])}</td><td>{html.escape(x['nome'] or '')}</td>"
                    f"<td><code>{x['aluno']}</code></td><td>{x['estado']}</td>"
                    f"<td style='text-align:right'>{x['percentual']:.0f} %</td><td>{res}</td>"
                    f"<td>{'sim' if x['celularParado'] else ''}</td></tr>")
        partes.append(
            f"<h2>Turma {t} <a href='/api/turmas/{t}/relatorio.csv'>baixar CSV</a></h2>"
            "<table><tr><th>aula</th><th>nome</th><th>pseudônimo</th><th>situação</th><th>%</th>"
            "<th>resultado</th><th>celular parado</th></tr>" + "".join(linhas) + "</table>")
    corpo = "".join(partes) or "<p>Nenhuma aula ainda.</p>"
    return ("<!doctype html><meta charset='utf-8'><meta http-equiv='refresh' content='5'>"
            "<title>Presença — relatório</title><style>body{font-family:system-ui;margin:24px}"
            "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}</style>"
            f"<h1>Presença — relatório de presença</h1>{corpo}"
            "<p style='color:#777'>Atualiza a cada 5 s. Dados do PostgreSQL/TimescaleDB.</p>")


def criar_manipulador(srv):
    class Manipulador(BaseHTTPRequestHandler):
        def log_message(self, *args):          # sem poluir o terminal do servidor
            pass

        def _responder(self, codigo, corpo, tipo="application/json; charset=utf-8", extra=None):
            dados = corpo if isinstance(corpo, bytes) else (
                corpo if isinstance(corpo, str) else json.dumps(json_seguro(corpo), ensure_ascii=False)
            ).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(dados)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):
            # Leituras do banco SEM a trava do servidor: banco lento nao segura as mensagens.
            caminho = self.path.split("?")[0]
            if caminho == "/":
                return self._responder(200, _pagina(srv), "text/html; charset=utf-8")
            if caminho == "/api/saude":
                with srv.trava:
                    saude = {
                        "banco": "online" if srv.banco.online else "fora",
                        "filaBanco": len(srv.banco.fila),
                        "broker": bool(srv.cliente and srv.cliente.is_connected()),
                        "sessoesAbertas": sum(not s.encerrada for s in srv.sessoes.values()),
                        "silenciosos": sorted(srv.silenciosos),
                        "ancorasMudas": sorted(srv.ancoras_mudas),
                    }
                return self._responder(200, saude)
            m = re.fullmatch(rf"/api/turmas/{TURMA}/relatorio(\.csv)?", caminho)
            if m:
                rel = srv.montar_relatorio(m.group(1))
                if rel is None:
                    return self._responder(503, {"erro": "banco fora do ar"})
                if m.group(2):
                    return self._responder(
                        200, ("﻿" + relatorio.csv(rel)).encode("utf-8"), "text/csv; charset=utf-8",
                        {"Content-Disposition": f"attachment; filename=presenca-{m.group(1)}.csv"})
                return self._responder(200, rel)
            m = re.fullmatch(rf"/api/alunos/{ALUNO}/historico", caminho)
            if m:
                h = srv.banco.historico_aluno(m.group(1))
                return self._responder(200 if h is not None else 503, h if h is not None else {"erro": "banco fora"})
            self._responder(404, {"erro": "não encontrado"})

        def do_POST(self):
            m = re.fullmatch(rf"/api/alunos/{ALUNO}/comando", self.path)
            if not m:
                return self._responder(404, {"erro": "não encontrado"})
            try:
                pedido = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except ValueError:
                return self._responder(400, {"erro": "JSON inválido"})
            tipo = pedido.get("tipo", "vibrar")
            if tipo not in ("vibrar", "chamar", "lanterna"):
                return self._responder(400, {"erro": "tipo deve ser vibrar, chamar ou lanterna"})
            with srv.trava:
                cid = srv.enviar_comando(m.group(1), tipo, pedido.get("texto"))
            if cid is None:
                return self._responder(409, {"erro": "aluno sem aula em andamento"})
            self._responder(202, {"comandoId": cid})

        def do_DELETE(self):
            m = re.fullmatch(rf"/api/alunos/{ALUNO}", self.path)
            if not m:
                return self._responder(404, {"erro": "não encontrado"})
            n = srv.esquecer_aluno(m.group(1))
            if n is None:
                return self._responder(503, {"erro": "banco fora do ar"})
            self._responder(200, {"apagado": m.group(1), "linhas": n})

    return Manipulador


def iniciar_api(srv, cfg):
    import os
    host = os.environ.get("PRESENCA_API_HOST", cfg.get("host", "127.0.0.1"))
    porta = cfg.get("porta", 8090)
    try:
        http = ThreadingHTTPServer((host, porta), criar_manipulador(srv))
    except OSError as e:
        print(f"  API HTTP não subiu na porta {porta}: {e}")
        return None
    threading.Thread(target=http.serve_forever, daemon=True).start()
    print(f"\033[90mAPI e relatório: http://{'127.0.0.1' if host == '0.0.0.0' else host}:{porta}/\033[0m")
    return http
