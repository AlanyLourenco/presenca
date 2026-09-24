/* ===========================================================================
 * Projeto Presença — Marco 2 / Atividade 03
 * PRODUTOR: âncora de sala com verificação cruzada de ocupação por CO2
 *
 * Aluna: Alany Gabrielly — matrícula 202105018
 * Responsabilidade individual: COMUNICAÇÃO E RESILIÊNCIA
 * Teste adversarial (final de matrícula 8): evento repetido, fora de ordem
 *                                           ou com salto na sequência
 *
 * RECORTE DO PROJETO
 * O sistema Presença mede permanência de estudantes por rádio. A fraude que
 * nenhuma defesa de rádio alcança é o conluio em massa: a turma deixa os
 * celulares na sala e vai embora — os aparelhos estão genuinamente ali.
 * Esta âncora confere a contagem do rádio contra a física do ar: gente na
 * sala produz CO2. Se o rádio declara 30 estudantes e o CO2 diz sala vazia,
 * alguém mente.
 *
 * ENTRADA SIMULADA — DECLARAÇÃO EXPLÍCITA
 * O potenciômetro representa a concentração de CO2 em ppm. NÃO houve
 * aquisição nem validação de grandeza física real: não há sensor de gás,
 * não há calibração e não há resposta química. O potenciômetro é apenas
 * uma fonte de valor controlável na faixa de 380 a 2200 ppm.
 *
 * LIMITAÇÃO DE TEMPO
 * eventTimeMs é o tempo desde o início da simulação (millis()), não tempo
 * absoluto — o ESP32 não tem relógio sincronizado aqui. O carimbo
 * autoritativo é aplicado pelo consumidor na recepção.
 * ===========================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// --------------------------------------------------------------------------
// Identificação e rede
// --------------------------------------------------------------------------
const char* DEVICE_ID  = "anc-204-A";
const char* ENTITY_ID  = "sala-204";

const char* WIFI_SSID  = "Wokwi-GUEST";
const char* WIFI_PASS  = "";

const char* MQTT_HOST  = "broker.hivemq.com";
const int   MQTT_PORT  = 1883;

const char* TOPICO_AMBIENTE = "ufg/ssu/presenca/alany/sala-204/ambiente";
const char* TOPICO_COMANDO  = "ufg/ssu/presenca/alany/sala-204/comando";

// --------------------------------------------------------------------------
// Pinos
// --------------------------------------------------------------------------
const int PINO_POT          = 34;  // entrada analógica — CO2 simulado
const int PINO_BTN_ANOMALIA = 25;  // injeta anomalia de sequência
const int PINO_BTN_REDE     = 26;  // simula queda de rede
const int PINO_LED_VERDE    = 14;
const int PINO_LED_AMARELO  = 27;
const int PINO_LED_VERMELHO = 13;

// --------------------------------------------------------------------------
// Parâmetros da regra
//   Todos são constantes de configuração. Na sala real, os tempos seriam de
//   minutos; aqui estão comprimidos para caber na demonstração.
// --------------------------------------------------------------------------
const float  PPM_MIN_VALIDO      = 350.0;   // faixa física do sensor
const float  PPM_MAX_VALIDO      = 5000.0;
const float  SALTO_MAX_PPM       = 300.0;   // variação instantânea implausível
const float  LIMIAR_OCUPADA      = 800.0;   // histerese: entra em OCUPADA
const float  LIMIAR_VAZIA        = 600.0;   // histerese: volta para VAZIA
const unsigned long PERSIST_OCUPADA     = 6000;   // sustentação exigida
const unsigned long PERSIST_VAZIA       = 8000;
const unsigned long VALIDADE_LEITURA    = 10000;  // expira o último dado bom
const int           CONTAGEM_SUSPEITA   = 10;     // rádio declarando ocupação
const unsigned long PERSIST_INCOERENCIA = 10000;  // antes de acusar
const unsigned long TEMPO_MINIMO_ESTADO = 3000;   // rearme: evita oscilação
const unsigned long INTERVALO_AMOSTRA   = 400;
const unsigned long INTERVALO_PUBLICACAO = 2000;
const int    JANELA_MEDIA        = 5;       // média móvel
const int    MAX_FILA            = 20;      // fila de store-and-forward

// --------------------------------------------------------------------------
// Estados
// --------------------------------------------------------------------------
enum Ocupacao { OCUP_INDETERMINADA = 0, OCUP_VAZIA = 1, OCUP_OCUPADA = 2 };
enum Estado   { EST_COERENTE = 0, EST_ATENCAO = 1, EST_INCOERENTE = 2 };
enum Anomalia { ANOM_NENHUMA = 0, ANOM_DUPLICATA = 1, ANOM_FORA_DE_ORDEM = 2, ANOM_SALTO = 3 };

const char* NOME_OCUPACAO[] = { "INDETERMINADA", "VAZIA", "OCUPADA" };
const char* NOME_ESTADO[]   = { "COERENTE", "ATENCAO", "INCOERENTE" };
const char* NOME_ANOMALIA[] = { "nenhuma", "duplicata", "fora-de-ordem", "salto" };

// --------------------------------------------------------------------------
// Estado mantido
// --------------------------------------------------------------------------
float  janela[JANELA_MEDIA];
int    janelaPreenchida = 0;
int    janelaIndice     = 0;
float  ppmFiltrado      = 0.0;
bool   temLeituraValida = false;
unsigned long ultimaLeituraValidaMs = 0;
unsigned int  amostrasInvalidas     = 0;
int           invalidasSeguidas     = 0;

Ocupacao ocupacao = OCUP_INDETERMINADA;
unsigned long tempoAcimaOcupada = 0;
unsigned long tempoAbaixoVazia  = 0;

Estado estado = EST_COERENTE;
unsigned long tempoIncoerente   = 0;
unsigned long ultimaMudancaEstado = 0;

int contagemRadio = 0;
String ultimoComandoId = "";

unsigned long sequencia = 0;
unsigned long ultimaSequenciaEnviada = 0;

// fila de store-and-forward
struct EventoPendente {
  unsigned long seq;
  float         valor;
  uint8_t       estado;
  uint8_t       ocupacao;
  int           contagem;
  unsigned long tempoMs;
  unsigned int  invalidas;
};
EventoPendente fila[MAX_FILA];
int filaInicio = 0, filaTamanho = 0;
unsigned int descartadosPorFilaCheia = 0;

bool redeSimuladaCaida = false;
Anomalia proximaAnomalia = ANOM_DUPLICATA;   // cicla a cada aperto
Anomalia anomaliaArmada  = ANOM_NENHUMA;

unsigned long ultimaAmostraMs = 0;
unsigned long ultimaPublicacaoMs = 0;

WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);

Adafruit_SSD1306 display(128, 64, &Wire, -1);
bool temDisplay = false;

// ==========================================================================
// ENTRADA E VALIDAÇÃO
// ==========================================================================

// Converte a leitura do potenciômetro para a faixa representada de CO2.
float lerPpmBruto() {
  int cru = analogRead(PINO_POT);            // 0..4095
  return 380.0 + (cru / 4095.0) * (2200.0 - 380.0);
}

/* Valida e filtra. Duas rejeições distintas:
 *   1. fora da faixa física do sensor  -> leitura impossível
 *   2. salto instantâneo grande demais -> ruído: a concentração de um gás
 *      num ambiente fechado não muda centenas de ppm em 400 ms
 * Retorna true se a amostra foi aceita.
 */
