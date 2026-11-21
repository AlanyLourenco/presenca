"""
Testes do Marco 4: persistencia, recuperacao depois de reiniciar, sensores do
celular, atuador (comando + confirmacao), cadastro, relatorio, silencio com
motivo, duas ancoras e LGPD.

Rodam sem broker e, por padrao, com o banco em memoria. Os testes marcados
`pg` usam o PostgreSQL/TimescaleDB de verdade (docker compose up -d banco) e
sao pulados se ele nao estiver no ar.
"""
import io
import json
import os
import sys
import threading
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import relatorio  # noqa: E402
import seguranca as seg  # noqa: E402
import servidor as srv  # noqa: E402
from banco import Banco, BancoMemoria  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from permanencia import DENTRO, FORA_DA_SALA, NEUTRO, Sala, classificar  # noqa: E402

CHAVE_A = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("11" * 32))
CHAVE_B = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("22" * 32))
CHAVE_SERVIDOR = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("33" * 32))
ALUNO_A, DEVICE_A = seg.identidade_da_chave(seg.publica_hex(CHAVE_A))
ALUNO_B, DEVICE_B = seg.identidade_da_chave(seg.publica_hex(CHAVE_B))
CHAVES = {ALUNO_A: CHAVE_A, ALUNO_B: CHAVE_B}
DEVICES = {ALUNO_A: DEVICE_A, ALUNO_B: DEVICE_B}
TURMA, AULA = "ABC234", "demo-1763600000000"
CONTRATO = os.path.join(srv.RAIZ, "contrato", "v1")

with open(os.path.join(srv.AQUI, "config.exemplo.json"), encoding="utf-8") as f:
    CFG = json.load(f)
SEGREDOS = {"broker": "teste.local", "servidor": {"usuario": "u", "senha": "s"},
            "ancoras": {"anc-pc-1": "01" * 32, "anc-pc-2": "02" * 32}}


def schema(nome):
    with open(os.path.join(CONTRATO, nome + ".schema.json"), encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))


class ClienteFalso:
    def __init__(self):
        self.publicados = []

    def publish(self, topico, carga, qos=0, retain=False):
        if not carga:                        # apagar mensagem retida
            self.publicados.append((topico, None, retain))
            return
        de, chave, dado = seg.abrir_envelope(topico, carga)
        assert de == "servidor" and chave == seg.publica_hex(CHAVE_SERVIDOR)
        self.publicados.append((topico, dado, retain))

    def is_connected(self):
        return True


def novo_servidor(tmp_path, banco):
    srv.AQUI = str(tmp_path)          # recebidos.log em pasta temporaria
    s = srv.Servidor(CFG, segredos=SEGREDOS, chave=CHAVE_SERVIDOR, banco=banco, conectar_mqtt=False)
    s.cliente = ClienteFalso()
    return s


@pytest.fixture
def banco():
    return BancoMemoria(lambda *_: None)


@pytest.fixture
def s(tmp_path, banco):
    return novo_servidor(tmp_path, banco)


def token(ancora):
    return seg.token_da_ancora(SEGREDOS["ancoras"][ancora], ancora, seg.janela())


def hb(seq, aluno=ALUNO_A, regiao="DENTRO_ALCANCE", boot="a1b2", rssi1=-55.0, rssi2=None, aula=AULA):
    anc = [{"id": "anc-pc-1", "rssi": rssi1, "token": token("anc-pc-1") if rssi1 is not None else None},
           {"id": "anc-pc-2", "rssi": rssi2, "token": token("anc-pc-2") if rssi2 is not None else None}]
    ouvidas = [a["rssi"] for a in anc if a["rssi"] is not None]
    dev = DEVICES[aluno]
    return {
        "eventType": "presenca.heartbeat.v3", "eventId": f"{dev}#{boot}#{seq}", "deviceId": dev,
        "entityId": "sala-pc", "aluno": aluno, "turma": TURMA, "aulaId": aula, "bootId": boot,
        "eventTimeMs": seq * 5000, "medidoEmMs": 1_763_600_000_000 + seq * 5000, "sequence": seq,
        "value": max(ouvidas) if ouvidas else None, "unit": "dBm", "state": regiao, "ancoras": anc,
        "amostrasInvalidas": 0, "bufferizado": False, "anomaliaInjetada": "nenhuma",
    }


