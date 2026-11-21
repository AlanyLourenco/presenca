/**
 * ATUADOR — Marco 4: uma operação enviada AO celular do estudante.
 *
 * O servidor (pelo terminal ou pela API) ou o professor (pelo app, na tela de
 * relatório) publica presenca.comando.v1 em .../comando/<aluno>. O celular:
 *   1. confere a assinatura: só executa se for da chave do SERVIDOR (fixada no
 *      app) ou da chave do ADMIN desta turma (fixada no pareamento);
 *   2. confere que é para ele, desta turma, dentro da validade e inédito;
 *   3. executa (vibra e notifica; no "chamar" pede um toque em "Estou aqui";
 *      na "lanterna" pisca o flash);
 *   4. confirma, assinado, em .../comando-ack/<aluno>: "executado" logo que
 *      executa e "respondido" quando o estudante toca no botão.
 *
 * Módulo puro (sem rede): testado com `npm test`.
 */
import { abrirEnvelope } from './assinatura.ts';

export type TipoComando = 'vibrar' | 'chamar' | 'lanterna';
export const TIPOS_COMANDO: TipoComando[] = ['vibrar', 'chamar', 'lanterna'];

export interface Comando {
  eventType: 'presenca.comando.v1';
  comandoId: string;
  aluno: string;
  turma: string;
  tipo: TipoComando;
  texto: string;
  emitidoEmMs: number;
  validadeS: number;
}

export type Conferido =
  | { ok: true; comando: Comando; de: 'servidor' | 'professor' }
  | { ok: false; motivo: string; comandoId?: string };

/** Margem para relógios de celulares diferentes não baterem. */
const TOLERANCIA_RELOGIO_MS = 30_000;

export function conferirComando(topico: string, texto: string, quem: {
  aluno: string; turma: string; chaveServidor: string; chaveAdmin: string | null;
}, agoraMs: number, jaVistos: Set<string>): Conferido {
  const a = abrirEnvelope(topico, texto);
  if (!a.ok) return { ok: false, motivo: a.motivo };
  const chave = a.chavePublica.toLowerCase();
  const de = chave === quem.chaveServidor.toLowerCase() ? 'servidor'
    : quem.chaveAdmin && chave === quem.chaveAdmin.toLowerCase() ? 'professor' : null;
  if (!de) return { ok: false, motivo: 'comando assinado por quem não é o servidor nem o professor' };

  const c = a.carga as Partial<Comando>;
  if (c?.eventType !== 'presenca.comando.v1' || typeof c.comandoId !== 'string'
      || !TIPOS_COMANDO.includes(c.tipo as TipoComando) || typeof c.texto !== 'string'
      || typeof c.emitidoEmMs !== 'number' || typeof c.validadeS !== 'number') {
    return { ok: false, motivo: 'comando fora do contrato' };
  }
  if (c.aluno !== quem.aluno || c.turma !== quem.turma) {
    return { ok: false, motivo: 'comando para outro aluno ou outra turma', comandoId: c.comandoId };
  }
  if (jaVistos.has(c.comandoId)) return { ok: false, motivo: 'comando repetido', comandoId: c.comandoId };
  if (agoraMs > c.emitidoEmMs + c.validadeS * 1000 + TOLERANCIA_RELOGIO_MS
      || c.emitidoEmMs > agoraMs + TOLERANCIA_RELOGIO_MS) {
    return { ok: false, motivo: 'comando vencido', comandoId: c.comandoId };
  }
  return { ok: true, comando: c as Comando, de };
}

export function montarComando(p: { aluno: string; turma: string; tipo: TipoComando; texto: string },
                              agoraMs: number, aleatorio = Math.random): Comando {
  const id = 'adm-' + Math.floor(aleatorio() * 0xffffffff).toString(16).padStart(8, '0');
  return { eventType: 'presenca.comando.v1', comandoId: id, ...p, texto: p.texto.slice(0, 200),
           emitidoEmMs: agoraMs, validadeS: 60 };
}

export type Resultado = 'executado' | 'respondido' | 'recusado' | 'vencido';

export function montarConfirmacao(comandoId: string, aluno: string, resultado: Resultado,
                                  agoraMs: number, detalhe?: string) {
  return { eventType: 'presenca.comando.ack.v1', comandoId, aluno, resultado, emMs: agoraMs,
           ...(detalhe ? { detalhe: detalhe.slice(0, 200) } : {}) };
}