bool amostrar() {
  float bruto = lerPpmBruto();

  if (bruto < PPM_MIN_VALIDO || bruto > PPM_MAX_VALIDO) {
    amostrasInvalidas++; invalidasSeguidas++;
    Serial.printf("[VALIDACAO] descartada: %.1f ppm fora da faixa [%.0f, %.0f]\n",
                  bruto, PPM_MIN_VALIDO, PPM_MAX_VALIDO);
    return false;
  }

  if (temLeituraValida && fabs(bruto - ppmFiltrado) > SALTO_MAX_PPM) {
    amostrasInvalidas++; invalidasSeguidas++;
    Serial.printf("[VALIDACAO] descartada: salto de %.1f ppm em %lu ms e implausivel\n",
                  fabs(bruto - ppmFiltrado), INTERVALO_AMOSTRA);
    return false;
  }

  janela[janelaIndice] = bruto;
  janelaIndice = (janelaIndice + 1) % JANELA_MEDIA;
  if (janelaPreenchida < JANELA_MEDIA) janelaPreenchida++;

  float soma = 0;
  for (int i = 0; i < janelaPreenchida; i++) soma += janela[i];
  ppmFiltrado = soma / janelaPreenchida;

  temLeituraValida = true;
  invalidasSeguidas = 0;
  ultimaLeituraValidaMs = millis();
  return true;
}

