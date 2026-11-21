"""
Projeto Presenca - Marco 4
PERSISTENCIA: PostgreSQL + TimescaleDB (esquema em ../banco/schema.sql).

Dois objetivos, nesta ordem:

  1. Nada se perde. Toda mensagem aceita, recusada, todo sensor e todo comando
     vai para o banco. Se o banco cair no meio da aula, as gravacoes ficam
     numa FILA em memoria e entram, na ordem, quando ele voltar. O servidor
     nunca para de decidir a presenca por causa do banco.
  2. A aula sobrevive ao reinicio do servidor. O estado de cada sessao e
     DERIVADO do log de eventos (decisao 7 do projeto: acumulador calculado
     retroativamente), entao recuperar e so reler os eventos da sessao aberta.

Duas implementacoes com a mesma interface:
  - Banco         o PostgreSQL de verdade (psycopg 3)
  - BancoMemoria  listas em memoria: testes e modo "sem banco"
"""

import json
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:          # sem psycopg: so o BancoMemoria funciona
    psycopg = None

DSN_PADRAO = "postgresql://presenca:presenca@localhost:55432/presenca"
MAX_FILA = 50_000            # ~70 h de um celular a cada 5 s; depois, descarta o mais antigo
ESPERA_RECONEXAO_S = 5
LEITURA_LIMITE_S = 3        # leitura que passa disso = banco travado: desiste, nao prende ninguem


def _agora():
    return datetime.now(timezone.utc)


