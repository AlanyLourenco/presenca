/**
 * Constantes de configuração do aplicativo.
 *
 * Os tópicos e os parâmetros do aparelho são os mesmos do ESP32 do Marco 2
 * (marco-02/aparelho/sketch.ino) e do servidor (marco-02/servidor/config.exemplo.json):
 * o celular entra no lugar do ESP32 sem que o servidor precise saber a diferença.
 */

// Broker: o celular fala MQTT dentro de WebSocket seguro (porta 8884). É o mesmo
// broker do ESP32, que continua na 1883; o broker entrega entre os dois transportes.
export const BROKER_URL = 'wss://broker.hivemq.com:8884/mqtt';

export const TOPICO_BASE = 'ufg/ssu/presenca/alany';

export const topicos = {
  heartbeat: (sala: string) => `${TOPICO_BASE}/${sala}/heartbeat`,
  estado: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/estado/${aluno}`,
  aviso: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/aviso/${aluno}`,
  turma: (codigo: string) => `${TOPICO_BASE}/turma/${codigo}`,
};

// Salas que o servidor conhece (polígono e posição das âncoras ficam lá).
export const SALAS: Record<string, { ancoras: [string, string, string] }> = {
  'sala-204': { ancoras: ['anc-204-A', 'anc-204-B', 'anc-204-C'] },
};
export const SALA_PADRAO = 'sala-204';

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