// ==========================================================================
// REGRA — não é comparação instantânea
// ==========================================================================

/* Camada 1: ocupação pelo CO2.
 * Usa histerese (800 sobe / 600 desce) e persistência: a condição precisa
 * se sustentar por segundos antes de mudar o estado. A faixa morta entre os
 * dois limiares impede oscilação de quem está na fronteira.
 */
void atualizarOcupacao(unsigned long agora, unsigned long dt) {
  // Validade do último dado: sem leitura boa recente, a ocupação expira.
  if (!temLeituraValida || (agora - ultimaLeituraValidaMs) > VALIDADE_LEITURA) {
    if (ocupacao != OCUP_INDETERMINADA) {
      Serial.println("[REGRA] ultimo dado expirou -> ocupacao INDETERMINADA");
    }
    ocupacao = OCUP_INDETERMINADA;
    tempoAcimaOcupada = tempoAbaixoVazia = 0;
    return;
  }

  if (janelaPreenchida < JANELA_MEDIA) return;   // ainda enchendo a janela

  if (ppmFiltrado >= LIMIAR_OCUPADA) {
    tempoAcimaOcupada += dt; tempoAbaixoVazia = 0;
    if (tempoAcimaOcupada >= PERSIST_OCUPADA && ocupacao != OCUP_OCUPADA) {
      ocupacao = OCUP_OCUPADA;
      Serial.printf("[REGRA] CO2 %.0f ppm sustentado por %lu ms -> OCUPADA\n",
                    ppmFiltrado, tempoAcimaOcupada);
    }
  } else if (ppmFiltrado <= LIMIAR_VAZIA) {
    tempoAbaixoVazia += dt; tempoAcimaOcupada = 0;
    if (tempoAbaixoVazia >= PERSIST_VAZIA && ocupacao != OCUP_VAZIA) {
      ocupacao = OCUP_VAZIA;
      Serial.printf("[REGRA] CO2 %.0f ppm sustentado por %lu ms -> VAZIA\n",
                    ppmFiltrado, tempoAbaixoVazia);
    }
  } else {
    // faixa morta da histerese: mantém o estado, não acumula tempo
    tempoAcimaOcupada = tempoAbaixoVazia = 0;
  }
}

/* Camada 2: verificação cruzada — COMBINA DUAS ENTRADAS.
 * O rádio (via consumidor) declara quantos estudantes estão na sala.
 * O CO2 diz se há gente. Discordância sustentada = suspeita de conluio.
 */
