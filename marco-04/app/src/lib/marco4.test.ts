import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Emissor, MedidorBle } from './aparelho.ts';
import { envelopar, publicaDe } from './assinatura.ts';
import { conferirComando, montarComando, montarConfirmacao } from './comandos.ts';
import { HISTERESE_DB } from './config.ts';
import { abrirRelatorio, relatorioCsv, type Relatorio } from './relatorio.ts';
import { montarSensor, ResumoMovimento } from './sensores.ts';
import { aulaEmAndamento, idDaAula, lerTurma, limiaresDa } from './turma.ts';

const SERVIDOR = '33'.repeat(32);
const ADMIN = '44'.repeat(32);
const ESTRANHO = '55'.repeat(32);
const ANCORAS = ['anc-pc-1', 'anc-pc-2'];

// ---------------------------------------------------------------- 2 âncoras
function anuncios(m: MedidorBle, ancora: string, rssi: number, desde: number, n = 10) {
  for (let i = 0; i < n; i++) m.anuncio(rssi, desde + i * 100, 'abcd1234', ancora);
  return desde + n * 100;
}

test('2 âncoras: perto do ESP32 (e longe do notebook) é dentro', () => {
  const m = new MedidorBle({ 'anc-pc-1': -60, 'anc-pc-2': -58 }, ANCORAS);
  let t = anuncios(m, 'anc-pc-1', -80, 0);
  t = anuncios(m, 'anc-pc-2', -50, t - 1000);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
  assert.equal(m.tokens[1], 'abcd1234');
});

test('2 âncoras: só sai quando está longe das duas', () => {
  const m = new MedidorBle({ 'anc-pc-1': -60, 'anc-pc-2': -58 }, ANCORAS);
  let t = anuncios(m, 'anc-pc-1', -50, 0);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
  t = anuncios(m, 'anc-pc-1', -60 - HISTERESE_DB - 5, t, 30);
  assert.equal(m.regiao, 'FORA_ALCANCE');
  anuncios(m, 'anc-pc-2', -55, t, 10);
  assert.equal(m.regiao, 'DENTRO_ALCANCE');
});

test('2 âncoras: ESP32 sem calibração não decide sozinho', () => {
  const m = new MedidorBle({ 'anc-pc-1': null, 'anc-pc-2': null }, ANCORAS);
  anuncios(m, 'anc-pc-2', -40, 0);
  assert.equal(m.regiao, 'INDETERMINADA');
});

test('2 âncoras: anúncio de âncora de outra sala é ignorado', () => {
  const m = new MedidorBle({ 'anc-pc-1': -60 }, ANCORAS);
  anuncios(m, 'anc-xx-9', -40, 0);
  assert.deepEqual(m.rssi, [null, null]);
});

test('turma do Marco 3 (só limiar1mDbm) continua valendo para o notebook', () => {
  assert.deepEqual(limiaresDa({ limiar1mDbm: -61 }), { 'anc-pc-1': -61 });
  const t = lerTurma(JSON.stringify({ eventType: 'presenca.turma.v1', codigo: 'ABC234', nome: 'x', sala: 'sala-pc',
    periodos: [], aulaAgora: null, limiar1mDbm: -61, limiares: { 'anc-pc-2': -57, 'ruim': 3 }, publicadoEmMs: 1 }))!;
  assert.deepEqual(limiaresDa(t), { 'anc-pc-1': -61, 'anc-pc-2': -57 });
});

// ---------------------------------------------------------------- heartbeat v3
test('heartbeat v3 leva turma e aula; a cada 5 s com a mesma sequência', () => {
  const enviados: string[] = [];
  const e = new Emissor({ deviceId: 'cel-ab12', aluno: 'tok-1234abcd', sala: 'sala-pc', ancoras: ANCORAS,
                          turma: 'ABC234', aulaId: 'demo-1' }, (j) => { enviados.push(j); return true; }, 0);
  const m = new MedidorBle({ 'anc-pc-1': -60 }, ANCORAS);
  e.heartbeat(m, 5000, true);
  const hb = JSON.parse(enviados[0]);
  assert.equal(hb.eventType, 'presenca.heartbeat.v3');
  assert.equal(hb.turma, 'ABC234');
  assert.equal(hb.aulaId, 'demo-1');
  assert.equal(hb.ancoras.length, 2);
});

test('id da aula: demonstração pelo início; grade pela data e hora', () => {
  const demo = aulaEmAndamento({ periodos: [], aulaAgora: { inicioMs: 1000, duracaoS: 120 } }, new Date(2000))!;
  assert.equal(idDaAula(demo, new Date(2000)), 'demo-1000');
  const quinta = new Date(2026, 10, 19, 19, 30);
  const grade = aulaEmAndamento({ periodos: [{ dia: 4, inicio: '19:00', fim: '20:40' }], aulaAgora: null }, quinta)!;
  assert.equal(idDaAula(grade, quinta), '2026-11-19-1900');
});

