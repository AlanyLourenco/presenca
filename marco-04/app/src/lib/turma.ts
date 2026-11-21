/**
 * Turma, períodos de aula e o código que o estudante digita ou lê no QR.
 * Módulo puro: sem rede, sem banco.
 */
import { ALFABETO_CODIGO, DURACAO_AULA_DEMO_S, TAMANHO_CODIGO } from './config.ts';

export const DIAS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];

export interface Periodo {
  dia: number;        // 0 = domingo … 6 = sábado
  inicio: string;     // "HH:MM"
  fim: string;        // "HH:MM"
}

/** O que o admin publica e o estudante recebe (contrato presenca.turma.v1). */
export interface Turma {
  eventType: 'presenca.turma.v1';
  codigo: string;
  nome: string;
  sala: string;
  periodos: Periodo[];
  /** Aula de demonstração iniciada pelo admin agora, fora da grade. */
  aulaAgora: { inicioMs: number; duracaoS: number } | null;
  /** RSSI da âncora a 1 m, calibrado pelo admin. null = ainda não calibrado. */
  limiar1mDbm: number | null;
  /** Marco 4: o limiar de 1 m de CADA âncora (notebook e ESP32). */
  limiares?: Record<string, number>;
  publicadoEmMs: number;
}

export function gerarCodigo(aleatorio: () => number = Math.random) {
  let c = '';
  for (let i = 0; i < TAMANHO_CODIGO; i++) c += ALFABETO_CODIGO[Math.floor(aleatorio() * ALFABETO_CODIGO.length)];
  return c;
}

/** Aceita "abc 234", "PRESENCA:ABC234" ou "presenca://turma/ABC234". */
export function normalizarCodigo(texto: string): string | null {
  const t = texto.trim().toUpperCase();
  const m = t.match(/(?:PRESENCA:(?:\/\/TURMA\/)?)?([A-Z0-9 -]+)$/);
  if (!m) return null;
  const c = m[1].replace(/[\s-]/g, '');
  if (c.length !== TAMANHO_CODIGO) return null;
  return [...c].every((x) => ALFABETO_CODIGO.includes(x)) ? c : null;
}

export const conteudoQr = (codigo: string) => `presenca://turma/${codigo}`;

export function horaValida(h: string) {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(h);
}

const minutos = (h: string) => Number(h.slice(0, 2)) * 60 + Number(h.slice(3, 5));

export function periodoValido(p: Periodo) {
  return p.dia >= 0 && p.dia <= 6 && horaValida(p.inicio) && horaValida(p.fim)
    && minutos(p.fim) > minutos(p.inicio);
}

export type AulaAtual =
  | { tipo: 'demonstracao'; inicioMs: number; fimMs: number }
  | { tipo: 'grade'; periodo: Periodo; fimMs: number }
  | null;

/** A aula em andamento agora, se houver. A demonstração tem prioridade. */
export function aulaEmAndamento(t: Pick<Turma, 'periodos' | 'aulaAgora'>, agora: Date): AulaAtual {
  if (t.aulaAgora) {
    const fimMs = t.aulaAgora.inicioMs + t.aulaAgora.duracaoS * 1000;
    if (agora.getTime() >= t.aulaAgora.inicioMs && agora.getTime() < fimMs) {
      return { tipo: 'demonstracao', inicioMs: t.aulaAgora.inicioMs, fimMs };
    }
  }
  const m = agora.getHours() * 60 + agora.getMinutes();
  for (const p of t.periodos) {
    if (p.dia === agora.getDay() && m >= minutos(p.inicio) && m < minutos(p.fim)) {
      const fim = new Date(agora);
      fim.setHours(Number(p.fim.slice(0, 2)), Number(p.fim.slice(3, 5)), 0, 0);
      return { tipo: 'grade', periodo: p, fimMs: fim.getTime() };
    }
  }
  return null;
}

/** Próxima aula da grade a partir de agora (até 7 dias), para mostrar na tela. */
export function proximaAula(periodos: Periodo[], agora: Date): Date | null {
  let melhor: Date | null = null;
  for (const p of periodos) {
    for (let d = 0; d <= 7; d++) {
      const dia = new Date(agora);
      dia.setDate(agora.getDate() + d);
      if (dia.getDay() !== p.dia) continue;
      dia.setHours(Number(p.inicio.slice(0, 2)), Number(p.inicio.slice(3, 5)), 0, 0);
      if (dia > agora && (!melhor || dia < melhor)) melhor = dia;
    }
  }
  return melhor;
}

const dois = (n: number) => String(n).padStart(2, '0');

/**
 * Identificador da aula (heartbeat v3): agrupa o relatório do professor.
 * Demonstração: "demo-<inicioMs>". Grade: "AAAA-MM-DD-HHMM" do início.
 */
export function idDaAula(a: NonNullable<AulaAtual>, agora: Date): string {
  if (a.tipo === 'demonstracao') return `demo-${a.inicioMs}`;
  return `${agora.getFullYear()}-${dois(agora.getMonth() + 1)}-${dois(agora.getDate())}-`
    + a.periodo.inicio.replace(':', '');
}

/** Limiar de cada âncora. Turma do Marco 3 (só limiar1mDbm) vale para a anc-pc-1. */
export function limiaresDa(t: Pick<Turma, 'limiar1mDbm' | 'limiares'>): Record<string, number | null> {
  return { 'anc-pc-1': t.limiar1mDbm, ...(t.limiares ?? {}) };
}

export function novaAulaAgora(agoraMs: number) {
  return { inicioMs: agoraMs, duracaoS: DURACAO_AULA_DEMO_S };
}

/** Confere o que chega da rede antes de gravar no banco. */
export function lerTurma(json: string): Turma | null {
  try {
    const t = JSON.parse(json);
    if (t?.eventType !== 'presenca.turma.v1' || typeof t.codigo !== 'string'
        || typeof t.nome !== 'string' || typeof t.sala !== 'string'
        || !Array.isArray(t.periodos) || !t.periodos.every(periodoValido)) return null;
    const limiar = typeof t.limiar1mDbm === 'number' && t.limiar1mDbm < 0 && t.limiar1mDbm > -127
      ? t.limiar1mDbm : null;
    const limiares: Record<string, number> = {};
    if (t.limiares && typeof t.limiares === 'object') {
      for (const [a, v] of Object.entries(t.limiares)) {
        if (/^anc-[a-z0-9-]+$/.test(a) && typeof v === 'number' && v < 0 && v > -127) limiares[a] = v;
      }
    }
    return { ...t, aulaAgora: t.aulaAgora ?? null, limiar1mDbm: limiar, limiares };
  } catch {
    return null;
  }
}
