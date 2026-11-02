/**
 * Marco 3 — todo dispositivo diz quem é, e prova.
 *
 * Cada aparelho tem um par de chaves Ed25519. Toda mensagem vai num envelope
 * (seguranca.envelope.v1) com a chave pública e a assinatura de
 * "tópico \n carga". O mesmo formato é conferido pelo servidor
 * (marco-03/servidor/seguranca.py) e o servidor assina o estado e os avisos
 * do mesmo jeito, para o celular conferir o caminho de volta.
 *
 * Módulo puro (sem rede, sem armazenamento): testado com `npm test`.
 */
import * as ed from '@noble/ed25519';
import { sha256 } from '@noble/hashes/sha256';
import { sha512 } from '@noble/hashes/sha512';
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils';

// O ed25519 precisa de um SHA-512 síncrono; o React Native não tem crypto.subtle.
ed.etc.sha512Sync = (...m) => sha512(ed.etc.concatBytes(...m));

export const TIPO_ENVELOPE = 'seguranca.envelope.v1';

export interface Envelope {
  eventType: typeof TIPO_ENVELOPE;
  de: string;
  chavePublica: string;   // 32 bytes em hex
  carga: string;          // a mensagem original, em JSON, exatamente como foi assinada
  assinatura: string;     // 64 bytes em hex
}

export type Aberto =
  | { ok: true; de: string; chavePublica: string; carga: unknown }
  | { ok: false; motivo: string };

export const publicaDe = (privadaHex: string) => bytesToHex(ed.getPublicKey(hexToBytes(privadaHex)));

/**
 * O pseudônimo sai do hash da chave pública: quem não tem a chave privada não
 * consegue assinar como esse aluno. Mesmo cálculo de identidade_da_chave() no
 * servidor.
 */
export function identidadeDaChave(publicaHex: string) {
  const h = bytesToHex(sha256(hexToBytes(publicaHex)));
  return { aluno: `tok-${h.slice(0, 8)}`, deviceId: `cel-${h.slice(8, 12)}` };
}

const mensagem = (topico: string, carga: string) => utf8ToBytes(topico + '\n' + carga);

export function envelopar(privadaHex: string, de: string, topico: string, carga: string | object): string {
  const texto = typeof carga === 'string' ? carga : JSON.stringify(carga);
  const env: Envelope = {
    eventType: TIPO_ENVELOPE,
    de,
    chavePublica: publicaDe(privadaHex),
    carga: texto,
    assinatura: bytesToHex(ed.sign(mensagem(topico, texto), hexToBytes(privadaHex))),
  };
  return JSON.stringify(env);
}

/** Confere a assinatura. Quem a chave é (e se pode falar ali) decide quem chamou. */
export function abrirEnvelope(topico: string, texto: string): Aberto {
  let env: Partial<Envelope>;
  try { env = JSON.parse(texto); } catch { return { ok: false, motivo: 'não é JSON' }; }
  if (env?.eventType !== TIPO_ENVELOPE) return { ok: false, motivo: 'sem assinatura' };
  if (typeof env.carga !== 'string' || typeof env.chavePublica !== 'string'
      || typeof env.assinatura !== 'string' || typeof env.de !== 'string') {
    return { ok: false, motivo: 'envelope malformado' };
  }
  let valida = false;
  try {
    valida = ed.verify(hexToBytes(env.assinatura), mensagem(topico, env.carga), hexToBytes(env.chavePublica));
  } catch { valida = false; }
  if (!valida) return { ok: false, motivo: 'assinatura falsa' };
  try {
    return { ok: true, de: env.de, chavePublica: env.chavePublica, carga: JSON.parse(env.carga) };
  } catch {
    return { ok: false, motivo: 'carga não é JSON' };
  }
}

/** Só aceita se a chave for exatamente a esperada (a do servidor, fixada no app). */
export function abrirDe(topico: string, texto: string, chaveEsperada: string): Aberto {
  const a = abrirEnvelope(topico, texto);
  if (a.ok && a.chavePublica.toLowerCase() !== chaveEsperada.toLowerCase()) {
    return { ok: false, motivo: 'chave desconhecida' };
  }
  return a;
}
