"""
Projeto Presenca - Marco 2
Nucleo da permanencia: localizacao e maquina de estados.

Modulo puro, sem rede e sem relogio. Recebe o log de heartbeats e devolve o
estado e o acumulado. Tudo o que decide frequencia esta aqui, e e isto que os
testes exercitam.

Duas regras do projeto tecnico (secao 6) moldam o desenho:

  1. O acumulador e calculado RETROATIVAMENTE sobre o log, nunca incrementado
     ao vivo. A cada heartbeat recebido, a linha do tempo inteira e refeita.
     Por isso um evento atrasado ou fora de ordem nao corrompe nada: ele entra
     na posicao certa do log e o resultado e o mesmo que se tivesse chegado em
     ordem.
  2. O orcamento de ausencia e POR SESSAO, nao por evento.

Tempos: todas as duracoes de projeto sao escritas em valores reais (30 s,
15 min...) e divididas por `escala`. Com escala 30, a aula de 50 min vira
100 s de demonstracao. Assim os numeros do codigo continuam sendo os numeros
do projeto.
"""

from dataclasses import dataclass, field

# Estados da maquina (projeto-tecnico.md secao 6)
FORA = "FORA"
PRESENTE = "PRESENTE"
AUSENCIA_TOLERADA = "AUSENCIA_TOLERADA"

# Classificacao de cada heartbeat
DENTRO, FORA_DA_SALA, NEUTRO = "dentro", "fora", "neutro"

# Regiao informada pelo aparelho (histerese -70/-85 dBm aplicada no ESP32)
REGIAO_DENTRO = "DENTRO_ALCANCE"
REGIAO_FORA = "FORA_ALCANCE"

# Tipos de aviso (projeto-tecnico.md secao 7) - so estes quatro momentos
AVISO_10 = "AVISO_10_MIN"
AVISO_13 = "AVISO_13_MIN"
LIMITE_ESGOTADO = "LIMITE_ESGOTADO"
FIM_DA_AULA = "FIM_DA_AULA"


# ---------------------------------------------------------------------------
# Parametros
# ---------------------------------------------------------------------------
@dataclass
class Parametros:
    """Valores do projeto em segundos REAIS. `escala` comprime todos juntos."""
    escala: float = 30.0
    persistencia_s: float = 30.0            # entrada e saida sustentadas por 30 s
    orcamento_ausencia_s: float = 15 * 60  #150  # 15 min por sessao, limite unico
    aviso_1_s: float = 10 * 60              #90 # 2/3 do orcamento
    aviso_2_s: float = 13 * 60              #120 # 87 % do orcamento
    requalificacao_s: float = 30 * 60       # min(30 min, tempo restante)
    duracao_aula_s: float = 50 * 60         # aula-hora
    presenca_minima: float = 0.75           # 37,5 de 50 min

    @classmethod
    def de_config(cls, cfg):
        p = cfg.get("parametros", {})
        return cls(**{k: v for k, v in p.items() if k in cls.__dataclass_fields__})

    # valores efetivos, ja comprimidos
    def t(self, segundos_reais):
        return segundos_reais / self.escala

    @property
    def persistencia(self): return self.t(self.persistencia_s)
    @property
    def orcamento(self): return self.t(self.orcamento_ausencia_s)
    @property
    def aviso_1(self): return self.t(self.aviso_1_s)
    @property
    def aviso_2(self): return self.t(self.aviso_2_s)
    @property
    def requalificacao(self): return self.t(self.requalificacao_s)
    @property
    def duracao_aula(self): return self.t(self.duracao_aula_s)