def enviar(s, dado, topico_nome="heartbeat", chave=None, sufixo=""):
    topico = s.cfg[f"topico_{topico_nome}"] + sufixo
    chave = chave or CHAVES[dado["aluno"]]
    de = seg.identidade_da_chave(seg.publica_hex(chave))[0]
    texto = seg.envelopar(chave, de, topico, dado)

    class Msg:
        pass
    m = Msg()
    m.topic, m.payload = topico, texto.encode()
    with redirect_stdout(io.StringIO()) as saida:
        s._ao_receber(None, None, m)
    return saida.getvalue()


def sensor(n, aluno=ALUNO_A, parado=False, nivel=0.8, carregando=False):
    return {"eventType": "presenca.sensor.v1", "sensorId": f"{DEVICES[aluno]}#a1b2#{n}",
            "aluno": aluno, "deviceId": DEVICES[aluno], "turma": TURMA,
            "medidoEmMs": 1_763_600_000_000 + n * 5000,
            "acelerometro": {"movimento": 0.002 if parado else 0.08, "amostras": 50, "parado": parado},
            "bateria": {"nivel": nivel, "carregando": carregando}}


# ---------------------------------------------------------------- contrato
def test_mensagens_de_exemplo_respeitam_os_contratos():
    assert not list(schema("presenca.heartbeat.v3").iter_errors(hb(1)))
    assert not list(schema("presenca.sensor.v1").iter_errors(sensor(1)))


def test_heartbeat_v3_abre_sessao_da_turma_e_da_aula(s):
    enviar(s, hb(1))
    sess = s.sessoes[ALUNO_A]
    assert (sess.turma, sess.aula_id) == (TURMA, AULA)


def test_aula_nova_abre_sessao_nova(s):
    for i in range(1, 4):
        enviar(s, hb(i))
    primeira = s.sessoes[ALUNO_A].id
    enviar(s, hb(4, aula="demo-1763609999999"))
    assert s.sessoes[ALUNO_A].id != primeira


# ---------------------------------------------------------------- persistência
def test_todo_heartbeat_vai_para_o_banco_inclusive_duplicata(s, banco):
    for i in range(1, 6):
        enviar(s, hb(i))
    enviar(s, hb(3))                                    # repetida
    assert len(banco.eventos) == 6
    assert [e["classificacao"] for e in banco.eventos].count("duplicado") == 1
    sess = banco.sessoes[s.sessoes[ALUNO_A].id]
    assert sess["turma"] == TURMA and sess["contagem"]["aceitos"] == 5


def test_recusa_vai_para_o_banco(s, banco):
    falso = hb(1)
    falso["ancoras"][0]["token"] = "deadbeef"
    enviar(s, falso)
    assert banco.recusas and banco.recusas[0]["motivo"] == "TOKEN VENCIDO"


# ---------------------------------------------------------------- recuperação
def test_servidor_reiniciado_recupera_a_aula_e_continua_igual(tmp_path, banco):
    """Reiniciar no meio da aula da o MESMO resultado que nao reiniciar."""
    roteiro = [hb(i, regiao="DENTRO_ALCANCE" if i < 8 or i > 12 else "FORA_ALCANCE",
                  rssi1=-55.0 if i < 8 or i > 12 else -90.0) for i in range(1, 22)]

    a = novo_servidor(tmp_path, banco)
    for d in roteiro[:10]:
        enviar(a, d)
    # ---- o servidor cai aqui; um novo processo sobe com o mesmo banco ----
    with redirect_stdout(io.StringIO()) as saida:
        b = novo_servidor(tmp_path, banco)
    assert "RECUPERADA" in saida.getvalue()
    assert b.sessoes[ALUNO_A].id == a.sessoes[ALUNO_A].id
    for d in roteiro[10:]:
        enviar(b, d)

    ref = novo_servidor(tmp_path, BancoMemoria(lambda *_: None))
    for d in roteiro:
        enviar(ref, d)
    rb, rr = b.sessoes[ALUNO_A].ultimo_resultado, ref.sessoes[ALUNO_A].ultimo_resultado
    assert rb.estado == rr.estado
    assert rb.acumulado_s == pytest.approx(rr.acumulado_s)
    assert rb.ausencia_usada_s == pytest.approx(rr.ausencia_usada_s)