void atualizarEstado(unsigned long agora, unsigned long dt) {
  bool condicaoSuspeita = (contagemRadio >= CONTAGEM_SUSPEITA) && (ocupacao == OCUP_VAZIA);
  bool dadoRuim = (ocupacao == OCUP_INDETERMINADA) || (invalidasSeguidas >= 3);

  Estado novo = estado;

  if (dadoRuim) {
    novo = EST_ATENCAO;                       // sem base para acusar ninguém
    tempoIncoerente = 0;
  } else if (condicaoSuspeita) {
    tempoIncoerente += dt;
    novo = (tempoIncoerente >= PERSIST_INCOERENCIA) ? EST_INCOERENTE : EST_ATENCAO;
  } else {
    tempoIncoerente = 0;
    novo = EST_COERENTE;
  }

  // Rearme: impede oscilação rápida entre estados (comandos repetidos)
  if (novo != estado) {
    if (agora - ultimaMudancaEstado < TEMPO_MINIMO_ESTADO) return;
    Serial.printf("[REGRA] estado %s -> %s (co2=%.0f ppm, ocupacao=%s, radio=%d)\n",
                  NOME_ESTADO[estado], NOME_ESTADO[novo],
                  ppmFiltrado, NOME_OCUPACAO[ocupacao], contagemRadio);
    estado = novo;
    ultimaMudancaEstado = agora;
  }
}

// ==========================================================================
// ATUAÇÃO
// ==========================================================================
void atuar() {
  // Comportamento seguro: ATENCAO nunca acusa, apenas sinaliza incerteza.
  digitalWrite(PINO_LED_VERDE,    estado == EST_COERENTE);
  digitalWrite(PINO_LED_AMARELO,  estado == EST_ATENCAO);
  digitalWrite(PINO_LED_VERMELHO, estado == EST_INCOERENTE);

  if (!temDisplay) return;
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  display.setCursor(0, 0);
  display.printf("%s", DEVICE_ID);
  display.setCursor(0, 12);
  display.setTextSize(2);
  display.printf("%.0f ppm", ppmFiltrado);
  display.setTextSize(1);
  display.setCursor(0, 32);
  display.printf("CO2: %s", NOME_OCUPACAO[ocupacao]);
  display.setCursor(0, 42);
  display.printf("Radio: %d  Seq: %lu", contagemRadio, sequencia);
  display.setCursor(0, 54);
  if (redeSimuladaCaida) display.printf("REDE OFF  fila:%d", filaTamanho);
  else                   display.printf("%s", NOME_ESTADO[estado]);
  display.display();
}

// ==========================================================================
// EVENTO
// ==========================================================================
void montarJson(char* buf, size_t n, unsigned long seq, float valor,
                uint8_t est, uint8_t ocup, int contagem, unsigned long tempoMs,
                unsigned int invalidas, bool bufferizado, Anomalia anom) {
  snprintf(buf, n,
    "{\"eventType\":\"sala.ambiente.v1\","
    "\"eventId\":\"%s#%lu\","
    "\"deviceId\":\"%s\",\"entityId\":\"%s\","
    "\"eventTimeMs\":%lu,\"sequence\":%lu,"
    "\"value\":%.1f,\"unit\":\"ppm\",\"state\":\"%s\","
    "\"ocupacaoCo2\":\"%s\",\"contagemRadio\":%d,"
    "\"amostrasInvalidas\":%u,\"bufferizado\":%s,"
    "\"anomaliaInjetada\":\"%s\"}",
    DEVICE_ID, seq, DEVICE_ID, ENTITY_ID, tempoMs, seq,
    valor, NOME_ESTADO[est], NOME_OCUPACAO[ocup], contagem,
    invalidas, bufferizado ? "true" : "false", NOME_ANOMALIA[anom]);
}

void enfileirar(unsigned long seq, float valor, unsigned long tempoMs) {
  if (filaTamanho >= MAX_FILA) {
    // Teto da fila: descarta o MAIS ANTIGO e registra o descarte, para que
    // o intervalo apareça como incompleto em vez de silenciosamente vazio.
    filaInicio = (filaInicio + 1) % MAX_FILA;
    filaTamanho--;
    descartadosPorFilaCheia++;
    Serial.printf("[FILA] cheia: evento mais antigo descartado (total %u)\n",
                  descartadosPorFilaCheia);
  }
  int pos = (filaInicio + filaTamanho) % MAX_FILA;
  fila[pos] = { seq, valor, (uint8_t)estado, (uint8_t)ocupacao,
                contagemRadio, tempoMs, amostrasInvalidas };
  filaTamanho++;
}

