"""
Testes do servidor sem broker: um cliente MQTT falso captura o que seria
publicado, e as respostas sao validadas contra os proprios contratos.

Marco 3: todo heartbeat sai assinado pela chave do aparelho e com o token
HMAC da janela atual de cada ancora; o que o servidor publica sai assinado
pela chave dele.
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
import seguranca as seg  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

CHAVE_A = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32))
CHAVE_B = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("22" * 32))
CHAVE_SERVIDOR = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("33" * 32))
ALUNO_A, DEVICE_A = seg.identidade_da_chave(seg.publica_hex(CHAVE_A))
ALUNO_B, DEVICE_B = seg.identidade_da_chave(seg.publica_hex(CHAVE_B))
CHAVE_DO_ALUNO = {ALUNO_A: CHAVE_A, ALUNO_B: CHAVE_B}

CONTRATO = os.path.join(srv.RAIZ, "contrato", "v1")


def schema(nome):
    with open(os.path.join(CONTRATO, nome), encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))


class ClienteFalso:
    """Guarda o que seria publicado, ja com o envelope aberto e conferido."""

    def __init__(self):
        self.publicados = []

    def publish(self, topico, carga, qos=0, retain=False):
        de, chave, dado = seg.abrir_envelope(topico, carga)
        assert de == "servidor" and chave == seg.publica_hex(CHAVE_SERVIDOR)
        self.publicados.append((topico, dado, retain))


@pytest.fixture
def s(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "AQUI", str(tmp_path))       # log em pasta temporaria
    with open(os.path.join(srv.RAIZ, "servidor", "testes", "config_marco2.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    segredos = {"broker": "teste.local", "servidor": {"usuario": "u", "senha": "s"},
                "ancoras": {a: (format(i, "02x") * 32) for i, a in enumerate(cfg["sala"]["ancoras"], 1)}}
    servidor = srv.Servidor(cfg, segredos=segredos, chave=CHAVE_SERVIDOR)
    servidor.cliente = ClienteFalso()
    return servidor


def token(s, ancora, atras=0):
    return seg.token_da_ancora(s.segredos["ancoras"][ancora], ancora, seg.janela() - atras)


def rssi(s, ponto):
    out = []
    for aid, (ax, ay) in s.sala.ancoras.items():
        d = max(0.1, math.hypot(ponto[0] - ax, ponto[1] - ay))
        out.append({"id": aid, "rssi": round(s.sala.rssi_1m - 10 * s.sala.expoente * math.log10(d), 1),
                    "token": token(s, aid)})
    return out


def hb(s, seq, ponto=(6, 4.5), regiao="DENTRO_ALCANCE", boot="a1b2", **extra):
    anc = rssi(s, ponto)
    d = {
        "eventType": "presenca.heartbeat.v2",
        "eventId": f"{DEVICE_A}#{boot}#{seq}",
        "deviceId": DEVICE_A, "entityId": "sala-204", "aluno": ALUNO_A,
        "bootId": boot, "eventTimeMs": seq * 500, "medidoEmMs": 1_760_000_000_000 + seq * 500,
        "sequence": seq,
        "value": max(a["rssi"] for a in anc), "unit": "dBm", "state": regiao,
        "ancoras": anc, "amostrasInvalidas": 0, "bufferizado": False,
        "anomaliaInjetada": "nenhuma",
    }
    d.update(extra)
    return d


def assinado(s, dado, chave=None, topico=None):
    chave = chave or CHAVE_DO_ALUNO[dado["aluno"]]
    de = seg.identidade_da_chave(seg.publica_hex(chave))[0]
    return seg.envelopar(chave, de, topico or s.cfg["topico_heartbeat"], dado)


def enviar(s, dado, chave=None, cru=None, topico=None):
    texto = cru if cru is not None else assinado(s, dado, chave, topico)
    with redirect_stdout(io.StringIO()) as saida:
        s._processar(texto.encode(), datetime.now(timezone.utc), s.cfg["topico_heartbeat"])
    return saida.getvalue()


def test_heartbeat_de_exemplo_respeita_o_contrato(s):
    assert not list(schema("presenca.heartbeat.v2.schema.json").iter_errors(hb(s, 1)))
    env = json.loads(assinado(s, hb(s, 1)))
    assert not list(schema("seguranca.envelope.v1.schema.json").iter_errors(env))


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
    assert topico.endswith(f"/estado/{ALUNO_A}") and retain


def test_campo_desconhecido_e_rejeitado_pelo_contrato(s):
    saida = enviar(s, hb(s, 1, bateria=63))
    assert "FORA DO CONTRATO" in saida
    assert s.sessao.contagem["recusados"] == 1 and not s.sessao.log


# -- Marco 3: seguranca -------------------------------------------------------
def test_mensagem_sem_assinatura_e_recusada(s):
    saida = enviar(s, None, cru=json.dumps(hb(s, 1)))
    assert "SEM ASSINATURA" in saida and not s.sessao.log


def test_carga_alterada_depois_de_assinada_e_recusada(s):
    env = json.loads(assinado(s, hb(s, 1, ponto=(40, 40), regiao="FORA_ALCANCE")))
    env["carga"] = env["carga"].replace("FORA_ALCANCE", "DENTRO_ALCANCE")
    saida = enviar(s, None, cru=json.dumps(env))
    assert "ASSINATURA FALSA" in saida and not s.sessao.log


def test_assinatura_de_outro_topico_e_recusada(s):
    saida = enviar(s, hb(s, 1), topico="ufg/ssu/presenca/alany/outra-sala/heartbeat")
    assert "ASSINATURA FALSA" in saida


def test_falar_em_nome_de_outro_aluno_e_recusado(s):
    """B tem a credencial MQTT do app (esta no APK), mas nao a chave de A."""
    saida = enviar(s, hb(s, 1), chave=CHAVE_B)
    assert "IDENTIDADE TROCADA" in saida and ALUNO_A not in s.sessoes


def test_token_de_outra_janela_e_recusado(s):
    d = hb(s, 1)
    for a in d["ancoras"]:
        a["token"] = token(s, a["id"], atras=5)            # um minuto atras
    saida = enviar(s, d)
    assert "TOKEN VENCIDO" in saida and not s.sessao.log


def test_token_inventado_e_recusado(s):
    d = hb(s, 1)
    d["ancoras"][0]["token"] = "00000000"
    assert "TOKEN VENCIDO" in enviar(s, d)


def test_heartbeat_da_fila_aceita_token_de_ate_48_s(s):
    d = hb(s, 1, bufferizado=True)
    for a in d["ancoras"]:
        a["token"] = token(s, a["id"], atras=3)
    saida = enviar(s, d)
    assert "RECUSADA" not in saida and len(s.sessao.log) == 1


def test_ancora_nao_ouvida_nao_precisa_de_token(s):
    d = hb(s, 1, ponto=(40, 40), regiao="FORA_ALCANCE")
    for a in d["ancoras"]:
        a["rssi"], a["token"] = None, None
    d["value"] = None
    assert "RECUSADA" not in enviar(s, d)


def test_respostas_saem_assinadas_pelo_servidor(s):
    enviar(s, hb(s, 1))
    assert s.cliente.publicados                          # o ClienteFalso ja conferiu


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


def de_outro(s, seq, aluno=ALUNO_B, device=DEVICE_B, **extra):
    d = hb(s, seq, **extra)
    d.update(aluno=aluno, deviceId=device, eventId=f"{device}#{d['bootId']}#{seq}")
    return d


def test_dois_aparelhos_tem_sessoes_separadas(s):
    """ESP32 e celular na mesma sala: os logs nao se misturam."""
    for i in range(1, 7):
        enviar(s, hb(s, i))
        enviar(s, de_outro(s, i, ponto=(30, 30), regiao="FORA_ALCANCE"))
    assert set(s.sessoes) == {ALUNO_A, ALUNO_B}
    assert s.sessoes[ALUNO_A].ultimo_resultado.estado == "PRESENTE"
    assert s.sessoes[ALUNO_B].ultimo_resultado.estado == "FORA"
    estados = {t.rsplit("/", 1)[1]: m["estado"] for t, m, _ in s.cliente.publicados
               if m["eventType"] == "presenca.estado.v1"}
    assert estados == {ALUNO_A: "PRESENTE", ALUNO_B: "FORA"}


def test_aula_seguinte_abre_sessao_nova_para_o_aluno(s):
    """Encerrada a aula, um boot novo do mesmo aluno e a aula seguinte."""
    fim = int(s.p.duracao_aula / 0.5) + 2
    for i in range(1, fim):
        enviar(s, hb(s, i))
    primeira = s.sessoes[ALUNO_A]
    assert primeira.encerrada
    enviar(s, hb(s, fim, boot="a1b2"))                   # mesmo boot: ignorado
    assert s.sessoes[ALUNO_A] is primeira
    enviar(s, hb(s, 1, boot="beef"))
    nova = s.sessoes[ALUNO_A]
    assert nova is not primeira and not nova.encerrada and len(nova.log) == 1
