import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Emissor, Medidor } from './aparelho.ts';
import { JANELA_MEDIA, MAX_FILA } from './config.ts';

const ID = { deviceId: 'cel-ab12', aluno: 'tok-1234abcd', sala: 'sala-204',
             ancoras: ['anc-204-A', 'anc-204-B', 'anc-204-C'] as const };

function medir(m: Medidor, rssi: number[], vezes = JANELA_MEDIA) {
  for (let i = 0; i < vezes; i++) m.amostrar(rssi);
}

test('região fica indeterminada até a janela encher e então entra', () => {
  const m = new Medidor();
  medir(m, [-56, -56, -56], JANELA_MEDIA - 1);
  assert.equal(m.regiao, 'INDETERMINADA');
  m.amostrar([-56, -56, -56]);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
});

test('histerese: na faixa morta mantém, abaixo de −85 sai', () => {
  const m = new Medidor();
  medir(m, [-60, -60, -60]);
  medir(m, [-78, -78, -78]);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
  medir(m, [-90, -90, -90]);
  assert.equal(m.regiao, 'FORA_ALCANCE');
  medir(m, [-78, -78, -78]);
  assert.equal(m.regiao, 'FORA_ALCANCE');
});

test('abaixo de −100 a âncora vira não ouvida e nenhuma ouvida é fora', () => {
  const m = new Medidor();
  medir(m, [-56, -56, -56]);
  m.amostrar([-105, -105, -105]);
  assert.deepEqual(m.rssi, [null, null, null]);
  assert.equal(m.regiao, 'FORA_ALCANCE');
});

test('heartbeat segue o contrato do ESP32', () => {
  const m = new Medidor();
  medir(m, [-62, -62, -59.4]);
  const enviados: string[] = [];
  const e = new Emissor(ID, (j) => (enviados.push(j), true), 1000, '76fd');
  e.heartbeat(m, 1500, true);
  const hb = JSON.parse(enviados[0]);
  assert.equal(hb.eventId, 'cel-ab12#76fd#1');
  assert.equal(hb.eventTimeMs, 500);
  assert.equal(hb.value, -59.4);
  assert.equal(hb.state, 'DENTRO_ALCANCE');
  assert.equal(hb.ancoras.length, 3);
  assert.equal(hb.bufferizado, false);
});

test('anomalias: duplicata reenvia igual, fora de ordem troca, salto pula 5', () => {
  const m = new Medidor();
  medir(m, [-56, -56, -56]);
  const seqs: number[] = [];
  const e = new Emissor(ID, (j) => (seqs.push(JSON.parse(j).sequence), true), 0, 'aaaa');
  e.heartbeat(m, 0, true);                         // 1
  e.armarAnomalia(); e.heartbeat(m, 500, true);    // duplicata do 1
  e.armarAnomalia(); e.heartbeat(m, 1000, true);   // 2 retido
  e.heartbeat(m, 1500, true);                      // 3, depois 2
  e.armarAnomalia(); e.heartbeat(m, 2000, true);   // salto: 9
  assert.deepEqual(seqs, [1, 1, 3, 2, 9]);
});

test('sem rede retém, entrega bufferizado e descarta o mais antigo no teto', () => {
  const m = new Medidor();
  medir(m, [-56, -56, -56]);
  const enviados: any[] = [];
  const e = new Emissor(ID, (j) => (enviados.push(JSON.parse(j)), true), 0, 'bbbb');
  for (let i = 0; i < MAX_FILA + 3; i++) e.heartbeat(m, i * 500, false);
  assert.equal(e.fila.length, MAX_FILA);
  assert.equal(e.descartadosFila, 3);
  assert.equal(e.drenar(true), MAX_FILA);
  assert.equal(enviados[0].sequence, 4);
  assert.equal(enviados[0].eventTimeMs, 1500);
  assert.ok(enviados.every((h) => h.bufferizado));
});

// ---------------------------------------------------------------------------
// Protótipo 1 — âncora Bluetooth única
// ---------------------------------------------------------------------------
import { limiarCalibrado, MedidorBle } from './aparelho.ts';
import { BLE_SUMIU_MS, HISTERESE_DB } from './config.ts';

function anuncios(m: MedidorBle, rssi: number, desde: number, n = 10) {
  for (let i = 0; i < n; i++) m.anuncio(rssi, desde + i * 100);
  return desde + n * 100;
}

test('BLE: acima do limiar de 1 m entra; na histerese mantém; abaixo dela sai', () => {
  const m = new MedidorBle(-60);
  let t = anuncios(m, -55, 0);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
  t = anuncios(m, -60 - HISTERESE_DB + 1, t, 30);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
  anuncios(m, -60 - HISTERESE_DB - 3, t, 30);
  assert.equal(m.regiao, 'FORA_ALCANCE');
});

test('BLE: um pacote isolado não muda a região (mediana)', () => {
  const m = new MedidorBle(-60);
  const t = anuncios(m, -50, 0);
  m.anuncio(-90, t);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
});

test('BLE: âncora calada vira não ouvida e fora do alcance', () => {
  const m = new MedidorBle(-60);
  const t = anuncios(m, -50, 0);
  m.atualizar(t + BLE_SUMIU_MS + 1);
  assert.deepEqual(m.rssi, [null]);
  assert.equal(m.regiao, 'FORA_ALCANCE');
});

test('BLE: calibração é a mediana e a distância a 1 m sai 1 m', () => {
  assert.equal(limiarCalibrado([-58, -61, -60, -75, -59]), -60);
  assert.equal(limiarCalibrado([-60]), null);
  const m = new MedidorBle(-60);
  anuncios(m, -60, 0);
  assert.equal(m.distancia(), 1);
});

test('BLE: sem calibração não decide dentro nem fora', () => {
  const m = new MedidorBle(null);
  anuncios(m, -40, 0);
  assert.equal(m.regiao, 'INDETERMINADA');
  assert.equal(m.distancia(), null);
  assert.equal(m.rssi[0], -40);
});