class Banco:
    """PostgreSQL com fila de gravacao para quedas do banco.

    Duas conexoes, de proposito:
      - a de GRAVACAO e usada so por uma thread propria (o "escritor"). Quem
        recebe as mensagens so poe na fila e segue: se o banco travar ou cair,
        a presenca continua sendo decidida e os tokens nao vencem esperando.
      - a de LEITURA (relatorio, recuperacao, API) e aberta sob demanda e
        cada consulta roda numa thread com tempo limite: banco travado (ex.:
        processo suspenso) devolve "fora" em 3 s em vez de prender quem leu.
    A fila tem trava propria: enfileirar nunca espera uma leitura.
    """

    def __init__(self, dsn=DSN_PADRAO, avisar=print):
        if psycopg is None:
            raise RuntimeError("psycopg ausente: pip install \"psycopg[binary]\"")
        self.dsn = dsn
        self.avisar = avisar
        self.conexao = None              # gravacao (so o escritor usa)
        self.leitura = None              # leitura
        self.fila = deque()
        self.descartados = 0
        self.trava = threading.RLock()   # protege a conexao de leitura
        self.trava_fila = threading.Lock()
        self._sinal = threading.Condition(threading.Lock())
        self._ultima_tentativa = 0.0
        self._fora_avisado = False
        self.conexao = self._abrir("gravação")
        self._fora_avisado = self.conexao is None
        threading.Thread(target=self._escritor, daemon=True, name="banco-escritor").start()

    # -- conexao -----------------------------------------------------------------
    @property
    def online(self):
        return self.conexao is not None and not self.conexao.closed

    def _abrir(self, para):
        try:
            return psycopg.connect(self.dsn, autocommit=True, connect_timeout=3, row_factory=dict_row,
                                   keepalives=1, keepalives_idle=5, keepalives_interval=2,
                                   keepalives_count=2)
        except Exception as e:  # noqa: BLE001 - qualquer falha = banco fora
            if para == "gravação" and not self._fora_avisado:
                self.avisar(f"banco fora do ar ({str(e).splitlines()[0][:90]}); "
                            f"as gravações esperam na fila")
            return None

    def _garantir(self):
        """So o escritor chama: (re)abre a conexao de gravacao, com espera entre tentativas."""
        if self.online:
            return True
        if time.time() - self._ultima_tentativa < ESPERA_RECONEXAO_S:
            return False
        self._ultima_tentativa = time.time()
        self.conexao = self._abrir("gravação")
        if self.conexao is None:
            self._fora_avisado = True
            return False
        if self._fora_avisado:
            self.avisar(f"banco de volta: gravando {len(self.fila)} pendente(s)")
        self._fora_avisado = False
        return True

    def criar_esquema(self, caminho_sql):
        with open(caminho_sql, encoding="utf-8") as f:
            sql = f.read()
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(sql)

    # -- gravacao com fila -------------------------------------------------------
    def _gravar(self, sql, params):
        """Nao toca no banco: so enfileira e acorda o escritor. Nunca bloqueia."""
        with self.trava_fila:
            self.fila.append((sql, params))
            if len(self.fila) > MAX_FILA:
                self.fila.popleft()
                self.descartados += 1
        with self._sinal:
            self._sinal.notify()

    def _escritor(self):
        while True:
            with self._sinal:
                if not self.fila:
                    self._sinal.wait(1.0)
            if self.fila:
                self._esvaziar()

    def _esvaziar(self):
        if not self._garantir():
            return
        while self.fila:
            sql, params = self.fila[0]
            try:
                self.conexao.execute(sql, params)
            except (psycopg.OperationalError, psycopg.InterfaceError) as e:
                self.avisar(f"banco caiu: {str(e).splitlines()[0][:90]}; "
                            f"{len(self.fila)} gravação(ões) na fila")
                try:
                    self.conexao.close()
                except Exception:  # noqa: BLE001
                    pass
                self.conexao = None
                self._fora_avisado = True
                self._ultima_tentativa = time.time()
                return
            except psycopg.Error as e:
                # erro de DADO (nao de conexao): nao adianta repetir
                self.avisar(f"gravação recusada pelo banco: {str(e).splitlines()[0][:120]}")
            with self.trava_fila:
                if self.fila:
                    self.fila.popleft()

    def tentar_esvaziar(self):
        """Acorda o escritor (o banco pode ter voltado)."""
        with self._sinal:
            self._sinal.notify()

    def esperar_gravar(self, segundos=5.0):
        """Testes e encerramento: espera a fila esvaziar. Devolve True se esvaziou."""
        fim = time.time() + segundos
        while self.fila and time.time() < fim:
            self.tentar_esvaziar()
            time.sleep(0.05)
        return not self.fila

    def _conexao_leitura(self):
        if self.leitura is None or self.leitura.closed:
            self.leitura = self._abrir("leitura")
        return self.leitura

    def _na_leitura(self, funcao, limite=LEITURA_LIMITE_S):
        """Roda funcao(conexao) numa thread e espera no maximo `limite` s.

        Banco travado: a thread fica presa la (daemon), a conexao e abandonada
        e quem pediu recebe None ("banco fora") a tempo de seguir a vida."""
        resultado = {}

        def trabalho():
            with self.trava:
                c = self._conexao_leitura()
            resultado["c"] = c
            if c is None:
                return
            try:
                resultado["r"] = funcao(c)
            except (psycopg.OperationalError, psycopg.InterfaceError):
                with self.trava:
                    if self.leitura is c:
                        self.leitura = None

        th = threading.Thread(target=trabalho, daemon=True, name="banco-leitura")
        th.start()
        th.join(limite)
        if th.is_alive():
            with self.trava:
                presa = resultado.get("c")
                if presa is None or self.leitura is presa:
                    self.leitura = None          # presa: a proxima leitura abre outra
            return None
        return resultado.get("r")

    def _ler(self, sql, params=()):
        return self._na_leitura(lambda c: c.execute(sql, params).fetchall())

    # -- escritas ----------------------------------------------------------------
    def aluno_visto(self, aluno, chave, device):
        self._gravar(
            "INSERT INTO alunos (aluno, chave_publica, device_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (aluno) DO UPDATE SET ultimo_visto = now()",
            (aluno, chave, device))

    def identificacao(self, aluno, chave, device, turma, nome, matricula):
        self.aluno_visto(aluno, chave, device)
        self._gravar(
            "INSERT INTO identificacao (aluno, turma, nome, matricula) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (aluno, turma) DO UPDATE SET nome = EXCLUDED.nome, "
            "matricula = EXCLUDED.matricula, informado_em = now()",
            (aluno, turma, nome, matricula))

    def salvar_sessao(self, s):
        """s: dict com as colunas de `sessoes` (ver Sessao.para_banco)."""
        cols = list(s)
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
        valores = [Jsonb(v) if c == "contagem" else v for c, v in s.items()]
        self._gravar(
            f"INSERT INTO sessoes ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
            f"ON CONFLICT (id) DO UPDATE SET {sets}, atualizada_em = now()",
            valores)

    def evento(self, e):
        self._gravar(
            "INSERT INTO eventos (recebido_em, sessao, aluno, turma, event_id, boot_id, sequencia, "
            "classificacao, t_linha, classe, estado, regiao, rssi, bufferizado, carga) "
            "VALUES (%(recebido_em)s, %(sessao)s, %(aluno)s, %(turma)s, %(event_id)s, %(boot_id)s, "
            "%(sequencia)s, %(classificacao)s, %(t_linha)s, %(classe)s, %(estado)s, %(regiao)s, "
            "%(rssi)s, %(bufferizado)s, %(carga)s)",
            {**e, "carga": Jsonb(e["carga"])})

    def sensor(self, s):
        self._gravar(
            "INSERT INTO sensores (recebido_em, aluno, turma, sensor_id, movimento, parado, "
            "bateria, carregando, carga) VALUES (%(recebido_em)s, %(aluno)s, %(turma)s, "
            "%(sensor_id)s, %(movimento)s, %(parado)s, %(bateria)s, %(carregando)s, %(carga)s)",
            {**s, "carga": Jsonb(s["carga"])})

    def recusa(self, recebido_em, topico, motivo, detalhe):
        self._gravar("INSERT INTO recusas (recebido_em, topico, motivo, detalhe) "
                     "VALUES (%s, %s, %s, %s)", (recebido_em, topico, motivo, detalhe))

    def comando(self, c):
        self._gravar(
            "INSERT INTO comandos (comando_id, aluno, turma, tipo, texto, de) "
            "VALUES (%(comandoId)s, %(aluno)s, %(turma)s, %(tipo)s, %(texto)s, %(de)s) "
            "ON CONFLICT (comando_id) DO NOTHING", c)

    def confirmacao(self, comando_id, resultado):
        self._gravar("UPDATE comandos SET confirmado_em = now(), resultado = %s "
                     "WHERE comando_id = %s", (resultado, comando_id))

    # -- leituras ----------------------------------------------------------------
    def sessoes_abertas(self, horas=3):
        """Sessoes nao encerradas que mexeram nas ultimas `horas`: a aula em andamento."""
        return self._ler(
            "SELECT * FROM sessoes WHERE encerrada_em IS NULL AND atualizada_em > %s "
            "ORDER BY aberta_em", (_agora() - timedelta(hours=horas),)) or []

    def eventos_da_sessao(self, sessao):
        return self._ler(
            "SELECT event_id, boot_id, sequencia, classificacao, t_linha, classe, carga "
            "FROM eventos WHERE sessao = %s ORDER BY recebido_em", (sessao,)) or []

    def sessoes_da_turma(self, turma, limite_aulas=20):
        return self._ler(
            "WITH aulas AS (SELECT aula_id, min(aberta_em) AS inicio FROM sessoes "
            "  WHERE turma = %s GROUP BY aula_id ORDER BY inicio DESC LIMIT %s) "
            "SELECT s.*, i.nome, i.matricula, a.inicio AS aula_inicio "
            "FROM sessoes s JOIN aulas a USING (aula_id) "
            "LEFT JOIN identificacao i ON i.aluno = s.aluno AND i.turma = s.turma "
            "WHERE s.turma = %s ORDER BY a.inicio DESC, s.aluno",
            (turma, limite_aulas, turma))

    def resumo_sensores(self, sessao_ids):
        """Por sessao: o celular ficou parado a aula toda? ultima bateria."""
        if not sessao_ids:
            return {}
        linhas = self._ler(
            "SELECT s.id AS sessao, bool_and(x.parado) AS sempre_parado, count(x.*) AS n, "
            "  (array_agg(x.bateria ORDER BY x.recebido_em DESC))[1] AS bateria "
            "FROM sessoes s JOIN sensores x ON x.aluno = s.aluno "
            "  AND x.recebido_em BETWEEN s.aberta_em AND coalesce(s.encerrada_em, now()) "
            "WHERE s.id = ANY(%s) GROUP BY s.id", (list(sessao_ids),)) or []
        return {l["sessao"]: l for l in linhas}

    def historico_aluno(self, aluno):
        return self._ler(
            "SELECT id, turma, aula_id, aberta_em, encerrada_em, estado, percentual, aprovado "
            "FROM sessoes WHERE aluno = %s ORDER BY aberta_em DESC", (aluno,))

    def apagar_aluno(self, aluno):
        """Direito de eliminacao (LGPD art. 18, VI): tudo o que se refere ao pseudonimo.

        Antes, espera a fila de gravacao: senao um evento ainda na fila
        recriaria o aluno depois de apagado."""
        self.esperar_gravar()

        def apagar(c):
            n = {}
            for tabela in ("eventos", "sensores", "comandos", "sessoes", "identificacao", "alunos"):
                n[tabela] = c.execute(f"DELETE FROM {tabela} WHERE aluno = %s", (aluno,)).rowcount
            return n
        return self._na_leitura(apagar, limite=10)

    def estatisticas(self):
        """Tamanho e compressao das tabelas temporais (para o relatorio e o video)."""
        return self._ler(
            "SELECT h.hypertable_name AS tabela, "
            "  (SELECT count(*) FROM timescaledb_information.chunks c "
            "     WHERE c.hypertable_name = h.hypertable_name) AS pedacos, "
            "  pg_size_pretty(hypertable_size(format('%%I', h.hypertable_name)::regclass)) AS tamanho "
            "FROM timescaledb_information.hypertables h ORDER BY 1")


