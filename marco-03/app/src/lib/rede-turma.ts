/**
 * Como a configuração da turma chega do celular do admin ao do estudante.
 *
 * O admin publica a turma como mensagem RETIDA no tópico .../turma/<código>.
 * O broker guarda a última versão e a entrega a quem assinar depois — é isso
 * que faz o código funcionar: o estudante assina o tópico do código digitado
 * e recebe a grade na hora, mesmo que o admin esteja offline.
 *
 * Marco 3: a turma sai ASSINADA pela chave do celular do admin. No pareamento
 * (código ou QR, uma vez) o estudante guarda essa chave; depois disso só aceita
 * mudanças assinadas por ela. Sem isso, quem tivesse a senha do broker poderia
 * publicar uma turma falsa com o limiar de 1 m em −100 dBm, e todo mundo ficaria
 * "perto" de casa.
 */
import * as SecureStore from 'expo-secure-store';
import { abrirEnvelope, envelopar } from './assinatura';
import { ESPERA_TURMA_MS, topicos } from './config';
import { minhaIdentidade } from './identidade';
import { mqtt } from './mqtt';
import { lerTurma, type Turma } from './turma';

const chaveDoAdmin = (codigo: string) => `presenca.admin.${codigo}`;

export async function publicarTurma(t: Omit<Turma, 'eventType' | 'publicadoEmMs'>) {
  const eu = await minhaIdentidade();
  const msg: Turma = { eventType: 'presenca.turma.v1', ...t, publicadoEmMs: Date.now() };
  const topico = topicos.turma(t.codigo);
  const ok = mqtt.publicar(topico, envelopar(eu.privada, 'admin', topico, msg), { retido: true, qos: 1 });
  if (ok) await SecureStore.setItemAsync(chaveDoAdmin(t.codigo), eu.chavePublica);
  return ok ? msg.publicadoEmMs : null;
}

/** Abre o envelope; devolve a turma e a chave de quem assinou, ou null. */
function abrir(codigo: string, topico: string, texto: string) {
  const a = abrirEnvelope(topico, texto);
  if (!a.ok) return null;
  const t = lerTurma(JSON.stringify(a.carga));
  return t && t.codigo === codigo ? { turma: t, chave: a.chavePublica } : null;
}

/**
 * Pareamento: espera a configuração publicada do código e FIXA a chave do
 * admin que a assinou. null se nada válido chegar a tempo.
 */
export function buscarTurma(codigo: string, esperaMs = ESPERA_TURMA_MS): Promise<Turma | null> {
  return new Promise((resolve) => {
    const fim = setTimeout(() => { parar(); resolve(null); }, esperaMs);
    const parar = mqtt.assinar(topicos.turma(codigo), async (topico, texto) => {
      const r = abrir(codigo, topico, texto);
      if (!r) return;
      clearTimeout(fim);
      parar();
      await SecureStore.setItemAsync(chaveDoAdmin(codigo), r.chave);
      resolve(r.turma);
    });
  });
}

/**
 * Acompanha as mudanças que o admin publicar enquanto a tela estiver aberta.
 * Só aceita o que vier assinado pela chave fixada no pareamento.
 */
export function acompanharTurma(codigo: string, aoMudar: (t: Turma) => void, aoRecusar?: (motivo: string) => void) {
  return mqtt.assinar(topicos.turma(codigo), async (topico, texto) => {
    const r = abrir(codigo, topico, texto);
    if (!r) return aoRecusar?.('turma sem assinatura válida');
    const fixada = await SecureStore.getItemAsync(chaveDoAdmin(codigo));
    if (fixada && fixada !== r.chave) return aoRecusar?.('turma assinada por outro administrador');
    aoMudar(r.turma);
  });
}