def test_depois_de_reiniciar_repetida_continua_sendo_repetida(tmp_path, banco):
    a = novo_servidor(tmp_path, banco)
    for i in range(1, 6):
        enviar(a, hb(i))
    with redirect_stdout(io.StringIO()):
        b = novo_servidor(tmp_path, banco)
    saida = enviar(b, hb(4))
    assert "REPETIDA" in saida
    assert b.sessoes[ALUNO_A].contagem["aceitos"] == 5


def test_aviso_ja_enviado_nao_e_reenviado_depois_de_reiniciar(tmp_path, banco):
    a = novo_servidor(tmp_path, banco)
    for i in range(1, 4):
        enviar(a, hb(i))
    for i in range(4, 12):                                # sai e fica fora: aviso 1 (24 s)
        enviar(a, hb(i, regiao="FORA_ALCANCE", rssi1=None))
    enviados = {m["tipo"] for t, m, _ in a.cliente.publicados if "/aviso/" in t}
    assert enviados
    with redirect_stdout(io.StringIO()):
        b = novo_servidor(tmp_path, banco)
    enviar(b, hb(12, regiao="FORA_ALCANCE", rssi1=None))
    reenviados = {m["tipo"] for t, m, _ in b.cliente.publicados if "/aviso/" in t}
    assert not (reenviados & enviados)


# ---------------------------------------------------------------- sensores
def test_sensor_do_celular_e_aceito_e_gravado(s, banco):
    enviar(s, sensor(1, nivel=0.42), "sensor")
    assert banco.sensores[0]["bateria"] == 0.42 and banco.sensores[0]["parado"] is False
    assert s.bateria[ALUNO_A] == (0.42, False)


def test_sensor_repetido_nao_e_gravado_duas_vezes(s, banco):
    enviar(s, sensor(1), "sensor")
    enviar(s, sensor(1), "sensor")
    assert len(banco.sensores) == 1


def test_sensor_em_nome_de_outro_e_recusado(s, banco):
    saida = enviar(s, sensor(1, aluno=ALUNO_B), "sensor", chave=CHAVE_A)
    assert "IDENTIDADE TROCADA" in saida and not banco.sensores


# ---------------------------------------------------------------- silêncio
def test_silencio_com_bateria_baixa_diz_que_e_bateria(s):
    enviar(s, hb(1))
    enviar(s, sensor(1, nivel=0.03), "sensor")
    s.ultimo_contato[ALUNO_A] = time.time() - 60
    s.parar.set()                                 # o laço roda uma vez só
    with redirect_stdout(io.StringIO()) as saida:
        s.parar.wait = lambda _t, _f=iter([False, True]): next(_f)
        s._vigiar()
    assert "SILÊNCIO" in saida.getvalue() and "BATERIA" in saida.getvalue()


def test_ancora_que_ninguem_ouve_e_avisada(s):
    enviar(s, hb(1))
    s.ancora_ouvida["anc-pc-1"] = time.time() - 60
    with redirect_stdout(io.StringIO()) as saida:
        s.parar.wait = lambda _t, _f=iter([False, True]): next(_f)
        s._vigiar()
    assert "ÂNCORA MUDA" in saida.getvalue()


# ---------------------------------------------------------------- atuador
def test_comando_sai_assinado_e_dentro_do_contrato(s, banco):
    enviar(s, hb(1))
    with redirect_stdout(io.StringIO()):
        cid = s.enviar_comando(ALUNO_A, "chamar")
    topico, msg, _ = s.cliente.publicados[-1]
    assert topico.endswith(f"/comando/{ALUNO_A}")
    assert not list(schema("presenca.comando.v1").iter_errors(msg))
    assert msg["comandoId"] == cid and banco.comandos[cid]["de"] == "servidor"


