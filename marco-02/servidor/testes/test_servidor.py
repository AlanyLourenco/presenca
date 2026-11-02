"""
Testes do servidor sem broker: um cliente MQTT falso captura o que seria
publicado, e as respostas sao validadas contra os proprios contratos.
"""
import io
import json
import math
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import servidor as srv  # noqa: E402

CONTRATO = os.path.join(srv.RAIZ, "contrato", "v1")


def schema(nome):
    with open(os.path.join(CONTRATO, nome), encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))


class ClienteFalso:
    def __init__(self):
        self.publicados = []

    def publish(self, topico, carga, qos=0, retain=False):
        self.publicados.append((topico, json.loads(carga), retain))


@pytest.fixture
def s(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "AQUI", str(tmp_path))       # log em pasta temporaria
    with open(os.path.join(srv.RAIZ, "servidor", "config.exemplo.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    servidor = srv.Servidor(cfg)
    servidor.cliente = ClienteFalso()
    return servidor


def rssi(ponto, sala):
    out = []
    for aid, (ax, ay) in sala.ancoras.items():
        d = max(0.1, math.hypot(ponto[0] - ax, ponto[1] - ay))
        out.append({"id": aid, "rssi": round(sala.rssi_1m - 10 * sala.expoente * math.log10(d), 1)})
    return out


def hb(s, seq, ponto=(6, 4.5), regiao="DENTRO_ALCANCE", boot="a1b2", **extra):
    anc = rssi(ponto, s.sala)
    d = {
        "eventType": "presenca.heartbeat.v1",
        "eventId": f"apar-01#{boot}#{seq}",
        "deviceId": "apar-01", "entityId": "sala-204", "aluno": "tok-7f3a",
        "bootId": boot, "eventTimeMs": seq * 500, "sequence": seq,
        "value": max(a["rssi"] for a in anc), "unit": "dBm", "state": regiao,
        "ancoras": anc, "amostrasInvalidas": 0, "bufferizado": False,
        "anomaliaInjetada": "nenhuma",
    }
    d.update(extra)
    return d


def enviar(s, dado):
    with redirect_stdout(io.StringIO()) as saida:
        s._processar(json.dumps(dado).encode(), datetime.now(timezone.utc))
    return saida.getvalue()


def test_heartbeat_de_exemplo_respeita_o_contrato(s):
    assert not list(schema("presenca.heartbeat.v1.schema.json").iter_errors(hb(s, 1)))


def test_respostas_respeitam_os_contratos(s):
    for i in range(1, 80):
        enviar(s, hb(s, i, ponto=(6, 4.5) if i < 10 else (40, 40),
                     regiao="DENTRO_ALCANCE" if i < 10 else "FORA_ALCANCE"))
    est = schema("presenca.estado.v1.schema.json")
    avi = schema("presenca.aviso.v1.schema.json")
    estados = [m for t, m, _ in s.cliente.publicados if "/estado/" in t]
    avisos = [m for t, m, _ in s.cliente.publicados if "/aviso/" in t]
    assert estados and avisos
    for m in estados:
        assert not list(est.iter_errors(m)), m
    for m in avisos:
        assert not list(avi.iter_errors(m)), m
    assert [a["tipo"] for a in avisos] == ["AVISO_10_MIN", "AVISO_13_MIN", "LIMITE_ESGOTADO"]


def test_estado_e_retido_e_por_aluno(s):
    enviar(s, hb(s, 1))
    topico, msg, retain = s.cliente.publicados[-1]
    assert topico.endswith("/estado/tok-7f3a") and retain


def test_campo_desconhecido_e_rejeitado_pelo_contrato(s):
    saida = enviar(s, hb(s, 1, bateria=63))
    assert "INVÁLIDA" in saida
    assert s.sessao.contagem["invalidos"] == 1 and not s.sessao.log


def test_duplicata_nao_entra_no_log(s):
    enviar(s, hb(s, 1))
    saida = enviar(s, hb(s, 1))
    assert "REPETIDA" in saida
    assert len(s.sessao.log) == 1


def test_fora_de_ordem_e_aceito_na_posicao_original(s):
    for i in (1, 2, 4, 3):
        saida = enviar(s, hb(s, i))
    assert "FORA DE ORDEM" in saida
    assert sorted(e["t"] for e in s.sessao.log) == [0.5, 1.0, 1.5, 2.0]


def test_atrasado_que_preenche_lacuna_nao_fica_como_perdido(s):
    """Achado rodando no Wokwi: 101 antes de 100 contava 1 perdido para sempre."""
    for i in (1, 2, 4):
        enviar(s, hb(s, i))
    assert s.sessao.contagem["perdidos"] == 1
    saida = enviar(s, hb(s, 3))
    assert "não estava perdida" in saida
    assert s.sessao.contagem["perdidos"] == 0


def test_salto_conta_os_perdidos(s):
    enviar(s, hb(s, 1))
    saida = enviar(s, hb(s, 7))
    assert "SALTO" in saida and s.sessao.contagem["perdidos"] == 5


def test_reboot_nao_vira_duplicata(s):
    """Sequencia recomeca em 1 no boot novo; o bootId separa as identidades."""
    for i in range(1, 5):
        enviar(s, hb(s, i, boot="a1b2"))
    saida = enviar(s, hb(s, 1, boot="c3d4"))
    assert "REPETIDA" not in saida
    assert len(s.sessao.log) == 5
    assert max(e["t"] for e in s.sessao.log) > 2.0      # encaixado depois


def test_lote_atrasado_recalcula_o_passado(s):
    for i in range(1, 11):
        enviar(s, hb(s, i))
    for i in range(21, 31):                              # 11..20 retidos
        enviar(s, hb(s, i))
    antes = s.sessao.ultimo_resultado.acumulado_s
    for i in range(11, 21):
        saida = enviar(s, hb(s, i, bufferizado=True))
    assert "ATRASADA" in saida
    assert s.sessao.ultimo_resultado.acumulado_s >= antes
    assert s.sessao.ultimo_resultado.estado == "PRESENTE"


def test_contador_ingenuo_infla_com_duplicatas(s):
    for i in range(1, 11):
        enviar(s, hb(s, i))
        enviar(s, hb(s, i))                              # cada um chega duas vezes
    assert s.sessao.ingenuo_s == pytest.approx(10.0)
    assert s.sessao.ultimo_resultado.acumulado_s == pytest.approx(4.5)


def de_outro(s, seq, aluno="tok-c3d4e5f6", device="cel-9a8b", **extra):
    d = hb(s, seq, **extra)
    d.update(aluno=aluno, deviceId=device, eventId=f"{device}#{d['bootId']}#{seq}")
    return d


def test_dois_aparelhos_tem_sessoes_separadas(s):
    """ESP32 e celular na mesma sala: os logs nao se misturam."""
    for i in range(1, 7):
        enviar(s, hb(s, i))
        enviar(s, de_outro(s, i, ponto=(30, 30), regiao="FORA_ALCANCE"))
    assert set(s.sessoes) == {"tok-7f3a", "tok-c3d4e5f6"}
    assert s.sessoes["tok-7f3a"].ultimo_resultado.estado == "PRESENTE"
    assert s.sessoes["tok-c3d4e5f6"].ultimo_resultado.estado == "FORA"
    estados = {t.rsplit("/", 1)[1]: m["estado"] for t, m, _ in s.cliente.publicados
               if m["eventType"] == "presenca.estado.v1"}
    assert estados == {"tok-7f3a": "PRESENTE", "tok-c3d4e5f6": "FORA"}


def test_aula_seguinte_abre_sessao_nova_para_o_aluno(s):
    """Encerrada a aula, um boot novo do mesmo aluno e a aula seguinte."""
    fim = int(s.p.duracao_aula / 0.5) + 2
    for i in range(1, fim):
        enviar(s, hb(s, i))
    primeira = s.sessoes["tok-7f3a"]
    assert primeira.encerrada
    enviar(s, hb(s, fim, boot="a1b2"))                   # mesmo boot: ignorado
    assert s.sessoes["tok-7f3a"] is primeira
    enviar(s, hb(s, 1, boot="beef"))
    nova = s.sessoes["tok-7f3a"]
    assert nova is not primeira and not nova.encerrada and len(nova.log) == 1