# ---------------------------------------------------------------------------
class BancoMemoria:
    """Mesma interface, em memoria. Os testes usam; o servidor cai nele com --sem-banco."""

    online = True

    def esperar_gravar(self, segundos=5.0):
        return True

    def __init__(self, avisar=print):
        self.avisar = avisar
        self.fila = deque()
        self.descartados = 0
        self.alunos, self.ident, self.sessoes, self.comandos = {}, {}, {}, {}
        self.eventos, self.sensores, self.recusas = [], [], []

    def tentar_esvaziar(self):
        pass

    def aluno_visto(self, aluno, chave, device):
        self.alunos.setdefault(aluno, {"aluno": aluno, "chave_publica": chave, "device_id": device})

    def identificacao(self, aluno, chave, device, turma, nome, matricula):
        self.aluno_visto(aluno, chave, device)
        self.ident[(aluno, turma)] = {"nome": nome, "matricula": matricula}

    def salvar_sessao(self, s):
        atual = self.sessoes.setdefault(s["id"], {"aberta_em": _agora(), "encerrada_em": None})
        atual.update(s)
        atual["atualizada_em"] = _agora()

    def evento(self, e):
        self.eventos.append(dict(e))

    def sensor(self, s):
        self.sensores.append(dict(s))

    def recusa(self, recebido_em, topico, motivo, detalhe):
        self.recusas.append({"recebido_em": recebido_em, "motivo": motivo, "detalhe": detalhe})

    def comando(self, c):
        self.comandos.setdefault(c["comandoId"], {**c, "resultado": None})

    def confirmacao(self, comando_id, resultado):
        if comando_id in self.comandos:
            self.comandos[comando_id]["resultado"] = resultado

    def sessoes_abertas(self, horas=3):
        limite = _agora() - timedelta(hours=horas)
        return [dict(s) for s in self.sessoes.values()
                if s.get("encerrada_em") is None and s["atualizada_em"] > limite]

    def eventos_da_sessao(self, sessao):
        return [e for e in self.eventos if e["sessao"] == sessao]

    def sessoes_da_turma(self, turma, limite_aulas=20):
        linhas = []
        inicios = {}
        for s in self.sessoes.values():
            if s.get("turma") == turma:
                a = s.get("aula_id")
                inicios[a] = min(inicios.get(a, s["aberta_em"]), s["aberta_em"])
        aulas = sorted(inicios, key=inicios.get, reverse=True)[:limite_aulas]
        for s in self.sessoes.values():
            if s.get("turma") == turma and s.get("aula_id") in aulas:
                i = self.ident.get((s["aluno"], turma), {})
                linhas.append({**s, "nome": i.get("nome"), "matricula": i.get("matricula"),
                               "aula_inicio": inicios[s.get("aula_id")]})
        return sorted(linhas, key=lambda l: (-l["aula_inicio"].timestamp(), l["aluno"]))

    def resumo_sensores(self, sessao_ids):
        r = {}
        for sid in sessao_ids:
            s = self.sessoes.get(sid)
            xs = [x for x in self.sensores if s and x["aluno"] == s["aluno"]]
            if xs:
                r[sid] = {"sempre_parado": all(x["parado"] for x in xs), "n": len(xs),
                          "bateria": xs[-1]["bateria"]}
        return r

    def historico_aluno(self, aluno):
        return [s for s in self.sessoes.values() if s["aluno"] == aluno]

    def apagar_aluno(self, aluno):
        n = {"eventos": sum(e["aluno"] == aluno for e in self.eventos)}
        self.eventos = [e for e in self.eventos if e["aluno"] != aluno]
        self.sensores = [x for x in self.sensores if x["aluno"] != aluno]
        self.sessoes = {k: v for k, v in self.sessoes.items() if v["aluno"] != aluno}
        self.ident = {k: v for k, v in self.ident.items() if k[0] != aluno}
        self.alunos.pop(aluno, None)
        return n

    def estatisticas(self):
        return [{"tabela": "eventos", "pedacos": 0, "tamanho": f"{len(self.eventos)} linhas (memória)"}]


def abrir_banco(cfg, avisar=print, forcar_memoria=False):
    """O banco do config, ou o de memoria se pedido / se nao houver psycopg."""
    if forcar_memoria or psycopg is None:
        if psycopg is None and not forcar_memoria:
            avisar("psycopg ausente: usando banco em MEMÓRIA (nada fica gravado)")
        return BancoMemoria(avisar)
    return Banco(cfg.get("banco", {}).get("dsn", DSN_PADRAO), avisar)


def json_seguro(x):
    """Para a API: datas viram texto ISO."""
    return json.loads(json.dumps(x, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)))