def test_comando_para_aluno_sem_aula_nao_sai(s):
    with redirect_stdout(io.StringIO()):
        assert s.enviar_comando(ALUNO_B, "vibrar") is None


def test_confirmacao_do_celular_fecha_o_laco(s, banco):
    enviar(s, hb(1))
    with redirect_stdout(io.StringIO()):
        cid = s.enviar_comando(ALUNO_A, "vibrar")
    ack = {"eventType": "presenca.comando.ack.v1", "comandoId": cid, "aluno": ALUNO_A,
           "resultado": "executado", "emMs": 1}
    saida = enviar(s, ack, "comando_ack", sufixo=f"/{ALUNO_A}")
    assert "CONFIRMOU" in saida and banco.comandos[cid]["resultado"] == "executado"


def test_confirmacao_forjada_por_outro_aluno_e_recusada(s, banco):
    enviar(s, hb(1))
    with redirect_stdout(io.StringIO()):
        cid = s.enviar_comando(ALUNO_A, "chamar")
    ack = {"eventType": "presenca.comando.ack.v1", "comandoId": cid, "aluno": ALUNO_A,
           "resultado": "respondido", "emMs": 1}
    saida = enviar(s, ack, "comando_ack", chave=CHAVE_B, sufixo=f"/{ALUNO_A}")
    assert "RECUSADA" in saida and banco.comandos[cid]["resultado"] is None


# ---------------------------------------------------------------- relatório
def test_relatorio_tem_nome_do_cadastro_e_respeita_o_contrato(s):
    cad = {"eventType": "presenca.cadastro.v1", "aluno": ALUNO_A, "turma": TURMA,
           "nome": "Maria Souza", "matricula": "202301234", "emMs": 1}
    enviar(s, cad, "cadastro", sufixo=f"/{ALUNO_A}")
    for i in range(1, 6):
        enviar(s, hb(i))
        enviar(s, hb(i, aluno=ALUNO_B, rssi1=None, regiao="FORA_ALCANCE"))
    rel = s.montar_relatorio(TURMA)
    assert not list(schema("presenca.relatorio.v1").iter_errors(rel))
    alunos = {x["aluno"]: x for x in rel["aulas"][0]["alunos"]}
    assert alunos[ALUNO_A]["nome"] == "Maria Souza" and alunos[ALUNO_B]["nome"] is None
    assert rel["aulas"][0]["emAndamento"]


def test_relatorio_e_publicado_retido_e_assinado(s):
    enviar(s, hb(1))
    s._publicar_relatorios()
    topico, msg, retido = s.cliente.publicados[-1]
    assert topico.endswith(f"/relatorio/{TURMA}") and retido and msg["turma"] == TURMA


def test_csv_abre_no_excel_em_portugues():
    rel = {"aulas": [{"aulaId": "demo-1", "inicioMs": 1_763_600_000_000, "alunos": [
        {"aluno": ALUNO_A, "nome": "Ana", "matricula": "1", "estado": "PRESENTE", "percentual": 87.5,
         "aprovado": True, "dentroS": 100.25, "perdoadoS": 5.0, "mensagens": 24,
         "celularParado": False, "bateria": 0.8}]}]}
    linhas = relatorio.csv(rel).splitlines()
    assert linhas[0].split(";")[:3] == ["aula", "inicio", "aluno"]
    assert ";87,5;presente;100,2;" in linhas[1] or ";87,5;presente;100,3;" in linhas[1]
    assert linhas[1].endswith(";não;80 %")


# ---------------------------------------------------------------- 2 âncoras
def test_duas_ancoras_perto_de_qualquer_uma_e_dentro():
    """O Marco 4 roda com uma ancora, mas a regra ja aceita mais (a ESP32)."""
    cfg2 = json.loads(json.dumps(CFG))
    cfg2["sala"]["ancoras"]["anc-pc-2"] = [3, 0]
    sala = Sala.de_config(cfg2)
    assert len(sala.ancoras) == 2

    def h(regiao, r1, r2):
        return {"state": regiao, "ancoras": [{"id": "anc-pc-1", "rssi": r1}, {"id": "anc-pc-2", "rssi": r2}]}
    assert classificar(h("DENTRO_ALCANCE", None, -55.0), sala)[0] == DENTRO
    assert classificar(h("FORA_ALCANCE", -90.0, None), sala)[0] == FORA_DA_SALA
    assert classificar(h("INDETERMINADA", -60.0, -60.0), sala)[0] == NEUTRO


