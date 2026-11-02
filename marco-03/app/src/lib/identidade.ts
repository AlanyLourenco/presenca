/**
 * Identidade do aparelho e do estudante — Marco 3.
 *
 * O projeto pede um par de chaves gerado no cofre do aparelho (decisão 5).
 * Aqui: 32 bytes aleatórios criptograficamente seguros são a semente de uma
 * chave Ed25519, guardada no armazenamento seguro do sistema
 * (expo-secure-store, cifrado pelo Keystore no Android). A chave privada nunca
 * sai do aparelho; o pseudônimo é o hash da chave PÚBLICA (assinatura.ts), e
 * todo heartbeat sai assinado com ela. Nunca MAC, IMEI ou nome.
 *
 * Limite declarado: a semente fica no armazenamento seguro, não DENTRO do chip
 * (o Keystore não oferece Ed25519 pelo Expo). Um celular com root a extrai.
 */
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { identidadeDaChave, publicaDe } from './assinatura';

const CHAVE = 'presenca.chave-ed25519';
const PIN_ADMIN = 'presenca.pin-admin';

export interface Eu {
  aluno: string;        // tok-xxxxxxxx — o que o servidor vê
  deviceId: string;     // cel-xxxx
  chavePublica: string; // hex, vai em todo envelope
  privada: string;      // hex, só para assinar; nunca é enviada
}

const hex = (bytes: Uint8Array) => [...bytes].map((x) => x.toString(16).padStart(2, '0')).join('');

let cache: Eu | null = null;

export async function minhaIdentidade(): Promise<Eu> {
  if (cache) return cache;
  let privada = await SecureStore.getItemAsync(CHAVE);
  if (!privada) {
    privada = hex(Crypto.getRandomBytes(32));
    await SecureStore.setItemAsync(CHAVE, privada);
  }
  const chavePublica = publicaDe(privada);
  cache = { ...identidadeDaChave(chavePublica), chavePublica, privada };
  return cache;
}

// ---- PIN do admin: guardado só como hash -----------------------------------
const hashPin = (pin: string) =>
  Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, 'presenca-admin:' + pin);

export async function temPinAdmin() {
  return (await SecureStore.getItemAsync(PIN_ADMIN)) !== null;
}

export async function definirPinAdmin(pin: string) {
  await SecureStore.setItemAsync(PIN_ADMIN, await hashPin(pin));
}

export async function conferirPinAdmin(pin: string) {
  return (await SecureStore.getItemAsync(PIN_ADMIN)) === (await hashPin(pin));
}
