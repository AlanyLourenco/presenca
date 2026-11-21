/**
 * ATUADOR no celular do estudante — Marco 4.
 *
 * Escuta .../comando/<aluno>, confere (comandos.ts) e EXECUTA:
 *   vibrar    vibra e mostra/notifica o texto
 *   chamar    vibra forte, notifica e mostra o botão "Estou aqui"
 *   lanterna  pisca o flash da câmera (o estudante mostra que está na sala)
 * e confirma, assinado, em .../comando-ack/<aluno>.
 */
import { Camera } from 'expo-camera';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Vibration } from 'react-native';
import { envelopar } from './assinatura';
import { conferirComando, montarConfirmacao, type Comando, type Resultado } from './comandos';
import { CHAVE_PUBLICA_SERVIDOR, PISCADA_MS, PISCADAS_LANTERNA, topicos } from './config';
import type { Eu } from './identidade';
import { mqtt } from './mqtt';
import { notificar } from './notificacoes';
import { chaveAdminDa } from './rede-turma';

export interface ComandoNaTela {
  comando: Comando;
  de: 'servidor' | 'professor';
  respondido: boolean;
  recebidoEm: number;
}

export function useComandos({ eu, sala, turma }: { eu: Eu | null; sala: string; turma: string }) {
  const vistos = useRef(new Set<string>());
  const [naTela, setNaTela] = useState<ComandoNaTela | null>(null);
  const [lanterna, setLanterna] = useState(false);
  const [recusados, setRecusados] = useState({ total: 0, motivo: '' });
  const [executados, setExecutados] = useState(0);

  const confirmar = useCallback((comandoId: string, resultado: Resultado, detalhe?: string) => {
    if (!eu) return;
    const topico = topicos.comandoAck(sala, eu.aluno);
    mqtt.publicar(topico, envelopar(eu.privada, eu.aluno, topico,
      montarConfirmacao(comandoId, eu.aluno, resultado, Date.now(), detalhe)), { qos: 1 });
  }, [eu, sala]);

  const piscar = useCallback(async (c: Comando) => {
    const perm = await Camera.getCameraPermissionsAsync().catch(() => null);
    const ok = perm?.granted || (await Camera.requestCameraPermissionsAsync().catch(() => null))?.granted;
    if (!ok) return confirmar(c.comandoId, 'recusado', 'sem permissão da câmera para a lanterna');
    for (let i = 0; i < PISCADAS_LANTERNA * 2; i++) {
      setLanterna(i % 2 === 0);
      await new Promise((r) => setTimeout(r, PISCADA_MS));
    }
    setLanterna(false);
    confirmar(c.comandoId, 'executado', `lanterna piscou ${PISCADAS_LANTERNA} vezes`);
  }, [confirmar]);

  useEffect(() => {
    if (!eu || !turma) return;
    let chaveAdmin: string | null = null;
    chaveAdminDa(turma).then((k) => { chaveAdmin = k; });
    return mqtt.assinar(topicos.comando(sala, eu.aluno), (topico, texto) => {
      if (!texto) return;
      const r = conferirComando(topico, texto, {
        aluno: eu.aluno, turma, chaveServidor: CHAVE_PUBLICA_SERVIDOR, chaveAdmin,
      }, Date.now(), vistos.current);
      if (!r.ok) {
        if (r.motivo === 'comando repetido') return;          // QoS 1 pode entregar 2 vezes
        setRecusados((x) => ({ total: x.total + 1, motivo: r.motivo }));
        if (r.comandoId && r.motivo === 'comando vencido') confirmar(r.comandoId, 'vencido');
        return;
      }
      const c = r.comando;
      vistos.current.add(c.comandoId);
      setExecutados((n) => n + 1);
      const titulo = r.de === 'professor' ? 'Mensagem do professor' : 'Presença';
      if (c.tipo === 'lanterna') {
        Vibration.vibrate(300);
        setNaTela({ comando: c, de: r.de, respondido: false, recebidoEm: Date.now() });
        piscar(c);
        return;
      }
      Vibration.vibrate(c.tipo === 'chamar' ? [0, 700, 250, 700, 250, 700] : [0, 400, 200, 400]);
      notificar(titulo, c.texto);
      setNaTela({ comando: c, de: r.de, respondido: false, recebidoEm: Date.now() });
      confirmar(c.comandoId, 'executado', c.tipo === 'chamar' ? 'vibrou e notificou; esperando o toque' : 'vibrou e notificou');
    });
  }, [eu, sala, turma, confirmar, piscar]);

  return {
    naTela,
    lanterna,
    recusados,
    executados,
    /** "Estou aqui": o estudante respondeu à chamada. */
    responder() {
      if (!naTela) return;
      confirmar(naTela.comando.comandoId, 'respondido', 'o estudante tocou em "Estou aqui"');
      setNaTela({ ...naTela, respondido: true });
    },
    fechar() { setNaTela(null); },
  };
}
