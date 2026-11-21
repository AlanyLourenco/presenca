import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  aulaEmAndamento, gerarCodigo, lerTurma, normalizarCodigo, proximaAula, type Turma,
} from './turma.ts';

const turma: Turma = {
  eventType: 'presenca.turma.v1', codigo: 'ABC234', nome: 'SSU', sala: 'sala-204',
  periodos: [{ dia: 4, inicio: '19:00', fim: '20:40' }], aulaAgora: null, limiar1mDbm: -62,
  publicadoEmMs: 0,
};
// 2026-10-08 é quinta-feira (dia 4)
const quinta = (h: number, m: number) => new Date(2026, 9, 8, h, m);

test('código: gera no alfabeto e aceita as formas digitadas e do QR', () => {
  const c = gerarCodigo();
  assert.equal(normalizarCodigo(c), c);
  assert.equal(normalizarCodigo(' abc 234 '), 'ABC234');
  assert.equal(normalizarCodigo('presenca://turma/ABC234'), 'ABC234');
  assert.equal(normalizarCodigo('ABC23'), null);
  assert.equal(normalizarCodigo('ABC230'), null);   // 0 não existe no alfabeto
});

test('aula em andamento pela grade, com fim no horário do período', () => {
  assert.equal(aulaEmAndamento(turma, quinta(18, 59)), null);
  const a = aulaEmAndamento(turma, quinta(19, 30));
  assert.equal(a?.tipo, 'grade');
  assert.equal(a!.fimMs, quinta(20, 40).getTime());
  assert.equal(aulaEmAndamento(turma, quinta(20, 40)), null);
});

test('aula de demonstração vale só na janela dela', () => {
  const inicio = quinta(10, 0).getTime();
  const t = { ...turma, aulaAgora: { inicioMs: inicio, duracaoS: 100 } };
  assert.equal(aulaEmAndamento(t, new Date(inicio + 50_000))?.tipo, 'demonstracao');
  assert.equal(aulaEmAndamento(t, new Date(inicio + 100_000)), null);
});

test('próxima aula é a da semana seguinte quando a de hoje já passou', () => {
  assert.deepEqual(proximaAula(turma.periodos, quinta(21, 0)), new Date(2026, 9, 15, 19, 0));
});

test('turma recebida da rede é conferida', () => {
  assert.ok(lerTurma(JSON.stringify(turma)));
  assert.equal(lerTurma('{"eventType":"outra"}'), null);
  assert.equal(lerTurma(JSON.stringify({ ...turma, periodos: [{ dia: 1, inicio: '20:00', fim: '19:00' }] })), null);
  assert.equal(lerTurma('não é json'), null);
});

test('o limiar de 1 m viaja com a turma; valor absurdo vira "não calibrado"', () => {
  assert.equal(lerTurma(JSON.stringify(turma))!.limiar1mDbm, -62);
  assert.equal(lerTurma(JSON.stringify({ ...turma, limiar1mDbm: 10 }))!.limiar1mDbm, null);
  const { limiar1mDbm: _, ...semLimiar } = turma;
  assert.equal(lerTurma(JSON.stringify(semLimiar))!.limiar1mDbm, null);
});
