/**
 * Constantes de configuração do aplicativo — MARCO 3 (segurança).
 *
 * O broker agora é o EMQX Cloud: só TLS, com usuário e senha. O endereço, a
 * senha do papel "app" e a chave pública do servidor ficam em segredos.ts,
 * gerado por marco-03/configurar.py e fora do git.
 *
 * Cópia do app do Marco 2 em que a âncora é o notebook, anunciando por
 * Bluetooth (prototipo-1/ancora/ancora.py), e o celular mede o sinal de verdade.
 * Os tópicos ficam em .../proto1/ para não se misturar com o Marco 2.
 *
 * Os tópicos e os parâmetros do aparelho são os mesmos do ESP32 do Marco 2
 * (marco-02/aparelho/sketch.ino) e do servidor (marco-02/servidor/config.exemplo.json):
 * o celular entra no lugar do ESP32 sem que o servidor precise saber a diferença.
 */

// Broker: MQTT dentro de WebSocket com TLS (wss://…:8084), usuário e senha.
export { BROKER_URL, CHAVE_PUBLICA_SERVIDOR, MQTT_SENHA, MQTT_USUARIO } from './segredos.ts';

export const TOPICO_BASE = 'ufg/ssu/presenca/alany/m3';

export const topicos = {
  heartbeat: (sala: string) => `${TOPICO_BASE}/${sala}/heartbeat`,
  estado: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/estado/${aluno}`,
  aviso: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/aviso/${aluno}`,
  turma: (codigo: string) => `${TOPICO_BASE}/turma/${codigo}`,
};

// Salas que o servidor conhece (polígono e posição das âncoras ficam lá).
export const SALAS: Record<string, { ancoras: string[] }> = {
  'sala-pc': { ancoras: ['anc-pc-1'] },
};
export const SALA_PADRAO = 'sala-pc';

// Âncora Bluetooth — o mesmo formato que ancora.py anuncia
export const BLE_EMPRESA = 0xffff;                     // código reservado para testes
export const BLE_PREFIXO = [0x50, 0x52, 0x53, 0x31];   // "PRS1"
export const BLE_JANELA_MS = 2000;      // mediana do RSSI nos últimos 2 s
export const BLE_SUMIU_MS = 4000;       // sem anúncio por 4 s: âncora não ouvida
export const BLE_MINIMO_AMOSTRAS = 3;   // abaixo disso a região fica indeterminada

// Distância-limite: perto do notebook é "na sala". O limiar é o RSSI medido a
// 1 m na calibração; a histerese evita oscilar na borda.
export const DISTANCIA_LIMITE_M = 1;
export const HISTERESE_DB = 5;          // entra acima do limiar, sai 5 dB abaixo
export const CALIBRACAO_MS = 8000;
export const EXPOENTE_PERDA = 2.2;      // para estimar a distância na tela

// Aparelho — mesmos valores do sketch.ino
export const RSSI_MIN = -105;            // faixa do controle de sinal
export const RSSI_MAX = -35;
export const RSSI_NAO_OUVIDA = -100;     // abaixo disso: âncora não ouvida
export const LIMIAR_ENTRADA = -70;       // histerese: entra DENTRO_ALCANCE
export const LIMIAR_SAIDA = -85;         // histerese: volta a FORA_ALCANCE
export const JANELA_MEDIA = 5;           // média móvel por âncora
export const INTERVALO_AMOSTRA_MS = 100;
export const INTERVALO_HEARTBEAT_MS = 500;   // real: 60–90 s, comprimido
export const VALIDADE_ESTADO_MS = 4000;      // resposta do servidor expira
export const MAX_FILA = 60;                  // 30 s de heartbeats retidos

// Posições de demonstração — as mesmas receitas dos potenciômetros no README do Marco 2
export const POSICOES: { nome: string; rssi: [number, number, number] }[] = [
  { nome: 'Dentro da sala', rssi: [-56, -56, -56] },
  { nome: 'Corredor', rssi: [-70, -49, -56] },
  { nome: 'Fora do prédio', rssi: [-105, -105, -105] },
];

// Turma
export const ALFABETO_CODIGO = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'; // sem 0/O, 1/I/L
export const TAMANHO_CODIGO = 6;
export const ESPERA_TURMA_MS = 8000;        // quanto esperar a configuração publicada
export const DURACAO_AULA_DEMO_S = 100;     // 50 min ÷ escala 30 do servidor
