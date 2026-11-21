-- Projeto Presença — Marco 4 — PERSISTÊNCIA
--
-- PostgreSQL com a extensão TimescaleDB: um banco só, com as duas naturezas de
-- dado que o professor pediu ("temporal e normal"):
--
--   TEMPORAIS (hypertables, particionadas por tempo e comprimidas):
--     eventos   todo heartbeat recebido, cru, com a classificação do servidor
--     sensores  acelerômetro e bateria do celular
--     recusas   tudo o que a segurança recusou (auditoria)
--
--   RELACIONAIS (tabelas normais):
--     alunos         pseudônimo + chave pública (quem é o aparelho)
--     identificacao  nome e matrícula — SEPARADO dos eventos (LGPD, art. 13)
--     sessoes        a aula de um aluno: resultado final e estado para recuperar
--     comandos       o que o atuador mandou ao celular e a confirmação
--
-- Idempotente: pode rodar de novo sem apagar nada.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------- relacionais
CREATE TABLE IF NOT EXISTS alunos (
    aluno           text PRIMARY KEY,            -- tok-xxxxxxxx (hash da chave)
    chave_publica   text NOT NULL,
    device_id       text NOT NULL,
    primeiro_visto  timestamptz NOT NULL DEFAULT now(),
    ultimo_visto    timestamptz NOT NULL DEFAULT now()
);

-- Dado pessoal. Fica numa tabela à parte para poder ser apagado sem mexer no
-- histórico pseudonimizado (direito de eliminação, LGPD art. 18, VI).
CREATE TABLE IF NOT EXISTS identificacao (
    aluno       text NOT NULL REFERENCES alunos(aluno) ON DELETE CASCADE,
    turma       text NOT NULL,
    nome        text NOT NULL,
    matricula   text,
    informado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (aluno, turma)
);

CREATE TABLE IF NOT EXISTS sessoes (
    id                   text PRIMARY KEY,       -- s + 4 hex
    aluno                text NOT NULL,
    turma                text,
    aula_id              text,
    sala                 text,
    aberta_em            timestamptz NOT NULL DEFAULT now(),
    atualizada_em        timestamptz NOT NULL DEFAULT now(),
    encerrada_em         timestamptz,
    inicio_t             double precision,       -- início na linha do tempo da sessão
    estado               text,
    acumulado_s          real,
    presenca_s           real,
    ausencia_creditada_s real,
    tempo_aula_s         real,
    percentual           real,
    aprovado             boolean,
    avisos               text[] NOT NULL DEFAULT '{}',
    contagem             jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS sessoes_turma ON sessoes (turma, aula_id);
CREATE INDEX IF NOT EXISTS sessoes_abertas ON sessoes (encerrada_em) WHERE encerrada_em IS NULL;

CREATE TABLE IF NOT EXISTS comandos (
    comando_id    text PRIMARY KEY,
    aluno         text NOT NULL,
    turma         text,
    tipo          text NOT NULL,
    texto         text,
    de            text NOT NULL,                 -- servidor ou admin
    enviado_em    timestamptz NOT NULL DEFAULT now(),
    confirmado_em timestamptz,
    resultado     text
);

-- ---------------------------------------------------------------- temporais
CREATE TABLE IF NOT EXISTS eventos (
    recebido_em    timestamptz NOT NULL,         -- carimbo do SERVIDOR
    sessao         text,
    aluno          text NOT NULL,
    turma          text,
    event_id       text NOT NULL,
    boot_id        text,
    sequencia      integer,
    classificacao  text NOT NULL,                -- aceito, duplicado, fora-de-ordem, atrasado
    t_linha        double precision,             -- posição na linha do tempo da sessão
    classe         text,                         -- dentro, fora, neutro
    estado         text,                         -- estado da máquina depois deste evento
    regiao         text,
    rssi           real,
    bufferizado    boolean NOT NULL DEFAULT false,
    carga          jsonb NOT NULL                -- o heartbeat inteiro, como chegou
);
SELECT create_hypertable('eventos', 'recebido_em', chunk_time_interval => interval '1 day',
                         if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS eventos_sessao ON eventos (sessao, recebido_em DESC);

CREATE TABLE IF NOT EXISTS sensores (
    recebido_em   timestamptz NOT NULL,
    aluno         text NOT NULL,
    turma         text,
    sensor_id     text NOT NULL,
    movimento     real,
    parado        boolean,
    bateria       real,
    carregando    boolean,
    carga         jsonb NOT NULL
);
SELECT create_hypertable('sensores', 'recebido_em', chunk_time_interval => interval '1 day',
                         if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS sensores_aluno ON sensores (aluno, recebido_em DESC);

CREATE TABLE IF NOT EXISTS recusas (
    recebido_em  timestamptz NOT NULL,
    topico       text,
    motivo       text NOT NULL,
    detalhe      text
);
SELECT create_hypertable('recusas', 'recebido_em', chunk_time_interval => interval '7 days',
                         if_not_exists => TRUE);

-- ------------------------------------------------- compressão e retenção
-- "Guardar todos os eventos e tentar comprimir": os pedaços (chunks) com mais
-- de 7 dias são comprimidos em colunas, agrupados por aluno. Heartbeats de um
-- mesmo aluno são muito parecidos entre si, e a compressão aproveita isso.
ALTER TABLE eventos  SET (timescaledb.compress, timescaledb.compress_segmentby = 'aluno',
                          timescaledb.compress_orderby = 'recebido_em');
ALTER TABLE sensores SET (timescaledb.compress, timescaledb.compress_segmentby = 'aluno',
                          timescaledb.compress_orderby = 'recebido_em');
SELECT add_compression_policy('eventos',  interval '7 days', if_not_exists => TRUE);
SELECT add_compression_policy('sensores', interval '7 days', if_not_exists => TRUE);

-- Retenção (LGPD, art. 15 e 16: guardar só pelo tempo necessário). O dado cru
-- serve para recalcular e auditar dentro do semestre; depois disso fica só o
-- resultado por aula, em `sessoes`. 180 dias ≈ um semestre e a revisão de notas.
SELECT add_retention_policy('eventos',  interval '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('sensores', interval '180 days', if_not_exists => TRUE);
SELECT add_retention_policy('recusas',  interval '180 days', if_not_exists => TRUE);
