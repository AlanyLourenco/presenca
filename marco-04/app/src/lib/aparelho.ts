/**
 * Lógica do aparelho do estudante, sem rede e sem tela.
 *
 * É a mesma do ESP32 do Marco 2 (marco-02/aparelho/sketch.ino), portada linha a
 * linha: média móvel por âncora, âncora não ouvida, região de rádio com
 * histerese, heartbeat com sequência por boot, fila durante a queda de rede e
 * as três anomalias do teste adversarial. Fica num módulo puro para poder ser
 * testada com `npm test`.
 */
import {
  BLE_JANELA_MS, BLE_MINIMO_AMOSTRAS, BLE_SUMIU_MS, EXPOENTE_PERDA, HISTERESE_DB,
  JANELA_MEDIA, LIMIAR_ENTRADA, LIMIAR_SAIDA, MAX_FILA, RSSI_NAO_OUVIDA,
} from './config.ts';

export type Regiao = 'INDETERMINADA' | 'DENTRO_ALCANCE' | 'FORA_ALCANCE';
export type Anomalia = 'nenhuma' | 'duplicata' | 'fora-de-ordem' | 'salto';
export const CICLO_ANOMALIAS: Anomalia[] = ['duplicata', 'fora-de-ordem', 'salto'];

// ---------------------------------------------------------------------------
// Medição: filtro e região
// ---------------------------------------------------------------------------
export class Medidor {
  private janela: number[][] = [[], [], []];
  private indice = [0, 0, 0];
  rssi: (number | null)[] = [null, null, null];   // filtrado; null = não ouvida
  tokens: (string | null)[] = [null, null, null];  // âncoras simuladas não anunciam token
  amostrasInvalidas = 0;
  regiao: Regiao = 'INDETERMINADA';

  /** Uma amostra bruta por âncora (dBm). */
  amostrar(brutos: number[]) {
    for (let i = 0; i < 3; i++) {
      const bruto = brutos[i];
      if (!Number.isFinite(bruto) || bruto > -30) {       // fisicamente impossível
        this.amostrasInvalidas++;
        continue;
      }
      // Abaixo de −100 dBm não é número baixo, é falta de dado: a janela é
      // esvaziada para valores velhos não se misturarem quando ela voltar.
      if (bruto < RSSI_NAO_OUVIDA) {
        this.rssi[i] = null;
        this.janela[i] = [];
        this.indice[i] = 0;
        continue;
      }
      const j = this.janela[i];
      j[this.indice[i]] = bruto;
      this.indice[i] = (this.indice[i] + 1) % JANELA_MEDIA;
      this.rssi[i] = j.reduce((a, b) => a + b, 0) / j.length;
    }
    this.atualizarRegiao();
  }

  private cheia(i: number) {
    return this.rssi[i] !== null && this.janela[i].length === JANELA_MEDIA;
  }

  /** Melhor sinal entre as âncoras ouvidas com a janela cheia. */
  melhor(): number | null {
    let m: number | null = null;
    for (let i = 0; i < 3; i++) {
      const r = this.rssi[i];
      if (this.cheia(i) && r !== null && (m === null || r > m)) m = r;
    }
    return m;
  }

  /** Entra acima de −70 dBm, só sai abaixo de −85; entre os dois, mantém. */
  private atualizarRegiao() {
    const nenhumaOuvida = this.rssi.every((r) => r === null);
    const algumaCheia = [0, 1, 2].some((i) => this.cheia(i));
    const melhor = this.melhor();
    if (nenhumaOuvida) this.regiao = 'FORA_ALCANCE';
    else if (melhor === null) this.regiao = algumaCheia ? this.regiao : 'INDETERMINADA';
    else if (melhor > LIMIAR_ENTRADA) this.regiao = 'DENTRO_ALCANCE';
    else if (melhor < LIMIAR_SAIDA) this.regiao = 'FORA_ALCANCE';
    else if (this.regiao === 'INDETERMINADA') this.regiao = 'FORA_ALCANCE'; // faixa morta sem histórico
  }
}

