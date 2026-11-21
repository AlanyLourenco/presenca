/**
 * Modo SEGUNDO PLANO — Marco 4 ("o app precisa funcionar com a tela apagada").
 *
 * No Android, quando a tela apaga, os relógios do JavaScript (setInterval)
 * param. O que mantém o app vivo é um SERVIÇO EM PRIMEIRO PLANO: uma
 * notificação fixa "Aula em andamento" que o sistema não pode matar.
 *
 * Usamos o serviço do expo-location porque é o módulo oficial do Expo. A
 * LOCALIZAÇÃO É DESCARTADA: o callback só serve de relógio (um a cada ~5 s)
 * para medir e mandar o heartbeat. Nenhuma coordenada é lida, guardada ou
 * enviada — GPS continua fora do projeto (CLAUDE.md, "não propor de novo").
 *
 * O Bluetooth com a tela apagada é tratado em ble.ts (varredura com filtro).
 */
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import { INTERVALO_HEARTBEAT_MS } from './config';

const TAREFA = 'presenca-batida-em-segundo-plano';
let batida: (() => void) | null = null;

// Precisa ser definida no carregamento do módulo (importado em _layout.tsx).
TaskManager.defineTask(TAREFA, async () => {
  try { batida?.(); } catch { /* a próxima batida tenta de novo */ }
});

/** A aula registra aqui o que fazer a cada batida (medir e mandar). */
export function aoBater(f: (() => void) | null) {
  batida = f;
}

export type EstadoSegundoPlano = 'desligado' | 'ligado' | 'sem-permissao' | 'erro';

/**
 * Liga o serviço. Pede a localização "o tempo todo" (Android exige para o
 * serviço continuar com a tela apagada); o estudante escolhe na tela do sistema.
 */
export async function ligarSegundoPlano(): Promise<EstadoSegundoPlano> {
  try {
    const frente = await Location.requestForegroundPermissionsAsync();
    if (frente.status !== 'granted') return 'sem-permissao';
    const fundo = await Location.requestBackgroundPermissionsAsync();
    if (fundo.status !== 'granted') return 'sem-permissao';
    if (await Location.hasStartedLocationUpdatesAsync(TAREFA)) return 'ligado';
    await Location.startLocationUpdatesAsync(TAREFA, {
      accuracy: Location.Accuracy.Lowest,       // não queremos a posição: só o relógio
      timeInterval: INTERVALO_HEARTBEAT_MS,
      distanceInterval: 0,
      pausesUpdatesAutomatically: false,
      foregroundService: {
        notificationTitle: 'Presença: aula em andamento',
        notificationBody: 'Medindo a sua permanência na sala pelo Bluetooth. A localização não é usada.',
        killServiceOnDestroy: true,
      },
    });
    return 'ligado';
  } catch {
    return 'erro';
  }
}

export async function desligarSegundoPlano() {
  try {
    if (await Location.hasStartedLocationUpdatesAsync(TAREFA)) await Location.stopLocationUpdatesAsync(TAREFA);
  } catch { /* já estava desligado */ }
}