void drenarFila() {
  char buf[512];
  while (filaTamanho > 0 && mqtt.connected()) {
    EventoPendente e = fila[filaInicio];
    // bufferizado=true e eventTimeMs ORIGINAL: o consumidor recebe um evento
    // atrasado, não um evento novo. É assim que a permanência é recalculada.
    montarJson(buf, sizeof(buf), e.seq, e.valor, e.estado, e.ocupacao,
               e.contagem, e.tempoMs, e.invalidas, true, ANOM_NENHUMA);
    if (!mqtt.publish(TOPICO_AMBIENTE, buf)) break;
    Serial.printf("[RETRY] entregue atrasado seq=%lu (tempo original %lu ms)\n",
                  e.seq, e.tempoMs);
    Serial.println(buf);
    filaInicio = (filaInicio + 1) % MAX_FILA;
    filaTamanho--;
  }
}

void publicar() {
  unsigned long agora = millis();
  unsigned long seq;
  Anomalia anom = anomaliaArmada;

  // ---- injeção do teste adversarial (final de matrícula 8) ----
  switch (anom) {
    case ANOM_DUPLICATA:
      seq = ultimaSequenciaEnviada;                 // repete a anterior
      Serial.printf("\n>>> ADVERSARIAL: repetindo sequencia %lu\n", seq);
      break;
    case ANOM_FORA_DE_ORDEM:
      seq = (ultimaSequenciaEnviada > 3) ? ultimaSequenciaEnviada - 3 : 1;
      Serial.printf("\n>>> ADVERSARIAL: enviando fora de ordem, seq %lu apos %lu\n",
                    seq, ultimaSequenciaEnviada);
      break;
    case ANOM_SALTO:
      sequencia += 6;                                // pula 5 números
      seq = sequencia;
      Serial.printf("\n>>> ADVERSARIAL: salto de %lu para %lu\n",
                    ultimaSequenciaEnviada, seq);
      break;
    default:
      sequencia++;
      seq = sequencia;
      break;
  }
  anomaliaArmada = ANOM_NENHUMA;

  char buf[512];
  montarJson(buf, sizeof(buf), seq, ppmFiltrado, (uint8_t)estado,
             (uint8_t)ocupacao, contagemRadio, agora, amostrasInvalidas,
             false, anom);

  Serial.println(buf);                              // requisito 5.2

  if (redeSimuladaCaida || !mqtt.connected()) {
    enfileirar(seq, ppmFiltrado, agora);
    Serial.printf("[REDE] indisponivel: evento seq=%lu retido (fila %d/%d)\n",
                  seq, filaTamanho, MAX_FILA);
  } else {
    mqtt.publish(TOPICO_AMBIENTE, buf);
  }

  if (anom == ANOM_NENHUMA || anom == ANOM_SALTO) ultimaSequenciaEnviada = seq;
}

// ==========================================================================
// COMANDO RECEBIDO — segunda entrada da regra
// ==========================================================================
void aoReceberComando(char* topico, byte* carga, unsigned int tamanho) {
  String msg;
  for (unsigned int i = 0; i < tamanho; i++) msg += (char)carga[i];

  int pId = msg.indexOf("\"commandId\":\"");
  String cmdId = "";
  if (pId >= 0) {
    int ini = pId + 13;
    int fim = msg.indexOf('"', ini);
    if (fim > ini) cmdId = msg.substring(ini, fim);
  }

  // Idempotência: comando já aplicado é ignorado. Entrega duplicada pelo
  // broker (QoS 1 reentrega) não altera o estado.
  if (cmdId.length() > 0 && cmdId == ultimoComandoId) {
    Serial.printf("[COMANDO] %s ja aplicado, ignorado\n", cmdId.c_str());
    return;
  }

  int p = msg.indexOf("\"contagem\":");
  if (p < 0) { Serial.println("[COMANDO] invalido: sem campo contagem"); return; }
  int valor = msg.substring(p + 11).toInt();
  if (valor < 0 || valor > 200) {
    Serial.printf("[COMANDO] invalido: contagem %d fora da faixa\n", valor);
    return;
  }

  contagemRadio = valor;
  ultimoComandoId = cmdId;
  Serial.printf("[COMANDO] %s aplicado: contagem do radio = %d\n",
                cmdId.c_str(), contagemRadio);
}