// ---------------------------------------------------------------------------
// PROTÓTIPO 1 — uma âncora Bluetooth de verdade (o notebook)
// ---------------------------------------------------------------------------
/** O que o Emissor precisa saber da medição, venha ela de onde vier. */
export interface Medicao {
  rssi: (number | null)[];
  /** Marco 3: o último token ouvido de cada âncora (null = não ouvida). */
  tokens: (string | null)[];
  regiao: Regiao;
  amostrasInvalidas: number;
}

const mediana = (xs: number[]) => {
  const o = [...xs].sort((a, b) => a - b);
  const m = o.length >> 1;
  return o.length % 2 ? o[m] : (o[m - 1] + o[m]) / 2;
};

/**
 * Recebe cada anúncio Bluetooth das âncoras com o RSSI medido pelo rádio do
 * celular. O RSSI de BLE oscila muito de um pacote para o outro, então vale a
 * MEDIANA dos últimos BLE_JANELA_MS, por âncora. Sem anúncio por BLE_SUMIU_MS,
 * a âncora deixa de ser ouvida.
 *
 * Marco 4 — DUAS ÂNCORAS (o notebook e o ESP32). Cada uma tem o seu limiar de
 * 1 m, calibrado pelo administrador (rádios diferentes transmitem com
 * potências diferentes). A região é:
 *   DENTRO_ALCANCE  se QUALQUER âncora está acima do seu limiar (perto de uma)
 *   FORA_ALCANCE    se todas as ouvidas estão HISTERESE_DB abaixo do limiar,
 *                   ou nenhuma é ouvida
 *   (entre os dois, mantém a anterior)
 * Sem nenhuma calibração não há como saber o que é 1 m: INDETERMINADA, e o
 * servidor trata como neutro.
 */
export class MedidorBle implements Medicao {
  readonly ancoras: readonly string[];
  private amostras = new Map<string, { t: number; rssi: number }[]>();
  private ultimoToken = new Map<string, string>();
  rssi: (number | null)[];
  tokens: (string | null)[];
  regiao: Regiao = 'INDETERMINADA';
  amostrasInvalidas = 0;
  limiares: Record<string, number | null>;

  /** `limiar`: um número (só a primeira âncora) ou um limiar por âncora. */
  constructor(limiar: number | null | Record<string, number | null>,
              ancoras: readonly string[] = ['anc-pc-1']) {
    this.ancoras = ancoras;
    this.rssi = ancoras.map(() => null);
    this.tokens = ancoras.map(() => null);
    this.limiares = {};
    this.definirLimiares(limiar);
  }

  definirLimiares(limiar: number | null | Record<string, number | null>) {
    this.limiares = typeof limiar === 'object' && limiar !== null
      ? { ...limiar } : { [this.ancoras[0]]: limiar };
  }

  /** Limiar da primeira âncora (compatível com o Marco 3). */
  get limiar() { return this.limiares[this.ancoras[0]] ?? null; }
  set limiar(v: number | null) { this.limiares[this.ancoras[0]] = v; }

  /**
   * Um anúncio recebido. O token é só repassado ao servidor: o celular não
   * tem o segredo da âncora e não consegue nem conferir nem fabricar um.
   */
  anuncio(rssi: number, agoraMs: number, token: string | null = null, ancora = this.ancoras[0]) {
    if (!this.ancoras.includes(ancora)) return;                 // âncora de outra sala
    if (!Number.isFinite(rssi) || rssi > -20 || rssi < -127) {   // fora do que o rádio entrega
      this.amostrasInvalidas++;
      return;
    }
    if (token) this.ultimoToken.set(ancora, token);
    const lista = this.amostras.get(ancora) ?? [];
    lista.push({ t: agoraMs, rssi });
    this.amostras.set(ancora, lista);
    this.atualizar(agoraMs);
  }