# ---------------------------------------------------------------------------
# Localizacao: trilateracao + pertinencia ao poligono (secao 5)
# ---------------------------------------------------------------------------
@dataclass
class Sala:
    poligono: list                  # [[x, y], ...] em metros
    ancoras: dict                   # id -> [x, y]
    rssi_1m: float = -45.0          # A: RSSI a 1 m
    expoente: float = 2.2           # n: perda de percurso

    @classmethod
    def de_config(cls, cfg):
        s = cfg["sala"]
        return cls(poligono=s["poligono"], ancoras=s["ancoras"],
                   rssi_1m=s.get("rssi_1m", -45.0), expoente=s.get("expoente", 2.2))

    def distancia(self, rssi):
        """RSSI = A - 10 n log10(d)  =>  d = 10^((A - RSSI) / 10n)."""
        return 10 ** ((self.rssi_1m - rssi) / (10 * self.expoente))

    def trilaterar(self, leituras):
        """leituras: {id_ancora: rssi}. Precisa das tres ancoras.

        Subtraindo a equacao do primeiro circulo das outras duas, o sistema
        vira linear em (x, y). Retorna None se faltar ancora ou se as ancoras
        forem colineares.
        """
        ids = [i for i in self.ancoras if leituras.get(i) is not None]
        if len(ids) < 3:
            return None
        (x1, y1), (x2, y2), (x3, y3) = (self.ancoras[i] for i in ids[:3])
        r1, r2, r3 = (self.distancia(leituras[i]) for i in ids[:3])

        a1, b1 = 2 * (x2 - x1), 2 * (y2 - y1)
        c1 = r1 ** 2 - r2 ** 2 - x1 ** 2 + x2 ** 2 - y1 ** 2 + y2 ** 2
        a2, b2 = 2 * (x3 - x1), 2 * (y3 - y1)
        c2 = r1 ** 2 - r3 ** 2 - x1 ** 2 + x3 ** 2 - y1 ** 2 + y3 ** 2

        det = a1 * b2 - a2 * b1
        if abs(det) < 1e-9:
            return None
        return ((c1 * b2 - c2 * b1) / det, (a1 * c2 - a2 * c1) / det)

    def contem(self, ponto):
        """Ray casting. Uma sala e um poligono com paredes, nao um raio."""
        x, y = ponto
        dentro = False
        pts = self.poligono
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                dentro = not dentro
            j = i
        return dentro


def classificar(heartbeat, sala):
    """Decide o que UM heartbeat diz: dentro, fora ou neutro.

    - A regiao (histerese -70/-85 dBm) ja vem decidida pelo aparelho.
    - O servidor acrescenta o que o aparelho nao sabe: onde fica a sala.

      FORA_ALCANCE                      -> fora
      DENTRO_ALCANCE e no poligono      -> dentro
      DENTRO_ALCANCE e fora do poligono -> fora  (sinal forte na sala vizinha)
      sem as tres ancoras / indefinido  -> neutro (nao ha base para decidir)

    Retorna (classe, posicao ou None).
    """
    regiao = heartbeat.get("state")

    # PROTOTIPO 1 - uma ancora so (o notebook). Sem tres ancoras nao ha
    # trilateracao: a regiao decidida no celular, com o limiar calibrado a
    # 1 m do notebook, e a decisao inteira. E o raio que o projeto rejeita
    # para a sala real; aqui e a simplificacao declarada do prototipo.
    if len(sala.ancoras) == 1:
        if regiao == REGIAO_FORA:
            return FORA_DA_SALA, None
        return (DENTRO if regiao == REGIAO_DENTRO else NEUTRO), None

    leituras = {a["id"]: a.get("rssi") for a in heartbeat.get("ancoras", [])}
    pos = sala.trilaterar(leituras)

    if regiao == REGIAO_FORA:
        return FORA_DA_SALA, pos
    if regiao != REGIAO_DENTRO or pos is None:
        return NEUTRO, pos
    return (DENTRO if sala.contem(pos) else FORA_DA_SALA), pos


# ---------------------------------------------------------------------------
# Maquina de estados, refeita sobre o log inteiro
# ---------------------------------------------------------------------------
@dataclass
class Aviso:
    tipo: str
    em: float                   # instante da linha do tempo em que e devido
    referencia: float = None    # para LIMITE_ESGOTADO: quando o tempo parou


