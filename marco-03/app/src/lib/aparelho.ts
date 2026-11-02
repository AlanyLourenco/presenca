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
 * Recebe cada anúncio Bluetooth da âncora com o RSSI medido pelo rádio do
 * celular. O RSSI de BLE oscila muito de um pacote para o outro, então vale a
 * MEDIANA dos últimos BLE_JANELA_MS. A região usa o limiar calibrado a 1 m:
 * entra acima dele, só sai HISTERESE_DB abaixo. Sem anúncio por BLE_SUMIU_MS,
 * a âncora deixa de ser ouvida e o aparelho está fora do alcance. Sem
 * calibração (limiar null) não há como saber o que é 1 m: a região fica
 * INDETERMINADA e o servidor trata como neutro.
 */
export class MedidorBle implements Medicao {
  private amostras: { t: number; rssi: number }[] = [];
  private ultimoToken: string | null = null;
  rssi: (number | null)[] = [null];
  tokens: (string | null)[] = [null];
  regiao: Regiao = 'INDETERMINADA';
  amostrasInvalidas = 0;
  limiar: number | null;

  constructor(limiar: number | null) {
    this.limiar = limiar;
  }

  /**
   * Um anúncio recebido. O token é só repassado ao servidor: o celular não
   * tem o segredo da âncora e não consegue nem conferir nem fabricar um.
   */
  anuncio(rssi: number, agoraMs: number, token: string | null = null) {
    if (!Number.isFinite(rssi) || rssi > -20 || rssi < -127) {   // fora do que o rádio entrega
      this.amostrasInvalidas++;
      return;
    }
    if (token) this.ultimoToken = token;
    this.amostras.push({ t: agoraMs, rssi });
    this.atualizar(agoraMs);
  }

  /** Chamado periodicamente: descarta o que envelheceu e refaz a região. */
  atualizar(agoraMs: number) {
    this.amostras = this.amostras.filter((a) => agoraMs - a.t <= BLE_JANELA_MS);
    const ultimo = this.amostras.at(-1);
    if (!ultimo || agoraMs - ultimo.t > BLE_SUMIU_MS) {
      this.rssi = [null];
      this.tokens = [null];
      this.regiao = 'FORA_ALCANCE';
      return;
    }
    this.rssi = [mediana(this.amostras.map((a) => a.rssi))];
    this.tokens = [this.ultimoToken];
    if (this.limiar === null) { this.regiao = 'INDETERMINADA'; return; }
    if (this.amostras.length < BLE_MINIMO_AMOSTRAS) return;     // mantém a anterior
    const r = this.rssi[0]!;
    if (r > this.limiar) this.regiao = 'DENTRO_ALCANCE';
    else if (r < this.limiar - HISTERESE_DB) this.regiao = 'FORA_ALCANCE';
    else if (this.regiao === 'INDETERMINADA') this.regiao = 'FORA_ALCANCE';
  }

  /** Distância estimada a partir do RSSI a 1 m (só para a tela). */
  distancia(): number | null {
    const r = this.rssi[0];
    if (r === null || this.limiar === null) return null;
    return 10 ** ((this.limiar - r) / (10 * EXPOENTE_PERDA));
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
  return {
    eventType: 'presenca.heartbeat.v2',
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
