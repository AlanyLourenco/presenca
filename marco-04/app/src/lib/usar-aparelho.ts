/**
 * O laço do aparelho do estudante — MARCO 4.
 *
 * Enquanto a tela da turma está aberta, o celular escuta as âncoras (o
 * notebook e o ESP32) por Bluetooth e mostra o sinal. Durante a aula:
 *   - a cada 5 s manda o HEARTBEAT (v3, com turma e aula) e o SENSOR
 *     (acelerômetro e bateria), os dois assinados;
 *   - retém o que não conseguiu mandar (sem rede) e manda depois;
 *   - escuta o estado e os avisos do servidor (só aceita assinados por ele).
 *
 * A batida vem de dois relógios: o setInterval da tela (app na frente) e o
 * serviço em segundo plano (tela apagada). Os dois chamam `bater`, que só
 * manda se já passaram 5 s desde a última vez.
 */
import { useEffect, useRef, useState } from 'react';
import { Emissor, type Anomalia } from './aparelho';
import { abrirDe, envelopar } from './assinatura';
import {
  CHAVE_PUBLICA_SERVIDOR, INTERVALO_HEARTBEAT_MS, INTERVALO_TELA_MS, SALAS, SALA_PADRAO, topicos,
  VALIDADE_ESTADO_MS,
} from './config';
import type { Eu } from './identidade';
import { mqtt } from './mqtt';
import { montarSensor } from './sensores';
import { aoBater } from './segundo-plano';
import { useAncora } from './usar-ancora';
import { useSensores } from './usar-sensores';

/** presenca.estado.v1 — o que o servidor decidiu. */
export interface EstadoServidor {
  estado: 'PRESENTE' | 'AUSENCIA_TOLERADA' | 'FORA';
  acumuladoS: number;
  provisorioS: number;
  percentual: number;
  orcamentoRestanteS: number;
  tempoAulaS: number;
  classe: 'dentro' | 'fora' | 'neutro';
  dentroPoligono: boolean | null;
  encerrada: boolean;
  emitidoEmMs: number;
}

export interface AvisoServidor {
  avisoId: string; tipo: string; texto: string; percentual?: number;
}

// Estado retido de uma aula antiga chega assim que se assina o tópico: só
// vale o que foi emitido há pouco.
const IDADE_MAXIMA_ESTADO_MS = 30_000;
// Folga para o relógio da tela e o do segundo plano não mandarem dois seguidos.
const FOLGA_MS = 400;