def test_heartbeat_ouvindo_o_esp32_e_aceito_com_o_token_dele(s):
    saida = enviar(s, hb(1, rssi1=None, rssi2=-52.0))
    assert "RECUSADA" not in saida and s.sessoes[ALUNO_A].contagem["aceitos"] == 1


def test_cadastro_no_topico_de_outro_aluno_e_recusado(s, banco):
    cad = {"eventType": "presenca.cadastro.v1", "aluno": ALUNO_A, "turma": TURMA,
           "nome": "Intruso", "matricula": "", "emMs": 1}
    saida = enviar(s, cad, "cadastro", sufixo=f"/{ALUNO_B}")
    assert "IDENTIDADE TROCADA" in saida
    assert not banco.ident


def test_cadastro_retido_reentregue_nao_conta_como_sinal_de_vida(s):
    cad = {"eventType": "presenca.cadastro.v1", "aluno": ALUNO_A, "turma": TURMA,
           "nome": "Ana", "matricula": "", "emMs": 1}
    topico = f"{CFG['topico_cadastro']}/{ALUNO_A}"

    class Msg:
        pass
    m = Msg()
    m.topic, m.retain = topico, True
    m.payload = seg.envelopar(CHAVES[ALUNO_A], ALUNO_A, topico, cad).encode()
    with redirect_stdout(io.StringIO()) as saida:
        s._ao_receber(None, None, m)
    assert "retido no broker" in saida.getvalue()
    assert ALUNO_A not in s.ultimo_contato


# ---------------------------------------------------------------- LGPD
def test_apagar_aluno_remove_tudo_dele_e_so_dele(s, banco):
    enviar(s, {"eventType": "presenca.cadastro.v1", "aluno": ALUNO_A, "turma": TURMA,
               "nome": "Ana", "matricula": "", "emMs": 1}, "cadastro", sufixo=f"/{ALUNO_A}")
    for i in range(1, 4):
        enviar(s, hb(i))
        enviar(s, hb(i, aluno=ALUNO_B))
    s.esquecer_aluno(ALUNO_A)
    assert (f"{CFG['topico_cadastro']}/{ALUNO_A}", None, True) in s.cliente.publicados  # retido apagado
    assert ALUNO_A not in s.sessoes
    assert all(e["aluno"] == ALUNO_B for e in banco.eventos)
    assert not any(k[0] == ALUNO_A for k in banco.ident)
    assert all(v["aluno"] == ALUNO_B for v in banco.sessoes.values())


# ---------------------------------------------------------------- PostgreSQL real
def _pg():
    try:
        b = Banco(os.environ.get("PRESENCA_DSN", CFG["banco"]["dsn"]), avisar=lambda *_: None)
    except Exception:  # noqa: BLE001
        return None
    return b if b.online else None


pg = pytest.mark.skipif(_pg() is None, reason="PostgreSQL do docker compose não está no ar")


@pg
def test_pg_grava_recupera_e_apaga(tmp_path):
    b = _pg()
    b.apagar_aluno(ALUNO_A)
    a = novo_servidor(tmp_path, b)
    for i in range(1, 8):
        enviar(a, hb(i, aula="pg-teste"))
    enviar(a, sensor(1), "sensor")
    sid = a.sessoes[ALUNO_A].id
    assert b.esperar_gravar()
    assert len(b.eventos_da_sessao(sid)) == 7
    with redirect_stdout(io.StringIO()):
        c = novo_servidor(tmp_path, b)
    assert c.sessoes[ALUNO_A].id == sid and len(c.sessoes[ALUNO_A].log) == 7
    rel = c.montar_relatorio(TURMA)
    assert any(x["aluno"] == ALUNO_A for aula in rel["aulas"] for x in aula["alunos"])
    n = b.apagar_aluno(ALUNO_A)
    assert n["eventos"] == 7 and n["sensores"] == 1