@dataclass
class Resultado:
    estado: str = FORA
    agora: float = 0.0
    presenca_s: float = 0.0          # tempo fisicamente presente, confirmado
    ausencia_creditada_s: float = 0.0  # ausencia tolerada ja requalificada
    provisorio_s: float = 0.0        # ausencia em curso ou aguardando requalificacao
    ausencia_usada_s: float = 0.0    # orcamento consumido na sessao
    orcamento_restante_s: float = 0.0
    esgotado: bool = False
    encerrada: bool = False
    avisos: list = field(default_factory=list)
    transicoes: list = field(default_factory=list)   # (t, de, para, porque)

    @property
    def acumulado_s(self):
        return self.presenca_s + self.ausencia_creditada_s

    def percentual(self, p):
        return 100.0 * self.acumulado_s / p.duracao_aula


def calcular(log, p, inicio=None):
    """Refaz a sessao inteira a partir do log.

    log: lista de (t, classe) - t em segundos da linha do tempo, classe de
         classificar(). Nao precisa estar ordenado; e ordenado aqui.
    inicio: instante de abertura da sessao (padrao: primeiro heartbeat).

    Retorna um Resultado com o estado no ultimo instante observado.
    """
    r = Resultado()
    eventos = sorted(log, key=lambda e: e[0])
    if not eventos:
        r.orcamento_restante_s = p.orcamento
        return r

    t0 = eventos[0][0] if inicio is None else inicio
    fim_aula = t0 + p.duracao_aula

    estado = FORA
    corrida_classe, corrida_inicio = None, None   # condicao sustentada em curso
    entrada = None           # inicio da presenca atual
    ausencia_inicio = None   # inicio REAL da ausencia atual
    usada = 0.0              # orcamento consumido
    pendente = None          # (duracao, requalifica_em): ausencia aguardando
    avisados = set()

    def mudar(t, para, porque):
        nonlocal estado
        r.transicoes.append((round(t - t0, 3), estado, para, porque))
        estado = para

    def avisar(tipo, em, ref=None):
        if tipo not in avisados:
            avisados.add(tipo)
            r.avisos.append(Aviso(tipo, round(em - t0, 3),
                                  None if ref is None else round(ref - t0, 3)))

    def resolver_pendente(ate):
        """Credita a ausencia anterior se a presenca durou a requalificacao."""
        nonlocal pendente
        if pendente and ate >= pendente[1]:
            r.ausencia_creditada_s += pendente[0]
            pendente = None

    def checar_orcamento(t):
        """Durante a ausencia: avisos e esgotamento, no instante exato."""
        nonlocal usada, ausencia_inicio
        if estado != AUSENCIA_TOLERADA:
            return
        for tipo, limite in ((AVISO_10, p.aviso_1), (AVISO_13, p.aviso_2)):
            if usada + (t - ausencia_inicio) >= limite:
                avisar(tipo, ausencia_inicio + (limite - usada))
        if usada + (t - ausencia_inicio) >= p.orcamento:
            quando = ausencia_inicio + (p.orcamento - usada)
            # estorno: a ausencia inteira deixa de ser creditada, e o aviso
            # diz a hora em que o tempo parou de contar - o inicio real
            usada = p.orcamento
            r.esgotado = True
            avisar(LIMITE_ESGOTADO, quando, ref=ausencia_inicio)
            mudar(quando, FORA, "orcamento de ausencia esgotado")
            ausencia_inicio = None

    for t, classe in eventos:
        if t > fim_aula:
            break

        # condicao sustentada: neutro interrompe qualquer corrida
        if classe != corrida_classe:
            corrida_classe, corrida_inicio = classe, t

        # Se ha um retorno em curso, o orcamento so e avaliado ate o inicio
        # dele: quem voltou a tempo nao pode ser punido pela demora da
        # confirmacao. Se o retorno nao se sustentar, o proximo heartbeat
        # reavalia com o tempo cheio - e o instante do esgotamento e exato.
        checar_orcamento(corrida_inicio if classe == DENTRO else t)

        sustentada = classe != NEUTRO and t - corrida_inicio >= p.persistencia

        if not sustentada:
            continue

        if estado == FORA and classe == DENTRO:
            entrada = corrida_inicio              # retroativo: desde o inicio real
            mudar(entrada, PRESENTE, "sinal na sala sustentado")

        elif estado == PRESENTE and classe == FORA_DA_SALA:
            saida = corrida_inicio                # inicio REAL da ausencia
            r.presenca_s += saida - entrada
            if pendente and saida < pendente[1]:
                pendente = None                   # saiu antes de requalificar
            resolver_pendente(saida)
            entrada = None
            if usada < p.orcamento:
                ausencia_inicio = saida
                mudar(saida, AUSENCIA_TOLERADA, "sinal fora da sala sustentado")
                checar_orcamento(t)
            else:
                mudar(saida, FORA, "saiu sem orcamento restante")

        elif estado == AUSENCIA_TOLERADA and classe == DENTRO:
            retorno = corrida_inicio
            duracao = retorno - ausencia_inicio
            usada += duracao
            requalifica = retorno + min(p.requalificacao, fim_aula - retorno)
            pendente = (duracao, requalifica)
            ausencia_inicio = None
            entrada = retorno
            mudar(retorno, PRESENTE, "retornou dentro do orcamento")

    # --- fechamento no ultimo instante observado ---
    agora = min(eventos[-1][0], fim_aula)
    r.encerrada = eventos[-1][0] >= fim_aula
    checar_orcamento(corrida_inicio if corrida_classe == DENTRO else agora)

    if estado == PRESENTE:
        # Saida ainda nao confirmada: o trecho depois do inicio dela fica
        # provisorio. Sem isso o garantido subiria e depois voltaria quando
        # a saida se confirmasse - e o acumulador tem de ser monotonico.
        # Com a aula encerrada, uma saida que nao chegou a se sustentar nao e
        # saida: o aluno estava na sala ate o fim, e a requalificacao (que
        # termina no fim da aula) se completa.
        saindo = corrida_classe == FORA_DA_SALA and not r.encerrada
        ate = corrida_inicio if saindo else agora
        r.presenca_s += ate - entrada
        r.provisorio_s += agora - ate
        resolver_pendente(ate)
    if pendente:
        r.provisorio_s += pendente[0]
    if estado == AUSENCIA_TOLERADA:
        r.provisorio_s += agora - ausencia_inicio
        usada_agora = usada + (agora - ausencia_inicio)
    else:
        usada_agora = usada

    if r.encerrada:
        # quem saiu no fim soma o que assistiu: ausencia em curso nao e creditada
        r.provisorio_s = 0.0
        avisar(FIM_DA_AULA, fim_aula)

    r.estado = estado
    r.agora = round(agora - t0, 3)
    r.ausencia_usada_s = min(usada_agora, p.orcamento)
    r.orcamento_restante_s = max(0.0, p.orcamento - usada_agora)
    return r


def texto_aviso(aviso, r, p):
    """Mensagens da secao 7, com os tempos da demonstracao."""
    orc = p.orcamento
    if aviso.tipo == AVISO_10:
        return f"Fora da sala ha {p.aviso_1:.0f} s. Seu limite e de {orc:.0f} s nesta aula."
    if aviso.tipo == AVISO_13:
        return f"Faltam {orc - p.aviso_2:.0f} s do seu limite. Depois disso o tempo para de contar."
    if aviso.tipo == LIMITE_ESGOTADO:
        return f"O tempo parou de ser contabilizado em t={aviso.referencia:.0f} s."
    if aviso.tipo == FIM_DA_AULA:
        return f"Voce acumulou {r.percentual(p):.0f}% desta aula."
    return aviso.tipo
