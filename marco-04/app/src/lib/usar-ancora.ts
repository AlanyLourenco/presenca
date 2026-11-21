/**
 * Escuta as âncoras (o notebook e, no Marco 4, o ESP32) por Bluetooth enquanto
 * a tela está aberta e mantém o MedidorBle atualizado. Usado na tela do
 * estudante (só mede) e na do administrador (mede e calibra cada âncora).
 */
import { useEffect, useRef, useState } from 'react';
import { limiarCalibrado, MedidorBle, type Regiao } from './aparelho';
import { escutarAncora, type EstadoBle } from './ble';
import { CALIBRACAO_MS, INTERVALO_TELA_MS } from './config';

export interface LeituraAncora {
  id: string;
  rssi: number | null;
  distancia: number | null;
  token: string | null;
  porSegundo: number;
}

export interface Leitura {
  /** A âncora mais forte (compatível com a tela do Marco 3). */
  rssi: number | null;
  regiao: Regiao;
  distancia: number | null;
  token: string | null;
  porSegundo: number;
  /** Todos os anúncios Bluetooth vistos, de qualquer aparelho: diagnóstico. */
  qualquerPorSegundo: number;
  /** Marco 4: cada âncora. */
  ancoras: LeituraAncora[];
}

const vazia = (ancoras: readonly string[]): Leitura => ({
  rssi: null, regiao: 'INDETERMINADA', distancia: null, token: null, porSegundo: 0, qualquerPorSegundo: 0,
  ancoras: ancoras.map((id) => ({ id, rssi: null, distancia: null, token: null, porSegundo: 0 })),
});

export function useAncora(limiares: Record<string, number | null>, ancoras: readonly string[]) {
  const medidor = useRef(new MedidorBle(limiares, ancoras));
  const coleta = useRef<{ ancora: string; rssis: number[] } | null>(null);   // calibração em andamento
  const contagem = useRef(new Map<string, number>());
  const contagemQualquer = useRef(0);
  const ultimoToken = useRef(new Map<string, string>());
  medidor.current.definirLimiares(limiares);

  const [estadoBle, setEstadoBle] = useState<EstadoBle>('iniciando');
  const [leitura, setLeitura] = useState<Leitura>(vazia(ancoras));
  const [calibrando, setCalibrando] = useState<string | null>(null);

  useEffect(() => escutarAncora((a) => {
    medidor.current.anuncio(a.rssi, Date.now(), a.token, a.ancora);
    if (coleta.current?.ancora === a.ancora) coleta.current.rssis.push(a.rssi);
    contagem.current.set(a.ancora, (contagem.current.get(a.ancora) ?? 0) + 1);
    ultimoToken.current.set(a.ancora, a.token);
  }, setEstadoBle, () => { contagemQualquer.current++; }), []);

  useEffect(() => {
    let ultima = Date.now();
    const t = setInterval(() => {
      const agora = Date.now();
      const m = medidor.current;
      m.atualizar(agora);
      const dt = Math.max(0.001, (agora - ultima) / 1000);
      const dist = m.distancias();
      const cada = m.ancoras.map((id, i) => ({
        id, rssi: m.rssi[i], distancia: dist[i], token: ultimoToken.current.get(id) ?? null,
        porSegundo: (contagem.current.get(id) ?? 0) / dt,
      }));
      const ouvidas = cada.filter((x) => x.rssi !== null);
      const forte = ouvidas.sort((a, b) => b.rssi! - a.rssi!)[0];
      setLeitura({
        rssi: forte?.rssi ?? null, regiao: m.regiao, distancia: m.distancia(), token: forte?.token ?? null,
        porSegundo: cada.reduce((s, x) => s + x.porSegundo, 0),
        qualquerPorSegundo: contagemQualquer.current / dt,
        ancoras: m.ancoras.map((id, i) => cada.find((x) => x.id === id) ?? cada[i]),
      });
      contagem.current.clear();
      contagemQualquer.current = 0;
      ultima = agora;
    }, INTERVALO_TELA_MS);
    return () => clearInterval(t);
  }, []);

  return {
    medidor,
    estadoBle,
    leitura,
    calibrando,
    /** Junta os anúncios de UMA âncora por CALIBRACAO_MS, parado a 1 m dela. */
    async calibrar(ancora: string): Promise<number | null> {
      coleta.current = { ancora, rssis: [] };
      setCalibrando(ancora);
      await new Promise((r) => setTimeout(r, CALIBRACAO_MS));
      const novo = limiarCalibrado(coleta.current?.rssis ?? []);
      coleta.current = null;
      setCalibrando(null);
      return novo;
    },
  };
}
