"""
Projeto Presenca - Marco 3
SEGURANCA: quem fala, e se a mensagem e de quem diz ser.

Tres camadas, de fora para dentro:

  1. Canal cifrado (TLS) e autenticacao MQTT (usuario e senha por papel) -
     ficam no broker HiveMQ Cloud; aqui so se le a credencial (segredos.json).
  2. Identidade do dispositivo - cada aparelho tem um par de chaves Ed25519.
     Toda mensagem vai num envelope assinado (seguranca.envelope.v1). O
     pseudonimo do aluno e DERIVADO da chave publica: ninguem consegue falar
     em nome de tok-1234abcd sem ter a chave privada que gerou esse nome.
  3. Prova de proximidade - o token que a ancora anuncia por Bluetooth e um
     HMAC do relogio com um segredo que so a ancora e o servidor conhecem.
     O celular repassa o token que ouviu; o servidor confere se e o da janela
     atual. Heartbeat inventado em casa nao tem o token certo.

Nada aqui fala com a rede: e tudo funcao pura, testada em testes/.
"""

import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

TIPO_ENVELOPE = "seguranca.envelope.v1"
TOKEN_S = 12                 # a ancora troca o token a cada 12 s (projeto: 10 a 15 s)
TOKEN_BYTES = 4              # cabe no anuncio Bluetooth junto com "PRS1" e o numero
# Ao vivo: a janela atual, a anterior (atraso de rede) e a seguinte (relogio
# do notebook um pouco adiantado). Heartbeat que ficou na fila sem rede chega
# atrasado de verdade: para ele se aceita voltar ATRASO_FILA_JANELAS janelas.
JANELAS_AO_VIVO = 1
ATRASO_FILA_JANELAS = 4       # 4 x 12 s = 48 s > 30 s de fila no app


# ---------------------------------------------------------------------------
# Segredos locais (nunca vao para o git)
# ---------------------------------------------------------------------------
def carregar_segredos(caminho):
    """Le segredos.json. Sem ele, o servidor nao sobe: nao ha modo inseguro."""
    if not os.path.exists(caminho):
        raise SystemExit(
            f"Falta {caminho}.\n"
            "Copie segredos.exemplo.json para segredos.json e preencha com o "
            "endereço e as senhas do HiveMQ Cloud (ver README do marco-03).")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def chave_do_servidor(caminho):
    """Carrega a chave privada do servidor; cria na primeira vez."""
    if os.path.exists(caminho):
        with open(caminho, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    chave = Ed25519PrivateKey.generate()
    with open(caminho, "wb") as f:
        f.write(chave.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    return chave


def publica_hex(chave_privada):
    return chave_privada.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


# ---------------------------------------------------------------------------
# Identidade derivada da chave
# ---------------------------------------------------------------------------
def identidade_da_chave(chave_publica_hex):
    """(aluno, deviceId) que pertencem a esta chave publica.

    O mesmo calculo roda no celular (app/src/lib/identidade.ts). Como o nome
    sai do hash da chave, nao precisa de cadastro previo para provar que
    "tok-1234abcd" e dono desta chave - so de conferir a assinatura.
    """
    h = hashlib.sha256(bytes.fromhex(chave_publica_hex)).hexdigest()
    return f"tok-{h[:8]}", f"cel-{h[8:12]}"


# ---------------------------------------------------------------------------
# Envelope assinado
# ---------------------------------------------------------------------------
def _mensagem_assinada(topico, carga):
    # O topico entra na assinatura: uma mensagem valida para o aluno A nao
    # pode ser recolocada no topico do aluno B.
    return (topico + "\n" + carga).encode("utf-8")


def envelopar(chave_privada, de, topico, carga_dict):
    carga = json.dumps(carga_dict, separators=(",", ":"), ensure_ascii=False)
    assinatura = chave_privada.sign(_mensagem_assinada(topico, carga))
    return json.dumps({
        "eventType": TIPO_ENVELOPE,
        "de": de,
        "chavePublica": publica_hex(chave_privada),
        "carga": carga,
        "assinatura": assinatura.hex(),
    }, separators=(",", ":"), ensure_ascii=False)


class Recusa(Exception):
    """Mensagem recusada por seguranca. `motivo` e curto, para a tela."""

    def __init__(self, motivo, detalhe=""):
        super().__init__(motivo)
        self.motivo = motivo
        self.detalhe = detalhe


def abrir_envelope(topico, texto):
    """Confere o envelope e devolve (de, chave_publica_hex, carga_dict).

    Levanta Recusa quando: nao e envelope, a assinatura nao confere, ou a
    carga nao e JSON. Quem a chave e (e se ela pode falar ali) e decidido por
    quem chamou.
    """
    try:
        env = json.loads(texto)
    except (TypeError, ValueError):
        raise Recusa("não é JSON")
    if not isinstance(env, dict) or env.get("eventType") != TIPO_ENVELOPE:
        raise Recusa("SEM ASSINATURA", "mensagem fora do envelope assinado")
    try:
        chave = Ed25519PublicKey.from_public_bytes(bytes.fromhex(env["chavePublica"]))
        assinatura = bytes.fromhex(env["assinatura"])
        carga = env["carga"]
        de = env["de"]
    except (KeyError, ValueError, TypeError):
        raise Recusa("ENVELOPE MALFORMADO")
    try:
        chave.verify(assinatura, _mensagem_assinada(topico, carga))
    except InvalidSignature:
        raise Recusa("ASSINATURA FALSA", "a assinatura não confere com a chave e o tópico")
    try:
        dado = json.loads(carga)
    except ValueError:
        raise Recusa("carga não é JSON")
    return de, env["chavePublica"], dado


# ---------------------------------------------------------------------------
# Token da ancora
# ---------------------------------------------------------------------------
def janela(agora_s=None, periodo=TOKEN_S):
    return int((time.time() if agora_s is None else agora_s) // periodo)


def token_da_ancora(segredo_hex, ancora, num_janela):
    """4 bytes de HMAC-SHA256(segredo, "anc-pc-1|<janela>"), em hex.

    E o que ancora.py anuncia por Bluetooth naquela janela de 12 s.
    """
    msg = f"{ancora}|{num_janela}".encode("utf-8")
    return hmac.new(bytes.fromhex(segredo_hex), msg, hashlib.sha256).digest()[:TOKEN_BYTES].hex()


def token_valido(segredo_hex, ancora, token, agora_s=None, atras=JANELAS_AO_VIVO):
    """O token e de uma janela entre `atras` janelas atras e a proxima?"""
    if not isinstance(token, str):
        return False
    j = janela(agora_s)
    return any(hmac.compare_digest(token_da_ancora(segredo_hex, ancora, j + d), token)
               for d in range(-atras, 2))


def novo_segredo():
    return secrets.token_hex(32)
