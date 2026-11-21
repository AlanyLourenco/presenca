/**
 * Sensores do celular — Marco 4 ("o app acessa pelo menos 1 sensor e esse dado
 * vai para o broker").
 *
 * ACELERÔMETRO (a IMU do celular): o que interessa não é a aceleração em si, e
 * sim se o celular se MEXE. Um celular que ficou parado sobre a mesa a aula
 * inteira, sem nenhum movimento de quem o carrega, é indício de aparelho
 * emprestado ou deixado na sala — a mitigação de "empréstimo de aparelho" que
 * o projeto previa (variância da IMU + revisão do professor). O app manda o
 * desvio-padrão do módulo da aceleração na janela de cada heartbeat (5 s).
 *
 * BATERIA: quando o celular some, o servidor consegue dizer "provavelmente
 * bateria" pela última leitura, em vez de adivinhar pelo formato do RSSI
 * (que o projeto rejeitou).
 *
 * Módulo puro: a leitura do hardware fica em usar-sensores.ts.
 */
import { MOVIMENTO_PARADO_G } from './config.ts';

/** Acumula as leituras do acelerômetro entre dois heartbeats. */
export class ResumoMovimento {
  private n = 0;
  private soma = 0;
  private somaQuadrados = 0;

  /** Uma leitura do acelerômetro, em g (x, y, z). */
  leitura(x: number, y: number, z: number) {
    if (![x, y, z].every(Number.isFinite)) return;
    const modulo = Math.sqrt(x * x + y * y + z * z);
    this.n++;
    this.soma += modulo;
    this.somaQuadrados += modulo * modulo;
  }

  /** Fecha a janela: devolve o resumo e recomeça. null se não houve leitura. */
  fechar(): { movimento: number; amostras: number; parado: boolean } | null {
    if (this.n === 0) return null;
    const media = this.soma / this.n;
    const variancia = Math.max(0, this.somaQuadrados / this.n - media * media);
    const movimento = Math.round(Math.sqrt(variancia) * 10000) / 10000;
    const r = { movimento, amostras: this.n, parado: movimento < MOVIMENTO_PARADO_G };
    this.n = 0;
    this.soma = 0;
    this.somaQuadrados = 0;
    return r;
  }
}

export interface Bateria { nivel: number; carregando: boolean }

/** presenca.sensor.v1 */
export function montarSensor(id: { aluno: string; deviceId: string; turma: string }, bootId: string,
                             n: number, agoraMs: number,
                             acelerometro: ReturnType<ResumoMovimento['fechar']>,
                             bateria: Bateria | null) {
  return {
    eventType: 'presenca.sensor.v1' as const,
    sensorId: `${id.deviceId}#${bootId}#${n}`,
    aluno: id.aluno,
    deviceId: id.deviceId,
    turma: id.turma,
    medidoEmMs: Math.round(agoraMs),
    acelerometro,
    bateria: bateria && Number.isFinite(bateria.nivel) && bateria.nivel >= 0
      ? { nivel: Math.round(bateria.nivel * 100) / 100, carregando: bateria.carregando }
      : null,
  };
}
