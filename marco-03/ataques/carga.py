#!/usr/bin/env python3
"""
Projeto Presenca - Marco 3
CARGA: quantos aparelhos o sistema acompanha ao mesmo tempo?

Simula N celulares de verdade: cada um com a PROPRIA chave Ed25519, mandando
heartbeat assinado com o token atual da ancora (este script conhece o segredo
da ancora so para fazer o papel de "celular que esta ouvindo a ancora").
Mede, para cada um, quanto tempo o servidor leva para devolver o estado
assinado, e quantas respostas se perdem.

    python carga.py 10            # 10 celulares, 30 s
    python carga.py 50 --tempo 60
    python carga.py 80 --conexoes  # uma conexao MQTT por celular (como no real)
    python carga.py 200 --sem-rede # so o servidor, sem broker: quanto ele aguenta

Rode o servidor com --quieto para ele nao gastar tempo imprimindo cada linha:
    python servidor.py --quieto

Por que a ANCORA nao e o limite: ela so transmite (farol). Um anuncio
Bluetooth e ouvido por todos os celulares em volta ao mesmo tempo, como
uma lampada e vista por todos na sala. Quem pode limitar e o caminho de
volta: broker e servidor. E isso que este teste mede.
"""

import argparse
import json
import os
import statistics
import sys
import threading
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "servidor"))
sys.path.insert(0, AQUI)
from seguranca import (  # noqa: E402
    abrir_envelope, envelopar, identidade_da_chave, janela, publica_hex, token_da_ancora,
)
from ataques import BASE, SALA, T_HEARTBEAT, cloud, conectar, seg  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

INTERVALO_S = 0.5            # o mesmo do app (heartbeat comprimido da demonstracao)
HEARTBEAT_REAL_S = 60        # no sistema real: 60-90 s


class Celular:
    def __init__(self, n):
        self.chave = Ed25519PrivateKey.generate()
        self.aluno, self.device = identidade_da_chave(publica_hex(self.chave))
        self.boot = f"{n:04x}"[-4:]
        self.seq = 0
        self.enviado_em = {}        # seq -> instante do envio
        self.latencias = []
        self.respostas = 0

    def heartbeat(self, segredo):
        self.seq += 1
        token = token_da_ancora(segredo, "anc-pc-1", janela())
        rssi = -50.0
        dado = {
            "eventType": "presenca.heartbeat.v2",
            "eventId": f"{self.device}#{self.boot}#{self.seq}",
            "deviceId": self.device, "entityId": SALA, "aluno": self.aluno, "bootId": self.boot,
            "eventTimeMs": self.seq * 500, "medidoEmMs": int(time.time() * 1000),
            "sequence": self.seq, "value": rssi, "unit": "dBm", "state": "DENTRO_ALCANCE",
            "ancoras": [{"id": "anc-pc-1", "rssi": rssi, "token": token}],
            "amostrasInvalidas": 0, "bufferizado": False, "anomaliaInjetada": "nenhuma",
        }
        self.enviado_em[self.seq] = time.time()
        return envelopar(self.chave, self.aluno, T_HEARTBEAT, dado)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int, help="quantos celulares simular")
    ap.add_argument("--tempo", type=float, default=30, help="segundos de teste")
    ap.add_argument("--conexoes", action="store_true", help="uma conexão MQTT por celular")
    ap.add_argument("--ws", action="store_true")
    ap.add_argument("--sem-rede", action="store_true", help="mede só o servidor, sem broker")
    args = ap.parse_args()
    if args.sem_rede:
        return sem_rede(args)

    segredo = seg()["ancoras"]["anc-pc-1"]
    celulares = [Celular(i) for i in range(args.n)]
    por_aluno = {c.aluno: c for c in celulares}
    trava = threading.Lock()

    def ao_receber(cli, ud, msg):
        agora = time.time()
        try:
            de, chave, est = abrir_envelope(msg.topic, msg.payload.decode())
        except Exception:
            return
        c = por_aluno.get(est.get("aluno"))
        if not c or msg.retain:
            return
        with trava:
            c.respostas += 1
            # a resposta corresponde ao heartbeat mais antigo ainda sem resposta
            if c.enviado_em:
                seq = min(c.enviado_em)
                c.latencias.append(agora - c.enviado_em.pop(seq))

    n_con = args.n if args.conexoes else 1
    clientes = []
    print(f"Conectando {n_con} cliente(s) MQTT ao EMQX Cloud…")
    for i in range(n_con):
        cli = cloud()
        ok, motivo = conectar(cli)
        if not ok:
            sys.exit(f"cliente {i + 1}: {motivo}")
        cli.on_message = ao_receber
        clientes.append(cli)
    clientes[0].subscribe(f"{BASE}/{SALA}/estado/+", qos=0)
    time.sleep(1.5)                                    # deixa os retidos antigos passarem

    print(f"Simulando {args.n} celulares, 1 heartbeat a cada {INTERVALO_S} s, por {args.tempo:.0f} s…")
    inicio = time.time()
    rodada = 0
    enviados = 0
    while time.time() - inicio < args.tempo:
        alvo = inicio + rodada * INTERVALO_S
        time.sleep(max(0, alvo - time.time()))
        for i, c in enumerate(celulares):
            cli = clientes[i % n_con]
            with trava:
                texto = c.heartbeat(segredo)
            cli.publish(T_HEARTBEAT, texto, qos=0)
            enviados += 1
        rodada += 1
    time.sleep(3)                                      # ultimas respostas

    lat = sorted(x for c in celulares for x in c.latencias)
    respostas = sum(c.respostas for c in celulares)
    duracao = time.time() - inicio - 3
    taxa = enviados / duracao
    print()
    print(f"══ Resultado: {args.n} celulares ══")
    print(f"  heartbeats enviados:  {enviados}  ({taxa:.0f} por segundo)")
    print(f"  estados de volta:     {respostas}  ({100 * respostas / max(1, enviados):.1f} %)")
    if lat:
        p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] * 1000  # noqa: E731
        print(f"  ida e volta (celular → broker → servidor → broker → celular):")
        print(f"     mediana {p(0.5):.0f} ms · 95 % abaixo de {p(0.95):.0f} ms · pior {lat[-1] * 1000:.0f} ms")
    equivalente = taxa * HEARTBEAT_REAL_S
    print(f"  Na aula real o heartbeat é a cada {HEARTBEAT_REAL_S} s: esta taxa equivale a "
          f"~{equivalente:.0f} celulares.")
    for cli in clientes:
        cli.loop_stop()
        cli.disconnect()


