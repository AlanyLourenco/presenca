/**
 * Lê o hardware do celular para sensores.ts: acelerômetro (expo-sensors) e
 * bateria (expo-battery). Só durante a aula.
 */
import * as Battery from 'expo-battery';
import { Accelerometer } from 'expo-sensors';
import { useEffect, useRef, useState } from 'react';
import { ACELEROMETRO_INTERVALO_MS } from './config';
import { ResumoMovimento, type Bateria } from './sensores';

export function useSensores(ativo: boolean) {
  const movimento = useRef(new ResumoMovimento());
  const bateria = useRef<Bateria | null>(null);
  const [disponivel, setDisponivel] = useState<boolean | null>(null);
  const [ultimo, setUltimo] = useState<{ x: number; y: number; z: number } | null>(null);

  useEffect(() => {
    if (!ativo) return;
    let assinatura: { remove(): void } | null = null;
    let mostrado = 0;
    Accelerometer.isAvailableAsync().then((ok) => {
      setDisponivel(ok);
      if (!ok) return;
      Accelerometer.setUpdateInterval(ACELEROMETRO_INTERVALO_MS);
      assinatura = Accelerometer.addListener(({ x, y, z }) => {
        movimento.current.leitura(x, y, z);
        const agora = Date.now();
        if (agora - mostrado > 500) { mostrado = agora; setUltimo({ x, y, z }); }   // a tela não precisa de 10/s
      });
    }).catch(() => setDisponivel(false));

    const lerBateria = async () => {
      try {
        const [nivel, estado] = await Promise.all([Battery.getBatteryLevelAsync(), Battery.getBatteryStateAsync()]);
        bateria.current = {
          nivel,
          carregando: estado === Battery.BatteryState.CHARGING || estado === Battery.BatteryState.FULL,
        };
      } catch { bateria.current = null; }
    };
    lerBateria();
    const nivelMudou = Battery.addBatteryLevelListener(lerBateria);
    const estadoMudou = Battery.addBatteryStateListener(lerBateria);
    return () => {
      assinatura?.remove();
      nivelMudou.remove();
      estadoMudou.remove();
    };
  }, [ativo]);

  return { movimento, bateria, disponivel, ultimo };
}
