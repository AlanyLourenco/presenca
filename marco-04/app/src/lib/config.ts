/**
 * Constantes de configuração do aplicativo — MARCO 4 (fluxo completo).
 *
 * Marco 4: heartbeat a cada 5 s (pedido do professor), sensores do celular
 * (acelerômetro e bateria) publicados no broker, comandos do atuador, relatório
 * da turma e modo segundo plano. Uma âncora (o notebook); o código aceita mais.
 *
 * O broker agora é o EMQX Cloud: só TLS, com usuário e senha. O endereço, a
 * senha do papel "app" e a chave pública do servidor ficam em segredos.ts,
 * gerado por marco-04/configurar.py e fora do git.
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

export const TOPICO_BASE = 'ufg/ssu/presenca/alany/m4';

export const topicos = {
  heartbeat: (sala: string) => `${TOPICO_BASE}/${sala}/heartbeat`,
  estado: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/estado/${aluno}`,
  aviso: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/aviso/${aluno}`,
  turma: (codigo: string) => `${TOPICO_BASE}/turma/${codigo}`,
  // Marco 4
  sensor: (sala: string) => `${TOPICO_BASE}/${sala}/sensor`,
  comando: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/comando/${aluno}`,
  comandoAck: (sala: string, aluno: string) => `${TOPICO_BASE}/${sala}/comando-ack/${aluno}`,
  comandoAckTodos: (sala: string) => `${TOPICO_BASE}/${sala}/comando-ack/+`,
  /** Retido, um por aluno: o servidor recebe mesmo se estava fora na hora. */
  cadastro: (aluno: string) => `${TOPICO_BASE}/cadastro/${aluno}`,
  relatorio: (codigo: string) => `${TOPICO_BASE}/relatorio/${codigo}`,
};

// Salas que o servidor conhece (polígono e posição das âncoras ficam lá).
export const SALAS: Record<string, { ancoras: string[] }> = {
  // Marco 4: só o notebook (anc-pc-1). Para a ESP32, acrescente 'anc-pc-2' aqui e
  // na sala do servidor (config.exemplo.json). Âncora não ouvida vai como null.
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
export const INTERVALO_HEARTBEAT_MS = 5000;  // Marco 4: 5 s (pedido do professor)
export const INTERVALO_TELA_MS = 500;        // a tela e a mediana do RSSI seguem a cada 0,5 s
export const VALIDADE_ESTADO_MS = 12000;     // resposta do servidor expira (> 2 heartbeats)
export const MAX_FILA = 72;                  // 6 min de heartbeats retidos sem rede

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
export const DURACAO_AULA_DEMO_S = 120;     // 2 min = 50 min ÷ escala 25 do servidor

// Sensores do celular (Marco 4)
export const ACELEROMETRO_INTERVALO_MS = 100;   // 10 leituras por segundo
export const MOVIMENTO_PARADO_G = 0.01;          // desvio-padrão abaixo disso = sobre a mesa

// Atuador (Marco 4)
export const PISCADAS_LANTERNA = 6;
export const PISCADA_MS = 350;
