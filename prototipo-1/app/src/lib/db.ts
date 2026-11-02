/**
 * Banco local (SQLite no próprio celular).
 *
 * Guarda as turmas que este aparelho administra ou em que está inscrito, os
 * avisos já recebidos (também servem para não tocar o mesmo aviso duas vezes)
 * e o resultado de cada aula. Nada disso sai do aparelho; o que o servidor
 * recebe é só o heartbeat.
 */
import type { SQLiteDatabase } from 'expo-sqlite';
import type { Periodo, Turma } from './turma';

export type Papel = 'admin' | 'aluno';

const VERSAO = 3;

export async function migrar(db: SQLiteDatabase) {
  const { user_version } = (await db.getFirstAsync<{ user_version: number }>('PRAGMA user_version'))!;
  if (user_version >= VERSAO) return;
  if (user_version < 1) await db.execAsync(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS turmas (
      codigo        TEXT NOT NULL,
      papel         TEXT NOT NULL CHECK (papel IN ('admin', 'aluno')),
      nome          TEXT NOT NULL,
      sala          TEXT NOT NULL,
      periodos      TEXT NOT NULL,          -- JSON: Periodo[]
      aula_agora    TEXT,                   -- JSON: { inicioMs, duracaoS } ou NULL
      publicado_em  INTEGER,                -- última versão publicada/recebida
      criado_em     INTEGER NOT NULL,
      PRIMARY KEY (codigo, papel)
    );
    CREATE TABLE IF NOT EXISTS avisos (
      aviso_id     TEXT PRIMARY KEY,
      codigo       TEXT NOT NULL,
      tipo         TEXT NOT NULL,
      texto        TEXT NOT NULL,
      percentual   REAL,
      recebido_em  INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS aulas (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      codigo        TEXT NOT NULL,
      encerrada_em  INTEGER NOT NULL,
      estado        TEXT NOT NULL,
      acumulado_s   REAL NOT NULL,
      tempo_aula_s  REAL NOT NULL,
      percentual    REAL NOT NULL
    );
  `);
  if (user_version < 2) await db.execAsync(`
    CREATE TABLE IF NOT EXISTS ajustes (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
  `);
  // Protótipo 1: o limiar de 1 m é da turma (calibrado pelo admin), não do aparelho.
  await db.execAsync(`
    ALTER TABLE turmas ADD COLUMN limiar_1m REAL;
    DELETE FROM ajustes WHERE chave = 'limiar_1m_dbm';
    PRAGMA user_version = ${VERSAO};
  `);
}

export async function lerAjuste(db: SQLiteDatabase, chave: string) {
  const l = await db.getFirstAsync<{ valor: string }>('SELECT valor FROM ajustes WHERE chave = ?', chave);
  return l?.valor ?? null;
}

export async function gravarAjuste(db: SQLiteDatabase, chave: string, valor: string) {
  await db.runAsync('INSERT OR REPLACE INTO ajustes (chave, valor) VALUES (?, ?)', chave, valor);
}

interface LinhaTurma {
  codigo: string; papel: Papel; nome: string; sala: string; periodos: string;
  aula_agora: string | null; publicado_em: number | null; limiar_1m: number | null;
}

export interface TurmaLocal extends Turma {
  papel: Papel;
  publicada: boolean;
}

function deLinha(l: LinhaTurma): TurmaLocal {
  return {
    eventType: 'presenca.turma.v1',
    codigo: l.codigo, papel: l.papel, nome: l.nome, sala: l.sala,
    periodos: JSON.parse(l.periodos) as Periodo[],
    aulaAgora: l.aula_agora ? JSON.parse(l.aula_agora) : null,
    limiar1mDbm: l.limiar_1m,
    publicadoEmMs: l.publicado_em ?? 0,
    publicada: l.publicado_em !== null,
  };
}

export async function listarTurmas(db: SQLiteDatabase, papel: Papel) {
  const linhas = await db.getAllAsync<LinhaTurma>(
    'SELECT * FROM turmas WHERE papel = ? ORDER BY criado_em DESC', papel);
  return linhas.map(deLinha);
}

export async function obterTurma(db: SQLiteDatabase, codigo: string, papel: Papel) {
  const l = await db.getFirstAsync<LinhaTurma>(
    'SELECT * FROM turmas WHERE codigo = ? AND papel = ?', codigo, papel);
  return l ? deLinha(l) : null;
}

/** Grava a turma. `publicadoEmMs` null = alteração local ainda não publicada. */
export async function salvarTurma(db: SQLiteDatabase, t: Omit<Turma, 'eventType' | 'publicadoEmMs'>,
                                  papel: Papel, publicadoEmMs: number | null) {
  await db.runAsync(
    `INSERT INTO turmas (codigo, papel, nome, sala, periodos, aula_agora, limiar_1m, publicado_em, criado_em)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (codigo, papel) DO UPDATE SET
       nome = excluded.nome, sala = excluded.sala, periodos = excluded.periodos,
       aula_agora = excluded.aula_agora, limiar_1m = excluded.limiar_1m,
       publicado_em = excluded.publicado_em`,
    t.codigo, papel, t.nome, t.sala, JSON.stringify(t.periodos),
    t.aulaAgora ? JSON.stringify(t.aulaAgora) : null, t.limiar1mDbm, publicadoEmMs, Date.now());
}

export async function apagarTurma(db: SQLiteDatabase, codigo: string, papel: Papel) {
  await db.runAsync('DELETE FROM turmas WHERE codigo = ? AND papel = ?', codigo, papel);
}

// ---- avisos ----------------------------------------------------------------
export interface Aviso {
  avisoId: string; tipo: string; texto: string; percentual?: number;
}

/** Devolve true se o aviso é novo (e o grava); false se já tinha sido mostrado. */
export async function registrarAviso(db: SQLiteDatabase, codigo: string, a: Aviso) {
  const r = await db.runAsync(
    `INSERT OR IGNORE INTO avisos (aviso_id, codigo, tipo, texto, percentual, recebido_em)
     VALUES (?, ?, ?, ?, ?, ?)`,
    a.avisoId, codigo, a.tipo, a.texto, a.percentual ?? null, Date.now());
  return r.changes > 0;
}

export async function ultimosAvisos(db: SQLiteDatabase, codigo: string, limite = 5) {
  return db.getAllAsync<{ aviso_id: string; tipo: string; texto: string; recebido_em: number }>(
    'SELECT * FROM avisos WHERE codigo = ? ORDER BY recebido_em DESC LIMIT ?', codigo, limite);
}

// ---- resultado das aulas ---------------------------------------------------
export async function registrarAula(db: SQLiteDatabase, codigo: string,
                                    r: { estado: string; acumuladoS: number; tempoAulaS: number; percentual: number }) {
  await db.runAsync(
    `INSERT INTO aulas (codigo, encerrada_em, estado, acumulado_s, tempo_aula_s, percentual)
     VALUES (?, ?, ?, ?, ?, ?)`,
    codigo, Date.now(), r.estado, r.acumuladoS, r.tempoAulaS, r.percentual);
}

export async function historico(db: SQLiteDatabase, codigo: string) {
  return db.getAllAsync<{ id: number; encerrada_em: number; acumulado_s: number; tempo_aula_s: number; percentual: number }>(
    'SELECT * FROM aulas WHERE codigo = ? ORDER BY encerrada_em DESC LIMIT 20', codigo);
}
