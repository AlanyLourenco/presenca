/**
 * O laço do aparelho do estudante — PROTÓTIPO 1.
 *
 * Enquanto a tela da turma está aberta, o celular escuta a âncora (o notebook)
 * por Bluetooth e mostra o sinal. Durante a aula, manda heartbeat a cada
 * 500 ms com a mediana do RSSI e a região decidida contra o limiar calibrado
 * a 1 m; retém quando a rede cai e escuta o estado e os avisos do servidor.
 *
 * O limiar vem da turma, calibrado pelo administrador. O estudante não
 * calibra: se pudesse, bastaria calibrar de longe para ficar sempre "perto".
 */
import { useEffect, useRef, useState } from 'react';
import { Emissor, type Anomalia } from './aparelho';
import { abrirDe, envelopar } from './assinatura';
import {
  CHAVE_PUBLICA_SERVIDOR, INTERVALO_HEARTBEAT_MS, SALAS, SALA_PADRAO, topicos, VALIDADE_ESTADO_MS,
} from './config';
import type { Eu } from './identidade';
import { mqtt } from './mqtt';
import { useAncora } from './usar-ancora';

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

export function useAparelho({ eu, sala, ativo, limiar, aoAviso, aoEncerrar }: {
  eu: Eu | null;
  sala: string;
  ativo: boolean;
  limiar: number | null;
  aoAviso: (a: AvisoServidor) => void;
  aoEncerrar: (e: EstadoServidor) => void;
}) {
  const ancora = useAncora(limiar);
  const medidor = ancora.medidor;
  const emissor = useRef<Emissor | null>(null);
  const encerrou = useRef(false);
  const avisoRef = useRef(aoAviso);
  const encerrarRef = useRef(aoEncerrar);
  avisoRef.current = aoAviso;
  encerrarRef.current = aoEncerrar;

  const [envio, setEnvio] = useState({ sequencia: 0, fila: 0, descartados: 0 });
  const [redeCaida, setRedeCaida] = useState(false);
  const [proximaAnomalia, setProximaAnomalia] = useState<Anomalia>('duplicata');
  const [estado, setEstado] = useState<{ e: EstadoServidor; recebidoEm: number } | null>(null);
  const [agora, setAgora] = useState(Date.now());
  // Marco 3: mensagens que chegaram no tópico do aluno sem a assinatura do servidor.
  const [recusadas, setRecusadas] = useState({ total: 0, motivo: '' });
  const recusar = (motivo: string) => setRecusadas((r) => ({ total: r.total + 1, motivo }));

  // Respostas do servidor
  useEffect(() => {
    if (!eu) return;
    // Só vale o que o SERVIDOR assinou (chave fixada no app por configurar.py).
    // Quem tem a senha do broker consegue publicar aqui, mas não consegue
    // forjar "PRESENTE, 100 %" em nome do servidor.
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

  // Heartbeat, só durante a aula
  useEffect(() => {
    let e: Emissor | null = null;
    if (eu && ativo) {
      const ancoras = SALAS[sala]?.ancoras ?? SALAS[SALA_PADRAO].ancoras;
      e = new Emissor(
        { deviceId: eu.deviceId, aluno: eu.aluno, sala, ancoras },
        // Todo heartbeat sai assinado pela chave do aparelho (envelope).
        (json) => mqtt.publicar(topicos.heartbeat(sala),
          envelopar(eu.privada, eu.aluno, topicos.heartbeat(sala), json)),
        Date.now(),
      );
      e.redeSimuladaCaida = redeCaida;
      emissor.current = e;
      encerrou.current = false;
    }
    const batida = setInterval(() => {
      const m = medidor.current;
      const t = Date.now();
      m.atualizar(t);
      if (e) {
        e.drenar(mqtt.conectado);
        e.heartbeat(m, t, mqtt.conectado);
        setEnvio({ sequencia: e.sequencia, fila: e.fila.length, descartados: e.descartadosFila });
      }
      setAgora(t);
    }, INTERVALO_HEARTBEAT_MS);
    return () => {
      clearInterval(batida);
      emissor.current = null;
    };
  }, [eu, sala, ativo]);

  return {
    estadoBle: ancora.estadoBle,
    leitura: ancora.leitura,
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