  /** Chamado periodicamente: descarta o que envelheceu e refaz a região. */
  atualizar(agoraMs: number) {
    const contagem: number[] = [];
    this.ancoras.forEach((a, i) => {
      const lista = (this.amostras.get(a) ?? []).filter((x) => agoraMs - x.t <= BLE_JANELA_MS);
      this.amostras.set(a, lista);
      const ultimo = lista.at(-1);
      contagem[i] = lista.length;
      if (!ultimo || agoraMs - ultimo.t > BLE_SUMIU_MS) {
        this.rssi[i] = null;
        this.tokens[i] = null;
      } else {
        this.rssi[i] = mediana(lista.map((x) => x.rssi));
        this.tokens[i] = this.ultimoToken.get(a) ?? null;
      }
    });
    if (this.rssi.every((r) => r === null)) { this.regiao = 'FORA_ALCANCE'; return; }

    const calibradas = this.ancoras
      .map((a, i) => ({ r: this.rssi[i], lim: this.limiares[a] ?? null, n: contagem[i] }))
      .filter((x): x is { r: number; lim: number; n: number } => x.r !== null && x.lim !== null);
    if (calibradas.length === 0) { this.regiao = 'INDETERMINADA'; return; }
    const firmes = calibradas.filter((x) => x.n >= BLE_MINIMO_AMOSTRAS);
    if (firmes.length === 0) return;                            // mantém a anterior

    if (firmes.some((x) => x.r > x.lim)) this.regiao = 'DENTRO_ALCANCE';
    else if (firmes.every((x) => x.r < x.lim - HISTERESE_DB)) this.regiao = 'FORA_ALCANCE';
    else if (this.regiao === 'INDETERMINADA') this.regiao = 'FORA_ALCANCE';
  }

  /** Distância estimada até a âncora mais próxima (só para a tela). */
  distancia(): number | null {
    const d = this.distancias().filter((x): x is number => x !== null);
    return d.length ? Math.min(...d) : null;
  }

  /** Distância estimada até cada âncora (null = não ouvida ou sem calibração). */
  distancias(): (number | null)[] {
    return this.ancoras.map((a, i) => {
      const r = this.rssi[i];
      const lim = this.limiares[a] ?? null;
      return r === null || lim === null ? null : 10 ** ((lim - r) / (10 * EXPOENTE_PERDA));
    });
  }
}

/** A calibração: mediana de tudo o que chegou durante a janela, parado a 1 m. */
export function limiarCalibrado(rssis: number[]): number | null {
  return rssis.length >= BLE_MINIMO_AMOSTRAS ? Math.round(mediana(rssis)) : null;
}

// ---------------------------------------------------------------------------
// Heartbeat
// ---------------------------------------------------------------------------
export interface Identidade {
  deviceId: string;
  aluno: string;
  sala: string;
  ancoras: readonly string[];
  /** Marco 4: com turma e aula, o heartbeat vai como v3 (o relatório agrupa por elas). */
  turma?: string;
  aulaId?: string;
}

interface Retrato {
  seq: number;
  tempoMs: number;
  medidoEmMs: number;
  rssi: (number | null)[];
  tokens: (string | null)[];
  regiao: Regiao;
  invalidas: number;
}

const um = (x: number) => Math.round(x * 10) / 10;

export function montarHeartbeat(id: Identidade, bootId: string, r: Retrato,
                                bufferizado: boolean, anomalia: Anomalia) {
  const ouvidas = r.rssi.filter((x): x is number => x !== null);
  const v3 = id.turma && id.aulaId ? { turma: id.turma, aulaId: id.aulaId } : {};
  return {
    eventType: id.turma && id.aulaId ? 'presenca.heartbeat.v3' : 'presenca.heartbeat.v2',
    ...v3,
    eventId: `${id.deviceId}#${bootId}#${r.seq}`,
    deviceId: id.deviceId,
    entityId: id.sala,
    aluno: id.aluno,
    bootId,
    eventTimeMs: r.tempoMs,
    medidoEmMs: r.medidoEmMs,
    sequence: r.seq,
    value: ouvidas.length ? um(Math.max(...ouvidas)) : null,
    unit: 'dBm',
    state: r.regiao,
    ancoras: id.ancoras.map((a, i) => (r.rssi[i] === null
      ? { id: a, rssi: null, token: null }
      : { id: a, rssi: um(r.rssi[i]!), token: r.tokens[i] ?? null })),
    amostrasInvalidas: r.invalidas,
    bufferizado,
    anomaliaInjetada: anomalia,
  };
}

