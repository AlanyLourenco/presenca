"""
Projeto Presenca - Marco 4
RELATORIO DE PRESENCA DA TURMA (para o professor).

Modulo puro: recebe as linhas de `sessoes` (com nome e matricula quando o
estudante se identificou) e o resumo dos sensores, e devolve:
  - montar()  o presenca.relatorio.v1, que o servidor publica RETIDO e
              ASSINADO em .../relatorio/<turma> e o app do professor mostra
  - csv()     a lista da turma para exportar (planilha), separada por ";"
              e com virgula decimal, que e o que o Excel em portugues abre
"""

import csv as _csv
import io

COLUNAS_CSV = ["aula", "inicio", "aluno", "nome", "matricula", "situacao", "percentual",
               "resultado", "dentro_s", "perdoado_s", "mensagens", "celular_parado", "bateria"]

NOME_ESTADO = {"PRESENTE": "presente", "AUSENCIA_TOLERADA": "fora (tolerância)",
               "FORA": "fora"}


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt is not None else 0


def montar(turma, linhas, sensores, gerado_em_ms):
    """linhas: sessoes da turma (dicts), ja ordenadas da aula mais nova para a mais velha."""
    aulas = {}
    ordem = []
    for l in linhas:
        a = l.get("aula_id") or "sem-aula"
        if a not in aulas:
            aulas[a] = {"aulaId": a, "inicioMs": _ms(l.get("aula_inicio") or l.get("aberta_em")),
                        "emAndamento": False, "alunos": []}
            ordem.append(a)
        x = sensores.get(l["id"], {})
        aberta = l.get("encerrada_em") is None
        aulas[a]["emAndamento"] = aulas[a]["emAndamento"] or aberta
        contagem = l.get("contagem") or {}
        aulas[a]["alunos"].append({
            "aluno": l["aluno"],
            "nome": l.get("nome"),
            "matricula": l.get("matricula"),
            "estado": l.get("estado") or "FORA",
            "percentual": round(float(l.get("percentual") or 0), 1),
            "aprovado": None if aberta else bool(l.get("aprovado")),
            "dentroS": round(float(l.get("presenca_s") or 0), 1),
            "perdoadoS": round(float(l.get("ausencia_creditada_s") or 0), 1),
            "mensagens": int(contagem.get("aceitos", 0)),
            # So vale como indicio se houve leituras suficientes (>= 6 = 30 s)
            "celularParado": bool(x["sempre_parado"]) if x.get("n", 0) >= 6 else None,
            "bateria": None if x.get("bateria") is None else round(float(x["bateria"]), 2),
            "ultimoContatoMs": _ms(l.get("atualizada_em")),
        })
    return {"eventType": "presenca.relatorio.v1", "turma": turma, "geradoEmMs": gerado_em_ms,
            "aulas": [aulas[a] for a in ordem][:20]}


def _num(x, casas=1):
    return "" if x is None else f"{x:.{casas}f}".replace(".", ",")


def csv(rel):
    """O relatorio como planilha (uma linha por aluno por aula)."""
    from datetime import datetime
    saida = io.StringIO()
    w = _csv.writer(saida, delimiter=";", lineterminator="\n")
    w.writerow(COLUNAS_CSV)
    for a in rel["aulas"]:
        inicio = datetime.fromtimestamp(a["inicioMs"] / 1000).strftime("%d/%m/%Y %H:%M") if a["inicioMs"] else ""
        for x in a["alunos"]:
            resultado = ("em andamento" if x["aprovado"] is None
                         else "presente" if x["aprovado"] else "falta")
            w.writerow([a["aulaId"], inicio, x["aluno"], x["nome"] or "", x["matricula"] or "",
                        NOME_ESTADO.get(x["estado"], x["estado"]), _num(x["percentual"]),
                        resultado, _num(x["dentroS"]), _num(x["perdoadoS"]), x["mensagens"],
                        "" if x["celularParado"] is None else ("sim" if x["celularParado"] else "não"),
                        "" if x["bateria"] is None else f"{round(x['bateria'] * 100)} %"])
    return saida.getvalue()
