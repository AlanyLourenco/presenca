/**
 * Escuta a âncora por Bluetooth Low Energy.
 *
 * O celular só ESCUTA: varre os anúncios, separa os que têm o código de
 * empresa 0xFFFF e o prefixo "PRS1" (formato de prototipo-1/ancora/ancora.py)
 * e entrega o RSSI de cada um. Não conecta em nada e não transmite nada.
 *
 * Precisa de build nativo (APK): o Expo Go não traz módulo de Bluetooth.
 */
import { PermissionsAndroid, Platform } from 'react-native';
import BleManager, { BleScanCallbackType, BleScanMatchMode, BleScanMode } from 'react-native-ble-manager';
import { BLE_EMPRESA, BLE_PREFIXO } from './config';

export interface Anuncio {
  ancora: string;     // anc-pc-<n>
  token: string;      // muda a cada 10–15 s na âncora
  rssi: number;
}

export type EstadoBle = 'iniciando' | 'sem-permissao' | 'desligado' | 'escutando' | 'erro';

const CHAVE_EMPRESA = BLE_EMPRESA.toString(16).padStart(4, '0');   // "ffff"

async function pedirPermissoes() {
  if (Platform.OS !== 'android') return true;
  // Localização também no Android 12+: sem a marca neverForLocation (ver
  // plugins/ble-sem-never-for-location.js) o sistema exige as duas.
  const pedidas = Number(Platform.Version) >= 31
    ? [PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN, PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
       PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION]
    : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
  const r = await PermissionsAndroid.requestMultiple(pedidas);
  return pedidas.every((p) => r[p] === PermissionsAndroid.RESULTS.GRANTED);
}

function lerAnuncio(bytes: number[] | undefined, rssi: number): Anuncio | null {
  if (!bytes || bytes.length < BLE_PREFIXO.length + 5) return null;
  if (!BLE_PREFIXO.every((b, i) => bytes[i] === b)) return null;
  const n = bytes[BLE_PREFIXO.length];
  const token = bytes.slice(BLE_PREFIXO.length + 1, BLE_PREFIXO.length + 5)
    .map((b) => b.toString(16).padStart(2, '0')).join('');
  return { ancora: `anc-pc-${n}`, token, rssi };
}

/**
 * Começa a escutar. Devolve a função que para. `aoEstado` informa se falta
 * permissão, se o Bluetooth está desligado ou se está escutando.
 */
export function escutarAncora(aoAnuncio: (a: Anuncio) => void, aoEstado: (e: EstadoBle) => void,
                              aoQualquer: () => void = () => {}) {
  let parado = false;
  const inscricoes: { remove(): void }[] = [];

  async function varrer() {
    if (parado) return;
    try {
      await BleManager.scan({
        seconds: 0,                                   // até mandar parar
        allowDuplicates: true,                        // cada anúncio é uma amostra
        scanMode: BleScanMode.LowLatency,
        matchMode: BleScanMatchMode.Aggressive,
        callbackType: BleScanCallbackType.AllMatches,
        // Sem filtro de fabricante: em alguns celulares o filtro feito no chip
        // descarta anúncios que deveriam passar. A âncora é separada aqui no
        // JavaScript, pelo prefixo PRS1.
      });
      aoEstado('escutando');
    } catch {
      aoEstado('erro');
    }
  }

  (async () => {
    aoEstado('iniciando');
    if (!(await pedirPermissoes())) return aoEstado('sem-permissao');
    await BleManager.start({ showAlert: false });
    inscricoes.push(BleManager.onDiscoverPeripheral((p) => {
      aoQualquer();
      const dado = p.advertising?.manufacturerData?.[CHAVE_EMPRESA];
      const a = lerAnuncio(dado?.bytes, p.rssi);
      if (a) aoAnuncio(a);
    }));
    // O Android encerra varreduras longas; recomeça sozinho.
    inscricoes.push(BleManager.onStopScan(() => { if (!parado) setTimeout(varrer, 1000); }));
    inscricoes.push(BleManager.onDidUpdateState(({ state }) => {
      if (state === 'on') varrer();
      else aoEstado('desligado');
    }));
    const estado = await BleManager.checkState();
    if (estado === 'on') await varrer();
    else {
      aoEstado('desligado');
      if (Platform.OS === 'android') BleManager.enableBluetooth().catch(() => {});
    }
  })().catch(() => aoEstado('erro'));

  return () => {
    parado = true;
    inscricoes.forEach((i) => i.remove());
    BleManager.stopScan().catch(() => {});
  };
}