// ==========================================================================
// BOTÕES
// ==========================================================================
void lerBotoes() {
  static bool  ultAnom = HIGH, ultRede = HIGH;
  static unsigned long tAnom = 0, tRede = 0;
  const unsigned long DEBOUNCE = 50;
  unsigned long agora = millis();

  bool bAnom = digitalRead(PINO_BTN_ANOMALIA);
  if (bAnom != ultAnom && agora - tAnom > DEBOUNCE) {
    tAnom = agora;
    if (bAnom == LOW) {                       // borda de descida
      anomaliaArmada  = proximaAnomalia;
      Serial.printf("\n### anomalia armada: %s (aplica na proxima publicacao)\n",
                    NOME_ANOMALIA[anomaliaArmada]);
      proximaAnomalia = (Anomalia)((proximaAnomalia % 3) + 1);   // cicla 1,2,3
    }
    ultAnom = bAnom;
  }

  bool bRede = digitalRead(PINO_BTN_REDE);
  if (bRede != ultRede && agora - tRede > DEBOUNCE) {
    tRede = agora;
    if (bRede == LOW) {
      redeSimuladaCaida = !redeSimuladaCaida;
      Serial.printf("\n### rede simulada: %s\n",
                    redeSimuladaCaida ? "INDISPONIVEL" : "RESTABELECIDA");
      if (!redeSimuladaCaida) drenarFila();
    }
    ultRede = bRede;
  }
}

// ==========================================================================
void conectarMqtt() {
  if (redeSimuladaCaida || mqtt.connected()) return;
  String id = String(DEVICE_ID) + "-" + String(random(0xffff), HEX);
  if (mqtt.connect(id.c_str())) {
    mqtt.subscribe(TOPICO_COMANDO);
    Serial.printf("[MQTT] conectado; assinando %s\n", TOPICO_COMANDO);
    drenarFila();
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(PINO_BTN_ANOMALIA, INPUT_PULLUP);
  pinMode(PINO_BTN_REDE,     INPUT_PULLUP);
  pinMode(PINO_LED_VERDE,    OUTPUT);
  pinMode(PINO_LED_AMARELO,  OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);

  Wire.begin(21, 22);
  temDisplay = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (temDisplay) { display.clearDisplay(); display.display(); }

  Serial.println("\n=== Presenca / ancora de sala — produtor ===");
  Serial.printf("dispositivo=%s  entidade=%s\n", DEVICE_ID, ENTITY_ID);
  Serial.println("POT = CO2 simulado | BTN1 = anomalia de sequencia | BTN2 = queda de rede");

  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  Serial.print("[WIFI] conectando");
  while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
  Serial.printf(" ok: %s\n", WiFi.localIP().toString().c_str());

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(aoReceberComando);
  mqtt.setBufferSize(512);               // o payload excede os 256 padrão
  conectarMqtt();

  ultimaMudancaEstado = millis();
}

void loop() {
  unsigned long agora = millis();

  lerBotoes();
  if (!redeSimuladaCaida) { conectarMqtt(); mqtt.loop(); }

  if (agora - ultimaAmostraMs >= INTERVALO_AMOSTRA) {
    unsigned long dt = agora - ultimaAmostraMs;
    ultimaAmostraMs = agora;
    amostrar();
    atualizarOcupacao(agora, dt);
    atualizarEstado(agora, dt);
    atuar();
  }

  if (agora - ultimaPublicacaoMs >= INTERVALO_PUBLICACAO) {
    ultimaPublicacaoMs = agora;
    publicar();
  }
}
