/**
 * Escuta a âncora (o notebook) por Bluetooth enquanto a tela está aberta e
 * mantém o MedidorBle atualizado. Usado na tela do estudante (só mede) e na
 * do administrador (mede e calibra).
 */
import { useEffect, useRef, useState } from 'react';
import { limiarCalibrado, MedidorBle, type Regiao } from './aparelho';
import { escutarAncora, type EstadoBle } from './ble';
import { CALIBRACAO_MS, INTERVALO_HEARTBEAT_MS } from './config';

export interface Leitura {
  rssi: number | null;
  regiao: Regiao;
  distancia: number | null;
  token: string | null;
  porSegundo: number;
  /** Todos os anúncios Bluetooth vistos, de qualquer aparelho: diagnóstico. */
  qualquerPorSegundo: number;
}

export function useAncora(limiar: number | null) {
  const medidor = useRef(new MedidorBle(limiar));
  const coleta = useRef<number[] | null>(null);      // calibração em andamento
  const contagem = useRef(0);
  const contagemQualquer = useRef(0);
  const ultimoToken = useRef<string | null>(null);
  medidor.current.limiar = limiar;

  const [estadoBle, setEstadoBle] = useState<EstadoBle>('iniciando');
  const [leitura, setLeitura] = useState<Leitura>(
    { rssi: null, regiao: 'INDETERMINADA', distancia: null, token: null, porSegundo: 0, qualquerPorSegundo: 0 });
  const [calibrando, setCalibrando] = useState(false);

  useEffect(() => escutarAncora((a) => {
    medidor.current.anuncio(a.rssi, Date.now(), a.token);
    coleta.current?.push(a.rssi);
    contagem.current++;
    ultimoToken.current = a.token;
  }, setEstadoBle, () => { contagemQualquer.current++; }), []);

  useEffect(() => {
    let ultima = Date.now();
    const t = setInterval(() => {
      const agora = Date.now();
      const m = medidor.current;
      m.atualizar(agora);
      const dt = Math.max(0.001, (agora - ultima) / 1000);
      setLeitura({
        rssi: m.rssi[0], regiao: m.regiao, distancia: m.distancia(), token: ultimoToken.current,
        porSegundo: contagem.current / dt, qualquerPorSegundo: contagemQualquer.current / dt,
      });
      contagem.current = 0;
      contagemQualquer.current = 0;
      ultima = agora;
    }, INTERVALO_HEARTBEAT_MS);
    return () => clearInterval(t);
  }, []);

  return {
    medidor,
    estadoBle,
    leitura,
    calibrando,
    /** Junta os anúncios por CALIBRACAO_MS, parado a 1 m; devolve o limiar ou null. */
    async calibrar(): Promise<number | null> {
      coleta.current = [];
      setCalibrando(true);
      await new Promise((r) => setTimeout(r, CALIBRACAO_MS));
      const novo = limiarCalibrado(coleta.current ?? []);
      coleta.current = null;
      setCalibrando(false);
      return novo;
    },
  };
}