export function useAparelho({ eu, sala, turma, aulaId, ativo, limiares, aoAviso, aoEncerrar }: {
  eu: Eu | null;
  sala: string;
  turma: string;
  aulaId: string | null;
  ativo: boolean;
  limiares: Record<string, number | null>;
  aoAviso: (a: AvisoServidor) => void;
  aoEncerrar: (e: EstadoServidor) => void;
}) {
  const ancoras = SALAS[sala]?.ancoras ?? SALAS[SALA_PADRAO].ancoras;
  const ancora = useAncora(limiares, ancoras);
  const sensores = useSensores(ativo);
  const medidor = ancora.medidor;
  const emissor = useRef<Emissor | null>(null);
  const encerrou = useRef(false);
  const avisoRef = useRef(aoAviso);
  const encerrarRef = useRef(aoEncerrar);
  avisoRef.current = aoAviso;
  encerrarRef.current = aoEncerrar;

  const [envio, setEnvio] = useState({ sequencia: 0, fila: 0, descartados: 0, sensores: 0 });
  const [ultimoSensor, setUltimoSensor] = useState<ReturnType<typeof montarSensor> | null>(null);
  const [redeCaida, setRedeCaida] = useState(false);
  const [proximaAnomalia, setProximaAnomalia] = useState<Anomalia>('duplicata');
  const [estado, setEstado] = useState<{ e: EstadoServidor; recebidoEm: number } | null>(null);
  const [agora, setAgora] = useState(Date.now());
  const [recusadas, setRecusadas] = useState({ total: 0, motivo: '' });
  const recusar = (motivo: string) => setRecusadas((r) => ({ total: r.total + 1, motivo }));

  // Respostas do servidor
  useEffect(() => {
    if (!eu) return;
    const pararEstado = mqtt.assinar(topicos.estado(sala, eu.aluno), (topico, texto) => {
      const a = abrirDe(topico, texto, CHAVE_PUBLICA_SERVIDOR);
      if (!a.ok) return recusar(`estado: ${a.motivo}`);
      try {
        const e = a.carga as EstadoServidor;
        if (Date.now() - e.emitidoEmMs > IDADE_MAXIMA_ESTADO_MS) return;
        setEstado({ e, recebidoEm: Date.now() });
        if (e.encerrada && !encerrou.current && emissor.current) {
          encerrou.current = true;
          encerrarRef.current(e);
        }
      } catch { /* mensagem ilegível: ignora */ }
    });
    const pararAviso = mqtt.assinar(topicos.aviso(sala, eu.aluno), (topico, texto) => {
      const a = abrirDe(topico, texto, CHAVE_PUBLICA_SERVIDOR);
      if (!a.ok) return recusar(`aviso: ${a.motivo}`);
      avisoRef.current(a.carga as AvisoServidor);
    });
    return () => { pararEstado(); pararAviso(); };
  }, [eu, sala]);

  // Heartbeat e sensor, só durante a aula
  useEffect(() => {
    let e: Emissor | null = null;
    let ultimaBatida = 0;
    let nSensor = 0;
    if (eu && ativo && aulaId) {
      e = new Emissor(
        { deviceId: eu.deviceId, aluno: eu.aluno, sala, ancoras, turma, aulaId },
        (json) => mqtt.publicar(topicos.heartbeat(sala),
          envelopar(eu.privada, eu.aluno, topicos.heartbeat(sala), json)),
        Date.now(),
      );
      e.redeSimuladaCaida = redeCaida;
      emissor.current = e;
      encerrou.current = false;
    }

    const bater = (forcar = false) => {
      const t = Date.now();
      medidor.current.atualizar(t);
      if (!e || !eu) return;
      if (!forcar && t - ultimaBatida < INTERVALO_HEARTBEAT_MS - FOLGA_MS) return;
      ultimaBatida = t;
      const conectado = mqtt.conectado && !e.redeSimuladaCaida;
      e.drenar(mqtt.conectado);
      e.heartbeat(medidor.current, t, mqtt.conectado);
      // Sensor: o dado do celular vai para o broker junto com cada heartbeat.
      const s = montarSensor({ aluno: eu.aluno, deviceId: eu.deviceId, turma }, e.bootId, ++nSensor, t,
                             sensores.movimento.current.fechar(), sensores.bateria.current);
      if (conectado) {
        mqtt.publicar(topicos.sensor(sala), envelopar(eu.privada, eu.aluno, topicos.sensor(sala), s));
      }
      setUltimoSensor(s);
      setEnvio({ sequencia: e.sequencia, fila: e.fila.length, descartados: e.descartadosFila, sensores: nSensor });
    };

    if (e) aoBater(() => bater());            // relógio do segundo plano
    const tela = setInterval(() => { bater(); setAgora(Date.now()); }, INTERVALO_TELA_MS);
    return () => {
      clearInterval(tela);
      aoBater(null);
      emissor.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eu, sala, turma, aulaId, ativo]);

  return {
    estadoBle: ancora.estadoBle,
    leitura: ancora.leitura,
    sensores: { disponivel: sensores.disponivel, ultimo: sensores.ultimo, enviado: ultimoSensor },
    envio,
    redeCaida,
    proximaAnomalia,
    estado: estado?.e ?? null,
    estadoValido: !!estado && agora - estado.recebidoEm < VALIDADE_ESTADO_MS,
    agora,
    recusadas,
    armarAnomalia(): Anomalia | null {
      const e = emissor.current;
      if (!e) return null;
      const a = e.armarAnomalia();
      setProximaAnomalia(e.proximaAnomalia);
      return a;
    },
    alternarRede() {
      const v = !redeCaida;
      setRedeCaida(v);
      if (emissor.current) emissor.current.redeSimuladaCaida = v;
    },
  };
}
