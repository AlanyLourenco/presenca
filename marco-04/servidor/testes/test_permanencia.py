"""
Testes da maquina de permanencia. Escala 30: persistencia 1 s, orcamento
30 s, avisos em 20 s e 26 s, requalificacao 60 s, aula de 100 s.
"""
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from permanencia import (  # noqa: E402
    AUSENCIA_TOLERADA, AVISO_10, AVISO_13, DENTRO, FIM_DA_AULA, FORA,
    FORA_DA_SALA, LIMITE_ESGOTADO, NEUTRO, PRESENTE, Parametros, Sala,
    calcular, classificar,
)

AQUI = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(AQUI, "config_marco2.json"), encoding="utf-8") as f:
    CFG = json.load(f)

P = Parametros.de_config(CFG)
SALA = Sala.de_config(CFG)
PASSO = 0.5   # heartbeat a cada 500 ms


def trajeto(*trechos, inicio=0.0):
    """trajeto((20, DENTRO), (10, FORA_DA_SALA)) -> log de heartbeats."""
    log, t = [], inicio
    for dur, classe in trechos:
        fim = t + dur
        while t < fim - 1e-9:
            log.append((round(t, 3), classe))
            t += PASSO
    return log


def tipos(r):
    return [a.tipo for a in r.avisos]


# ---------------------------------------------------------------- parametros
def test_escala_comprime_todos_os_tempos_juntos():
    assert P.persistencia == 1
    assert P.orcamento == 30
    assert (P.aviso_1, P.aviso_2) == (20, 26)
    assert P.duracao_aula == 100


# ---------------------------------------------------------------- localizacao
def rssi_em(ponto):
    """RSSI sintetico pelo proprio modelo de propagacao."""
    import math
    out = []
    for aid, (ax, ay) in SALA.ancoras.items():
        d = max(0.1, math.hypot(ponto[0] - ax, ponto[1] - ay))
        out.append({"id": aid, "rssi": SALA.rssi_1m - 10 * SALA.expoente * math.log10(d)})
    return out


@pytest.mark.parametrize("ponto", [(6, 4.5), (2, 2), (11, 8), (6, 1)])
def test_trilateracao_recupera_o_ponto(ponto):
    leituras = {a["id"]: a["rssi"] for a in rssi_em(ponto)}
    x, y = SALA.trilaterar(leituras)
    assert x == pytest.approx(ponto[0], abs=1e-6)
    assert y == pytest.approx(ponto[1], abs=1e-6)


def test_sinal_forte_na_sala_vizinha_nao_conta():
    """O caso que derruba o raio: a parede. Sinal de dentro do alcance,
    posicao fora do poligono."""
    hb = {"state": "DENTRO_ALCANCE", "ancoras": rssi_em((17, 4.5))}
    classe, pos = classificar(hb, SALA)
    assert classe == FORA_DA_SALA
    assert pos[0] > 12


def test_dentro_da_sala_e_dentro_do_alcance():
    hb = {"state": "DENTRO_ALCANCE", "ancoras": rssi_em((6, 4.5))}
    assert classificar(hb, SALA)[0] == DENTRO


def test_fora_do_alcance_decide_sem_posicao():
    hb = {"state": "FORA_ALCANCE", "ancoras": [{"id": "anc-204-A", "rssi": None}]}
    assert classificar(hb, SALA)[0] == FORA_DA_SALA


def test_ancora_nao_ouvida_deixa_neutro():
    anc = rssi_em((6, 4.5))
    anc[2]["rssi"] = None
    hb = {"state": "DENTRO_ALCANCE", "ancoras": anc}
    assert classificar(hb, SALA)[0] == NEUTRO


# ---------------------------------------------------------------- maquina
def test_entrada_exige_persistencia_e_conta_desde_o_inicio_real():
    r = calcular(trajeto((0.5, DENTRO)), P, inicio=0)
    assert r.estado == FORA                       # 0,5 s nao basta
    r = calcular(trajeto((20, DENTRO)), P, inicio=0)
    assert r.estado == PRESENTE
    assert r.transicoes[0][0] == 0                # retroativo ao inicio
    assert r.presenca_s == pytest.approx(19.5)


def test_oscilacao_curta_nao_derruba_a_presenca():
    log = trajeto((10, DENTRO), (0.5, FORA_DA_SALA), (10, DENTRO))
    r = calcular(log, P, inicio=0)
    assert r.estado == PRESENTE
    assert [t[2] for t in r.transicoes] == [PRESENTE]


def test_neutro_interrompe_a_condicao():
    log = trajeto((10, DENTRO), (0.5, FORA_DA_SALA), (0.5, NEUTRO), (0.5, FORA_DA_SALA))
    assert calcular(log, P, inicio=0).estado == PRESENTE


def test_ausencia_curta_e_creditada_apos_requalificar():
    # 20 s dentro, 10 s fora, volta ate o fim da aula
    log = trajeto((20, DENTRO), (10, FORA_DA_SALA), (70, DENTRO))
    r = calcular(log, P, inicio=0)
    assert r.estado == PRESENTE
    assert r.ausencia_usada_s == pytest.approx(10)
    assert r.ausencia_creditada_s == pytest.approx(10)
    assert r.acumulado_s == pytest.approx(99.5)
    assert tipos(r) == []


