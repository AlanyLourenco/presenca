import { test } from 'node:test';
import assert from 'node:assert/strict';
import { abrirDe, abrirEnvelope, envelopar, identidadeDaChave, publicaDe } from './assinatura.ts';
import { Emissor, MedidorBle } from './aparelho.ts';

const A = '11'.repeat(32);
const B = '22'.repeat(32);
const T = 'ufg/ssu/presenca/alany/m3/sala-pc/heartbeat';

test('o pseudônimo é o mesmo que o servidor calcula para a mesma chave', () => {
  // valor conferido com seguranca.identidade_da_chave() em Python
  assert.deepEqual(identidadeDaChave(publicaDe(A)), { aluno: 'tok-10ba682c', deviceId: 'cel-8ad1' });
});

test('envelope assinado abre e devolve a carga', () => {
  const a = abrirEnvelope(T, envelopar(A, 'eu', T, { x: 1 }));
  assert.ok(a.ok && (a.carga as { x: number }).x === 1 && a.chavePublica === publicaDe(A));
});

test('carga alterada, outro tópico ou mensagem crua são recusados', () => {
  const env = JSON.parse(envelopar(A, 'eu', T, { estado: 'FORA' }));
  env.carga = env.carga.replace('FORA', 'PRESENTE');
  assert.deepEqual(abrirEnvelope(T, JSON.stringify(env)), { ok: false, motivo: 'assinatura falsa' });
  assert.equal(abrirEnvelope(T + '/x', envelopar(A, 'eu', T, {})).ok, false);
  assert.deepEqual(abrirEnvelope(T, '{"estado":"PRESENTE"}'), { ok: false, motivo: 'sem assinatura' });
});

test('estado assinado por outra chave que não a do servidor é recusado', () => {
  assert.deepEqual(abrirDe(T, envelopar(B, 'servidor', T, {}), publicaDe(A)),
    { ok: false, motivo: 'chave desconhecida' });
  assert.equal(abrirDe(T, envelopar(A, 'servidor', T, {}), publicaDe(A)).ok, true);
});

test('heartbeat v2 leva o token ouvido; âncora calada vai sem token', () => {
  const m = new MedidorBle(-60);
  for (let i = 0; i < 5; i++) m.anuncio(-50, 1000 + i * 100, 'a1b2c3d4');
  m.atualizar(1500);
  const saidas: string[] = [];
  const e = new Emissor({ deviceId: 'cel-8ad1', aluno: 'tok-10ba682c', sala: 'sala-pc', ancoras: ['anc-pc-1'] },
    (j) => { saidas.push(j); return true; }, 1000);
  e.heartbeat(m, 1500, true);
  const hb = JSON.parse(saidas[0]);
  assert.equal(hb.eventType, 'presenca.heartbeat.v2');
  assert.deepEqual(hb.ancoras, [{ id: 'anc-pc-1', rssi: -50, token: 'a1b2c3d4' }]);
  m.atualizar(9000);                                    // 7,5 s sem anúncio
  e.heartbeat(m, 9000, true);
  assert.deepEqual(JSON.parse(saidas[1]).ancoras, [{ id: 'anc-pc-1', rssi: null, token: null }]);
});
