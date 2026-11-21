/**
 * Relatório de presença da turma — Marco 4 (tela do professor).
 *
 * O servidor publica presenca.relatorio.v1 RETIDO e ASSINADO em
 * .../relatorio/<turma>. O app do professor só mostra o que vier com a
 * assinatura do servidor e exporta a lista em CSV (planilha), com ";" e
 * vírgula decimal, que é o que o Excel em português abre direto.
 *
 * Módulo puro: testado com `npm test`.
 */
import { abrirDe } from './assinatura.ts';

export interface AlunoNoRelatorio {
  aluno: string;
  nome: string | null;
  matricula: string | null;
  estado: string;
  percentual: number;
  aprovado: boolean | null;          // null = aula em andamento
  dentroS: number;
  perdoadoS: number;
  mensagens: number;
  celularParado: boolean | null;
  bateria: number | null;
  ultimoContatoMs: number;
}

export interface AulaNoRelatorio {
  aulaId: string;
  inicioMs: number;
  emAndamento: boolean;
  alunos: AlunoNoRelatorio[];
}

export interface Relatorio {
  eventType: 'presenca.relatorio.v1';
  turma: string;
  geradoEmMs: number;
  aulas: AulaNoRelatorio[];
}

export function abrirRelatorio(topico: string, texto: string, chaveServidor: string, turma: string):
  { ok: true; relatorio: Relatorio } | { ok: false; motivo: string } {
  const a = abrirDe(topico, texto, chaveServidor);
  if (!a.ok) return a;
  const r = a.carga as Partial<Relatorio>;
  if (r?.eventType !== 'presenca.relatorio.v1' || r.turma !== turma || !Array.isArray(r.aulas)) {
    return { ok: false, motivo: 'relatório fora do contrato' };
  }
  return { ok: true, relatorio: r as Relatorio };
}

const SITUACAO: Record<string, string> = {
  PRESENTE: 'presente', AUSENCIA_TOLERADA: 'fora (tolerância)', FORA: 'fora',
};

export const resultadoDe = (x: AlunoNoRelatorio) =>
  x.aprovado === null ? 'em andamento' : x.aprovado ? 'presente' : 'falta';

const num = (x: number, casas = 1) => x.toFixed(casas).replace('.', ',');

/** Uma célula de CSV: aspas quando precisa (";", aspas ou quebra de linha). */
function celula(v: string | number) {
  const s = String(v);
  return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

const dois = (n: number) => String(n).padStart(2, '0');
function dataHora(ms: number) {
  if (!ms) return '';
  const d = new Date(ms);
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)}/${d.getFullYear()} ${dois(d.getHours())}:${dois(d.getMinutes())}`;
}

export const COLUNAS_CSV = ['aula', 'inicio', 'aluno', 'nome', 'matricula', 'situacao', 'percentual',
  'resultado', 'dentro_s', 'perdoado_s', 'mensagens', 'celular_parado', 'bateria'];

export function relatorioCsv(r: Relatorio): string {
  const linhas = [COLUNAS_CSV.join(';')];
  for (const a of r.aulas) {
    for (const x of a.alunos) {
      linhas.push([
        a.aulaId, dataHora(a.inicioMs), x.aluno, x.nome ?? '', x.matricula ?? '',
        SITUACAO[x.estado] ?? x.estado, num(x.percentual), resultadoDe(x), num(x.dentroS),
        num(x.perdoadoS), x.mensagens,
        x.celularParado === null ? '' : x.celularParado ? 'sim' : 'não',
        x.bateria === null ? '' : `${Math.round(x.bateria * 100)} %`,
      ].map(celula).join(';'));
    }
  }
  return linhas.join('\n') + '\n';
}