def test_ausencia_fica_provisoria_ate_requalificar():
    log = trajeto((20, DENTRO), (10, FORA_DA_SALA), (15, DENTRO))
    r = calcular(log, P, inicio=0)
    assert r.ausencia_creditada_s == 0
    assert r.provisorio_s == pytest.approx(10)


def test_voltar_por_instantes_nao_reabre_credito():
    """Requalificacao: aparecer 5 s e sair de novo estorna a ausencia anterior."""
    log = trajeto((20, DENTRO), (10, FORA_DA_SALA), (5, DENTRO), (10, FORA_DA_SALA))
    r = calcular(log, P, inicio=0)
    assert r.estado == AUSENCIA_TOLERADA
    assert r.ausencia_creditada_s == 0
    assert r.ausencia_usada_s == pytest.approx(19.5)   # orcamento consumido mesmo assim


def test_avisos_chegam_antes_do_limite_e_uma_vez_so():
    log = trajeto((10, DENTRO), (27, FORA_DA_SALA))
    r = calcular(log, P, inicio=0)
    assert r.estado == AUSENCIA_TOLERADA
    assert tipos(r) == [AVISO_10, AVISO_13]
    assert [a.em for a in r.avisos] == [30, 36]        # 10 + 20, 10 + 26


def test_orcamento_esgotado_estorna_a_ausencia_inteira():
    log = trajeto((10, DENTRO), (40, FORA_DA_SALA))
    r = calcular(log, P, inicio=0)
    assert r.estado == FORA
    assert r.esgotado
    assert tipos(r) == [AVISO_10, AVISO_13, LIMITE_ESGOTADO]
    esg = r.avisos[-1]
    assert esg.em == 40 and esg.referencia == 10       # parou de contar em t=10
    assert r.acumulado_s == pytest.approx(10)          # nenhum segundo de ausencia


def test_orcamento_e_por_sessao_nao_por_evento():
    """Tres saidas de 12 s: cada uma cabe sozinha, a soma nao."""
    log = trajeto((10, DENTRO), (12, FORA_DA_SALA), (5, DENTRO),
                  (12, FORA_DA_SALA), (5, DENTRO), (12, FORA_DA_SALA))
    r = calcular(log, P, inicio=0)
    assert r.esgotado
    assert r.estado == FORA


def test_acumulador_e_monotonico_nunca_zera_ao_sair():
    anterior = 0
    log = trajeto((30, DENTRO), (40, FORA_DA_SALA), (30, DENTRO))
    for i in range(1, len(log) + 1):
        r = calcular(log[:i], P, inicio=0)
        assert r.acumulado_s >= anterior - 1e-9
        anterior = r.acumulado_s


def test_quem_sai_no_fim_soma_o_que_assistiu():
    log = trajeto((90, DENTRO), (11, FORA_DA_SALA))
    r = calcular(log, P, inicio=0)
    assert r.encerrada
    assert r.acumulado_s == pytest.approx(90)
    assert tipos(r)[-1] == FIM_DA_AULA


def test_saida_nao_confirmada_no_fim_nao_anula_a_ausencia_tolerada():
    """Caso visto no Wokwi: saiu em 23,6 s, voltou em 47,2 s e ficou ate o
    fim; um heartbeat 'fora' isolado em 99,9 s (sem persistencia) zerava os
    23,6 s perdoados e o resultado caia para 76 %."""
    log = (trajeto((23.6, DENTRO)) + trajeto((23.6, FORA_DA_SALA), inicio=23.6)
           + trajeto((52.7, DENTRO), inicio=47.2)
           + [(99.9, FORA_DA_SALA), (100.4, FORA_DA_SALA)])
    r = calcular(log, P, inicio=0)
    assert r.encerrada
    assert r.ausencia_creditada_s == pytest.approx(23.6)
    assert r.acumulado_s == pytest.approx(100)


def test_retorno_a_tempo_nao_e_punido_pela_demora_da_confirmacao():
    """Voltou 0,5 s antes do limite; a confirmacao so vem depois dele."""
    log = trajeto((10, DENTRO), (29.5, FORA_DA_SALA), (5, DENTRO))
    r = calcular(log, P, inicio=0)
    assert not r.esgotado
    assert r.estado == PRESENTE


# ---------------------------------------------------------------- retroativo
def test_ordem_de_chegada_nao_altera_o_resultado():
    log = trajeto((20, DENTRO), (10, FORA_DA_SALA), (40, DENTRO), (35, FORA_DA_SALA))
    embaralhado = log[:]
    random.Random(8).shuffle(embaralhado)
    a, b = calcular(log, P, inicio=0), calcular(embaralhado, P, inicio=0)
    assert (a.estado, a.acumulado_s, tipos(a)) == (b.estado, b.acumulado_s, tipos(b))


def test_lote_atrasado_corrige_o_passado():
    """Rede caiu durante uma ausencia: o servidor viu o aluno 'sumir' e
    depois recebe os heartbeats retidos, que mostram que ele estava na sala."""
    completo = trajeto((60, DENTRO))
    so_ao_vivo = [e for e in completo if not 20 <= e[0] < 45]
    parcial = calcular(so_ao_vivo, P, inicio=0)
    corrigido = calcular(completo, P, inicio=0)
    assert corrigido.acumulado_s == pytest.approx(59.5)
    assert corrigido.acumulado_s >= parcial.acumulado_s
