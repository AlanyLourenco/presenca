/**
 * Como a configuração da turma chega do celular do admin ao do estudante.
 *
 * O admin publica a turma como mensagem RETIDA no tópico .../turma/<código>.
 * O broker guarda a última versão e a entrega a quem assinar depois — é isso
 * que faz o código funcionar: o estudante assina o tópico do código digitado
 * e recebe a grade na hora, mesmo que o admin esteja offline.
 */
import { ESPERA_TURMA_MS, topicos } from './config';
import { mqtt } from './mqtt';
import { lerTurma, type Turma } from './turma';

export function publicarTurma(t: Omit<Turma, 'eventType' | 'publicadoEmMs'>) {
  const msg: Turma = { eventType: 'presenca.turma.v1', ...t, publicadoEmMs: Date.now() };
  const ok = mqtt.publicar(topicos.turma(t.codigo), JSON.stringify(msg), { retido: true, qos: 1 });
  return ok ? msg.publicadoEmMs : null;
}

/** Espera a configuração publicada do código; null se nada chegar a tempo. */
export function buscarTurma(codigo: string, esperaMs = ESPERA_TURMA_MS): Promise<Turma | null> {
  return new Promise((resolve) => {
    const fim = setTimeout(() => { parar(); resolve(null); }, esperaMs);
    const parar = mqtt.assinar(topicos.turma(codigo), (_t, texto) => {
      const t = lerTurma(texto);
      if (t && t.codigo === codigo) {
        clearTimeout(fim);
        parar();
        resolve(t);
      }
    });
  });
}

/** Acompanha as mudanças que o admin publicar enquanto a tela estiver aberta. */
export function acompanharTurma(codigo: string, aoMudar: (t: Turma) => void) {
  return mqtt.assinar(topicos.turma(codigo), (_t, texto) => {
    const t = lerTurma(texto);
    if (t && t.codigo === codigo) aoMudar(t);
  });
}
