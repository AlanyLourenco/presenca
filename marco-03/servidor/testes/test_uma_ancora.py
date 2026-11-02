"""Prototipo 1: com uma ancora so, vale a regiao decidida no celular."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from permanencia import DENTRO, FORA_DA_SALA, NEUTRO, Sala, classificar  # noqa: E402

with open(os.path.join(os.path.dirname(__file__), "..", "config.exemplo.json"), encoding="utf-8") as f:
    SALA = Sala.de_config(json.load(f))


def hb(regiao, rssi):
    return {"state": regiao, "ancoras": [{"id": "anc-pc-1", "rssi": rssi}]}


def test_perto_do_notebook_e_dentro():
    assert classificar(hb("DENTRO_ALCANCE", -55.0), SALA) == (DENTRO, None)


def test_longe_ou_sem_sinal_e_fora():
    assert classificar(hb("FORA_ALCANCE", -80.0), SALA) == (FORA_DA_SALA, None)
    assert classificar(hb("FORA_ALCANCE", None), SALA) == (FORA_DA_SALA, None)


def test_sem_calibracao_ainda_e_neutro():
    assert classificar(hb("INDETERMINADA", -60.0), SALA) == (NEUTRO, None)
