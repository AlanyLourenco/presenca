/**
 * Identidade do aparelho e do estudante.
 *
 * O projeto pede um par de chaves gerado no cofre de hardware do aparelho
 * (decisão 5). O Expo Go não expõe a geração de chaves no Keystore/Secure
 * Enclave, então aqui a aproximação é: 32 bytes aleatórios criptograficamente
 * seguros guardados no armazenamento seguro do sistema (expo-secure-store, que
 * é cifrado pelo Keystore no Android e fica no Keychain no iOS). O pseudônimo
 * enviado ao servidor é derivado do hash dessa chave — nunca MAC, IMEI ou nome.
 * Assinar o heartbeat com a chave fica para o build nativo.
 */
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const CHAVE = 'presenca.chave';
const PIN_ADMIN = 'presenca.pin-admin';

export interface Eu {
  aluno: string;       // tok-xxxxxxxx — o que o servidor vê
  deviceId: string;    // cel-xxxx
}

const hex = (bytes: Uint8Array) => [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');

let cache: Eu | null = null;

export async function minhaIdentidade(): Promise<Eu> {
  if (cache) return cache;
  let chave = await SecureStore.getItemAsync(CHAVE);
  if (!chave) {
    chave = hex(Crypto.getRandomBytes(32));
    await SecureStore.setItemAsync(CHAVE, chave);
  }
  const h = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, chave);
  cache = { aluno: `tok-${h.slice(0, 8)}`, deviceId: `cel-${h.slice(8, 12)}` };
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
