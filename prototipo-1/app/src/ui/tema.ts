import { useColorScheme } from 'react-native';

const claro = {
  fundo: '#F4F2EE',
  cartao: '#FFFFFF',
  texto: '#1C1B19',
  suave: '#6B6862',
  borda: '#E2DED6',
  primaria: '#1F4E79',
  primariaTexto: '#FFFFFF',
  presente: '#1E7A46',
  tolerancia: '#B7791F',
  fora: '#B3261E',
  neutro: '#7A766E',
  campo: '#FAF9F6',
};

const escuro: typeof claro = {
  fundo: '#141413',
  cartao: '#1F1E1C',
  texto: '#F1EFEA',
  suave: '#A19D95',
  borda: '#34322E',
  primaria: '#7FB0DD',
  primariaTexto: '#0E1A26',
  presente: '#4CC17E',
  tolerancia: '#E3A94B',
  fora: '#F07A72',
  neutro: '#8F8B83',
  campo: '#262522',
};

export type Cores = typeof claro;

export function useCores(): Cores {
  return useColorScheme() === 'dark' ? escuro : claro;
}

export const espaco = { xs: 4, s: 8, m: 12, l: 16, xl: 24 };
export const raio = 14;
