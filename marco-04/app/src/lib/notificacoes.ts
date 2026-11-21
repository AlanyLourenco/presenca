/**
 * Notificação local dos avisos, só onde ela existe.
 *
 * No Expo Go do Android (SDK 53 em diante) o simples import de
 * expo-notifications lança erro e derruba a tela que o importou. Por isso o
 * módulo é carregado sob demanda e, nesse caso, nunca é carregado: o aviso
 * fica com a vibração e o cartão na tela. No iPhone com Expo Go e no app
 * instalado, a notificação local funciona.
 */
import Constants, { ExecutionEnvironment } from 'expo-constants';
import { Platform } from 'react-native';

type Modulo = typeof import('expo-notifications');

const CANAL = 'avisos';
let modulo: Modulo | null | undefined;

function carregar(): Modulo | null {
  if (modulo !== undefined) return modulo;
  const expoGoAndroid = Platform.OS === 'android'
    && Constants.executionEnvironment === ExecutionEnvironment.StoreClient;
  if (expoGoAndroid) return (modulo = null);
  try {
    modulo = require('expo-notifications') as Modulo;
  } catch {
    modulo = null;
  }
  return modulo;
}

export const notificacoesDisponiveis = () => carregar() !== null;

/** Pede a permissão e prepara o canal. Pode ser chamada mais de uma vez. */
export async function prepararNotificacoes() {
  const N = carregar();
  if (!N) return;
  try {
    // Aviso que chega com o app aberto também aparece como notificação.
    N.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true, shouldShowList: true, shouldPlaySound: true, shouldSetBadge: false,
      }),
    });
    if (Platform.OS === 'android') {
      await N.setNotificationChannelAsync(CANAL, {
        name: 'Avisos de presença',
        importance: N.AndroidImportance.HIGH,
        vibrationPattern: [0, 400, 200, 400],
      });
    }
    await N.requestPermissionsAsync();
  } catch { /* sem notificação: o aviso continua na tela */ }
}

export async function notificar(titulo: string, texto: string) {
  const N = carregar();
  if (!N) return;
  try {
    await N.scheduleNotificationAsync({
      content: { title: titulo, body: texto },
      trigger: Platform.OS === 'android' ? { channelId: CANAL } : null,
    });
  } catch { /* idem */ }
}