/**
 * Produz os heartbeats de um "boot" (uma abertura da tela de aula) e decide o
 * que vai para a rede agora, o que fica retido e o que é adulterado pelo
 * teste adversarial. `publicar` devolve false se a rede não aceitou.
 */
export class Emissor {
  readonly bootId: string;
  private inicioMs: number;
  sequencia = 0;
  fila: Retrato[] = [];
  descartadosFila = 0;
  redeSimuladaCaida = false;
  proximaAnomalia: Anomalia = 'duplicata';
  anomaliaArmada: Anomalia = 'nenhuma';
  private ultimoPayload = '';
  private retido = '';

  private id: Identidade;
  private publicar: (json: string) => boolean;

  constructor(id: Identidade, publicar: (json: string) => boolean, agoraMs: number, bootId?: string) {
    this.id = id;
    this.publicar = publicar;
    this.bootId = bootId ?? Math.floor(Math.random() * 0x10000).toString(16).padStart(4, '0');
    this.inicioMs = agoraMs;
  }

  /** Arma a próxima anomalia do ciclo (o botão azul do ESP32). */
  armarAnomalia(): Anomalia {
    this.anomaliaArmada = this.proximaAnomalia;
    const i = CICLO_ANOMALIAS.indexOf(this.proximaAnomalia);
    this.proximaAnomalia = CICLO_ANOMALIAS[(i + 1) % CICLO_ANOMALIAS.length];
    return this.anomaliaArmada;
  }

  private enviar(json: string, conectado: boolean) {
    if (this.redeSimuladaCaida || !conectado) return false;
    return this.publicar(json);
  }

  private enfileirar(r: Retrato) {
    if (this.fila.length >= MAX_FILA) {
      // Teto: descarta o mais antigo. O servidor verá um salto na sequência.
      this.fila.shift();
      this.descartadosFila++;
    }
    this.fila.push(r);
  }

  /** Entrega os retidos com bufferizado=true e o eventTimeMs original. */
  drenar(conectado: boolean) {
    let enviados = 0;
    while (this.fila.length && !this.redeSimuladaCaida && conectado) {
      const r = this.fila[0];
      if (!this.publicar(JSON.stringify(montarHeartbeat(this.id, this.bootId, r, true, 'nenhuma')))) break;
      this.fila.shift();
      enviados++;
    }
    return enviados;
  }

  /** Um heartbeat, com a medição atual. Devolve o JSON produzido (ou null). */
  heartbeat(m: Medicao, agoraMs: number, conectado: boolean): string | null {
    const anom = this.anomaliaArmada;
    this.anomaliaArmada = 'nenhuma';

    if (anom === 'duplicata' && this.ultimoPayload) {
      this.enviar(this.ultimoPayload, conectado);          // mesmo eventId, byte a byte
      return this.ultimoPayload;
    }
    if (anom === 'salto') this.sequencia += 5;            // 5 números nunca enviados
    this.sequencia++;

    const r: Retrato = {
      seq: this.sequencia,
      tempoMs: Math.max(0, Math.round(agoraMs - this.inicioMs)),
      medidoEmMs: Math.round(agoraMs),
      rssi: [...m.rssi],
      tokens: [...m.tokens],
      regiao: m.regiao,
      invalidas: m.amostrasInvalidas,
    };
    const json = JSON.stringify(montarHeartbeat(this.id, this.bootId, r, false, anom));

    if (this.redeSimuladaCaida || !conectado) {
      this.enfileirar(r);
      return json;
    }
    if (anom === 'fora-de-ordem') {                       // segura este, entrega depois do próximo
      this.retido = json;
      return json;
    }
    this.enviar(json, conectado);
    this.ultimoPayload = json;
    if (this.retido) {
      this.enviar(this.retido, conectado);
      this.retido = '';
    }
    return json;
  }
}