@pg
def test_pg_banco_fora_guarda_na_fila_e_grava_quando_volta():
    b = _pg()
    b.apagar_aluno(ALUNO_B)
    b.aluno_visto(ALUNO_B, "00", DEVICE_B)
    assert b.esperar_gravar()
    b.conexao.close()                         # o banco "cai"
    b._ultima_tentativa = time.time() + 3600  # e ainda nao deu tempo de reconectar
    agora = datetime.now(timezone.utc)
    for i in range(3):
        b.recusa(agora, "t", "TESTE-FILA", ALUNO_B)
    time.sleep(0.3)
    assert len(b.fila) == 3                   # nada se perdeu: esta na fila
    b._ultima_tentativa = 0                   # o banco "volta"
    assert b.esperar_gravar(8)
    n = b._ler("SELECT count(*) AS n FROM recusas WHERE motivo = 'TESTE-FILA' AND detalhe = %s", (ALUNO_B,))
    assert n[0]["n"] >= 3
    b._ler("DELETE FROM recusas WHERE motivo = 'TESTE-FILA' RETURNING 1")
    b.apagar_aluno(ALUNO_B)


class ConexaoTravada:
    """Um banco que nao responde (como o processo suspenso): cada comando demora."""

    closed = False

    def __init__(self, demora=3):
        self.demora = demora

    def execute(self, *a, **k):
        time.sleep(self.demora)
        return self

    def fetchall(self):
        return []

    def close(self):
        pass


@pg
def test_pg_banco_travado_nao_atrasa_as_mensagens(tmp_path):
    """Defeito achado no teste ao vivo: com o banco pausado, as mensagens
    esperavam a gravacao, chegavam atrasadas e o token vencia. Agora quem
    grava e uma thread propria: processar continua instantaneo."""
    b = _pg()
    real = b.conexao
    b.conexao = ConexaoTravada()
    try:
        s = novo_servidor(tmp_path, b)
        inicio = time.time()
        for i in range(1, 6):
            enviar(s, hb(i, aula="pg-travado"))
        assert time.time() - inicio < 1.0, "o processamento esperou o banco"
        assert s.sessoes[ALUNO_A].contagem["aceitos"] == 5
    finally:
        b.conexao = real
    assert b.esperar_gravar(30)
    b.apagar_aluno(ALUNO_A)


@pg
def test_pg_leitura_travada_desiste_no_tempo_limite():
    b = _pg()
    b.leitura = ConexaoTravada(demora=8)
    inicio = time.time()
    assert b.sessoes_da_turma("TRAVADA") is None       # "banco fora", sem prender
    assert time.time() - inicio < 4
    assert b.leitura is None                           # a presa foi abandonada
    assert b.sessoes_da_turma("TRAVADA") == []         # a proxima abre outra e funciona


@pg
def test_pg_relatorio_lento_nao_segura_as_mensagens(tmp_path):
    """O 2º defeito do teste ao vivo: o vigia montava o relatorio (le o banco)
    segurando a trava do servidor; banco travado = mensagens paradas = token
    vencido. Agora o relatorio le fora da trava."""
    b = _pg()
    s = novo_servidor(tmp_path, b)
    enviar(s, hb(1, aula="pg-relatorio"))
    turma = s.sessoes[ALUNO_A].turma
    b.leitura = ConexaoTravada(demora=8)
    vigia = threading.Thread(target=s._publicar_relatorios, daemon=True)
    vigia.start()
    time.sleep(0.2)                                    # o relatorio ja esta preso no banco
    inicio = time.time()
    for i in range(2, 7):
        enviar(s, hb(i, aula="pg-relatorio"))
    assert time.time() - inicio < 1.0, "as mensagens esperaram o relatorio"
    assert s.sessoes[ALUNO_A].contagem["aceitos"] == 6
    vigia.join(5)
    assert turma in s.turmas_sujas                     # tenta de novo no proximo ciclo
    assert b.esperar_gravar(10)
    b.apagar_aluno(ALUNO_A)
