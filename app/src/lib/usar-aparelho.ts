/**
 * O laço do aparelho do estudante dentro da tela de aula: amostra o sinal a
 * cada 100 ms, manda heartbeat a cada 500 ms enquanto houver aula, retém
 * quando a rede cai e escuta o estado e os avisos que o servidor devolve.
 * Faz no celular o que o loop() do ESP32 fazia.
 */
import { useEffect, useRef, useState } from 'react';
import { Emissor, Medidor, type Anomalia, type Regiao } from './aparelho';
import {
  INTERVALO_AMOSTRA_MS, INTERVALO_HEARTBEAT_MS, POSICOES, SALAS, topicos, VALIDADE_ESTADO_MS,
} from './config';
import type { Eu } from './identidade';
import { mqtt } from './mqtt';

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

export function useAparelho({ eu, sala, ativo, aoAviso, aoEncerrar }: {
  eu: Eu | null;
  sala: string;
  ativo: boolean;
  aoAviso: (a: AvisoServidor) => void;
  aoEncerrar: (e: EstadoServidor) => void;
}) {
  const medidor = useRef(new Medidor());
  const emissor = useRef<Emissor | null>(null);
  const alvo = useRef<number[]>([...POSICOES[0].rssi]);
  const encerrou = useRef(false);
  const avisoRef = useRef(aoAviso);
  const encerrarRef = useRef(aoEncerrar);
  avisoRef.current = aoAviso;
  encerrarRef.current = aoEncerrar;

  const [rssiAlvo, setRssiAlvo] = useState<number[]>(alvo.current);
  const [leitura, setLeitura] = useState<{ rssi: (number | null)[]; regiao: Regiao }>(
    { rssi: [null, null, null], regiao: 'INDETERMINADA' });
  const [envio, setEnvio] = useState({ sequencia: 0, fila: 0, descartados: 0 });
  const [redeCaida, setRedeCaida] = useState(false);
  const [proximaAnomalia, setProximaAnomalia] = useState<Anomalia>('duplicata');
  const [estado, setEstado] = useState<{ e: EstadoServidor; recebidoEm: number } | null>(null);
  const [agora, setAgora] = useState(Date.now());

  // Respostas do servidor
  useEffect(() => {
    if (!eu) return;
    const pararEstado = mqtt.assinar(topicos.estado(sala, eu.aluno), (_t, texto) => {
      try {
        const e = JSON.parse(texto) as EstadoServidor;
        if (Date.now() - e.emitidoEmMs > IDADE_MAXIMA_ESTADO_MS) return;
        setEstado({ e, recebidoEm: Date.now() });
        if (e.encerrada && !encerrou.current && emissor.current) {
          encerrou.current = true;
          encerrarRef.current(e);
        }
      } catch { /* mensagem ilegível: ignora */ }
    });
    const pararAviso = mqtt.assinar(topicos.aviso(sala, eu.aluno), (_t, texto) => {
      try { avisoRef.current(JSON.parse(texto) as AvisoServidor); } catch { /* ignora */ }
    });
    return () => { pararEstado(); pararAviso(); };
  }, [eu, sala]);

  // Laço de medição e envio, só durante a aula
  useEffect(() => {
    if (!eu || !ativo) return;
    const ancoras = SALAS[sala]?.ancoras ?? SALAS['sala-204'].ancoras;
    const e = new Emissor(
      { deviceId: eu.deviceId, aluno: eu.aluno, sala, ancoras },
      (json) => mqtt.publicar(topicos.heartbeat(sala), json),
      Date.now(),
    );
    e.redeSimuladaCaida = redeCaida;
    emissor.current = e;
    encerrou.current = false;

    const amostra = setInterval(() => medidor.current.amostrar(alvo.current), INTERVALO_AMOSTRA_MS);
    const batida = setInterval(() => {
      const m = medidor.current;
      e.drenar(mqtt.conectado);
      e.heartbeat(m, Date.now(), mqtt.conectado);
      setLeitura({ rssi: [...m.rssi], regiao: m.regiao });
      setEnvio({ sequencia: e.sequencia, fila: e.fila.length, descartados: e.descartadosFila });
      setAgora(Date.now());
    }, INTERVALO_HEARTBEAT_MS);
    return () => {
      clearInterval(amostra);
      clearInterval(batida);
      emissor.current = null;
    };
  }, [eu, sala, ativo]);

  // Relógio da tela fora da aula (para a validade do estado e a contagem)
  useEffect(() => {
    if (ativo) return;
    const t = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(t);
  }, [ativo]);

  return {
    rssiAlvo,
    leitura,
    envio,
    redeCaida,
    proximaAnomalia,
    estado: estado?.e ?? null,
    estadoValido: !!estado && agora - estado.recebidoEm < VALIDADE_ESTADO_MS,
    agora,
    definirSinal(rssi: number[]) {
      alvo.current = rssi;
      setRssiAlvo(rssi);
    },
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