// ---------------------------------------------------------------- sensores
test('acelerômetro: celular parado tem desvio quase zero; na mão, não', () => {
  const r = new ResumoMovimento();
  for (let i = 0; i < 50; i++) r.leitura(0, 0, 1);
  assert.deepEqual(r.fechar(), { movimento: 0, amostras: 50, parado: true });
  for (let i = 0; i < 50; i++) r.leitura(0.1 * Math.sin(i), 0.2 * Math.cos(i), 1 + 0.1 * Math.sin(3 * i));
  const mao = r.fechar()!;
  assert.equal(mao.parado, false);
  assert.ok(mao.movimento > 0.01);
  assert.equal(r.fechar(), null);                    // janela recomeça vazia
});

test('sensor: monta presenca.sensor.v1 com id deduplicável', () => {
  const s = montarSensor({ aluno: 'tok-1234abcd', deviceId: 'cel-ab12', turma: 'ABC234' }, 'a1b2', 7, 123.4,
                         { movimento: 0.002, amostras: 50, parado: true }, { nivel: 0.4567, carregando: false });
  assert.equal(s.sensorId, 'cel-ab12#a1b2#7');
  assert.deepEqual(s.bateria, { nivel: 0.46, carregando: false });
  assert.equal(montarSensor({ aluno: 'a', deviceId: 'b', turma: 'c' }, 'x', 1, 0, null, { nivel: -1, carregando: false }).bateria, null);
});

// ---------------------------------------------------------------- atuador
const QUEM = { aluno: 'tok-1234abcd', turma: 'ABC234', chaveServidor: publicaDe(SERVIDOR), chaveAdmin: publicaDe(ADMIN) };
const TOPICO = 'x/comando/tok-1234abcd';

function comando(chave: string, extra: object = {}, agora = 1_000_000) {
  const c = { ...montarComando({ aluno: QUEM.aluno, turma: QUEM.turma, tipo: 'chamar', texto: 'oi' }, agora), ...extra };
  return { c, texto: envelopar(chave, 'x', TOPICO, c) };
}

test('comando do servidor e do professor são executados', () => {
  const vistos = new Set<string>();
  const a = conferirComando(TOPICO, comando(SERVIDOR).texto, QUEM, 1_000_500, vistos);
  assert.ok(a.ok && a.de === 'servidor');
  const b = conferirComando(TOPICO, comando(ADMIN).texto, QUEM, 1_000_500, vistos);
  assert.ok(b.ok && b.de === 'professor');
});

test('comando de estranho (mesmo com a senha do broker) é recusado', () => {
  const r = conferirComando(TOPICO, comando(ESTRANHO).texto, QUEM, 1_000_500, new Set());
  assert.equal(r.ok, false);
});

test('comando repetido, vencido ou de outro aluno não é executado', () => {
  const { c, texto } = comando(SERVIDOR);
  assert.equal(conferirComando(TOPICO, texto, QUEM, 1_000_500, new Set([c.comandoId])).ok, false);
  assert.equal(conferirComando(TOPICO, texto, QUEM, 1_000_000 + 61_000 + 30_000, new Set()).ok, false);
  const outro = comando(SERVIDOR, { aluno: 'tok-99999999' }).texto;
  assert.equal(conferirComando(TOPICO, outro, QUEM, 1_000_500, new Set()).ok, false);
});

test('comando com tópico trocado (copiado de outro aluno) falha na assinatura', () => {
  const { texto } = comando(SERVIDOR);
  assert.equal(conferirComando('x/comando/tok-99999999', texto, QUEM, 1_000_500, new Set()).ok, false);
});

test('confirmação respeita o contrato', () => {
  const ack = montarConfirmacao('srv-12345678', 'tok-1234abcd', 'respondido', 5);
  assert.deepEqual(Object.keys(ack).sort(), ['aluno', 'comandoId', 'emMs', 'eventType', 'resultado']);
});

// ---------------------------------------------------------------- relatório
const REL: Relatorio = { eventType: 'presenca.relatorio.v1', turma: 'ABC234', geradoEmMs: 1, aulas: [
  { aulaId: 'demo-1', inicioMs: new Date(2026, 10, 19, 19, 0).getTime(), emAndamento: false, alunos: [
    { aluno: 'tok-1234abcd', nome: 'Silva; Ana', matricula: '1', estado: 'PRESENTE', percentual: 87.5,
      aprovado: true, dentroS: 100.25, perdoadoS: 5, mensagens: 24, celularParado: false, bateria: 0.8,
      ultimoContatoMs: 1 },
  ] }] };

test('relatório só vale assinado pelo servidor e da turma certa', () => {
  const t = 'x/relatorio/ABC234';
  assert.ok(abrirRelatorio(t, envelopar(SERVIDOR, 'servidor', t, REL), publicaDe(SERVIDOR), 'ABC234').ok);
  assert.equal(abrirRelatorio(t, envelopar(ESTRANHO, 'servidor', t, REL), publicaDe(SERVIDOR), 'ABC234').ok, false);
  assert.equal(abrirRelatorio(t, envelopar(SERVIDOR, 'servidor', t, REL), publicaDe(SERVIDOR), 'ZZZ999').ok, false);
});

test('CSV: ";" e vírgula decimal, e nome com ";" vai entre aspas', () => {
  const [cab, linha] = relatorioCsv(REL).trim().split('\n');
  assert.equal(cab.split(';')[0], 'aula');
  assert.equal(linha, 'demo-1;19/11/2026 19:00;tok-1234abcd;"Silva; Ana";1;presente;87,5;presente;100,3;5,0;24;não;80 %');
});