def sem_rede(args):
    """Chama o servidor direto (sem broker) com N celulares por `tempo` s de aula."""
    import io
    from contextlib import redirect_stdout
    from datetime import datetime, timezone
    import servidor as srv

    class Nulo:
        publicados = 0

        def publish(self, *a, **k):
            Nulo.publicados += 1

    with open(os.path.join(RAIZ, "servidor", "config.exemplo.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    segredo = "ab" * 32
    s = srv.Servidor(cfg, segredos={"broker": "-", "servidor": {"usuario": "-", "senha": "-"},
                                    "ancoras": {"anc-pc-1": segredo}},
                     chave=Ed25519PrivateKey.generate())
    s.cliente = Nulo()
    s.log = open(os.devnull, "w", encoding="utf-8")
    s.quieto, s.painel_a_cada = True, 0
    celulares = [Celular(i) for i in range(args.n)]
    rodadas = int(args.tempo / INTERVALO_S)
    tempos = []
    with redirect_stdout(io.StringIO()):
        for _ in range(rodadas):
            for c in celulares:
                texto = c.heartbeat(segredo).encode()
                t0 = time.perf_counter()
                s._processar(texto, datetime.now(timezone.utc), T_HEARTBEAT)
                tempos.append(time.perf_counter() - t0)
    tempos.sort()
    media = statistics.mean(tempos)
    print(f"══ Servidor sem rede: {args.n} celulares × {rodadas} heartbeats ({args.tempo:.0f} s de aula) ══")
    print(f"  aceitos: {sum(len(x.log) for x in s.sessoes.values())} de {len(tempos)} · "
          f"recusados: {sum(x.contagem['recusados'] for x in s.sessoes.values())}")
    print(f"  por mensagem (abre envelope, confere assinatura e token, recalcula a aula, assina a resposta):")
    print(f"     média {media * 1000:.2f} ms · 95 % abaixo de {tempos[int(0.95 * len(tempos))] * 1000:.2f} ms")
    capacidade = 1 / media
    print(f"  ≈ {capacidade:.0f} mensagens por segundo num núcleo deste notebook")
    print(f"  com heartbeat a cada {HEARTBEAT_REAL_S} s (aula real): ≈ {capacidade * HEARTBEAT_REAL_S:.0f} celulares")


if __name__ == "__main__":
    main()
