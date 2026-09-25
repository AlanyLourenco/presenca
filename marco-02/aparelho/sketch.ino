/* ==========================================================================
 * Projeto Presença — Marco 2 / Atividade 03
 * APARELHO DO ESTUDANTE: mede o sinal das 3 âncoras e envia heartbeat
 *
 * Aluna: Alany Gabrielly — matrícula 202105018
 * Responsabilidade individual: COMUNICAÇÃO E RESILIÊNCIA
 * Teste adversarial (final de matrícula 8): evento repetido, fora de ordem
 *                                           ou com salto na sequência
 *
 * PAPEL NO SISTEMA
 * No Presença a âncora é um farol: transmite e nunca escuta. Quem mede o
 * sinal é o aparelho do estudante, que envia ao servidor o RSSI de cada
 * âncora. O servidor localiza (trilateração + polígono da sala), aplica a
 * máquina de estados e devolve o estado e os avisos. Este ESP32 faz o papel
 * desse aparelho.
 *
 * ENTRADA SIMULADA — DECLARAÇÃO EXPLÍCITA
 * Os três potenciômetros representam o RSSI (dBm) ouvido de cada âncora:
 * A, B e C, de cima para baixo. NÃO houve aquisição de sinal de rádio real:
 * o Wokwi não simula propagação, não há BLE, distância nem parede. Os
 * potenciômetros são apenas fontes de valor controláveis na faixa de
 * -105 a -35 dBm. Abaixo de -100 dBm a âncora é tratada como NÃO OUVIDA.
 *
 * LIMITAÇÃO DE TEMPO
 * eventTimeMs é o tempo desde o boot (millis()), não tempo absoluto. O
 * servidor usa só a diferença entre eventos de um mesmo boot.
 * ========================================================================== */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// --------------------------------------------------------------------------
// Identidade e rede
// --------------------------------------------------------------------------
const char* DEVICE_ID  = "apar-01";
const char* ALUNO      = "tok-7f3a";   // pseudônimo, nunca MAC/IMEI/nome
const char* ENTITY_ID  = "sala-204";
const char* ID_ANCORA[3] = { "anc-204-A", "anc-204-B", "anc-204-C" };

const char* WIFI_SSID  = "Wokwi-GUEST";
const char* WIFI_PASS  = "";

const char* MQTT_HOST  = "broker.hivemq.com";
const int   MQTT_PORT  = 1883;

const char* TOPICO_HEARTBEAT = "ufg/ssu/presenca/alany/sala-204/heartbeat";
const char* TOPICO_ESTADO    = "ufg/ssu/presenca/alany/sala-204/estado/tok-7f3a";
const char* TOPICO_AVISO     = "ufg/ssu/presenca/alany/sala-204/aviso/tok-7f3a";

// --------------------------------------------------------------------------
// Pinos
// --------------------------------------------------------------------------
const int PINO_POT[3]       = { 34, 35, 32 };  // ADC1: RSSI das âncoras A, B, C
const int PINO_BTN_ANOMALIA = 25;
const int PINO_BTN_REDE     = 26;
const int PINO_LED_VERDE    = 14;   // PRESENTE
const int PINO_LED_AMARELO  = 27;   // AUSENCIA_TOLERADA (pisca em aviso)
const int PINO_LED_VERMELHO = 13;   // FORA
const int PINO_BUZZER       = 18;   // notificação

// --------------------------------------------------------------------------
// Parâmetros — constantes de configuração
// --------------------------------------------------------------------------
const float RSSI_POT_MIN        = -105.0;  // escala do potenciômetro
const float RSSI_POT_MAX        = -35.0;
const float RSSI_NAO_OUVIDA     = -100.0;  // abaixo disso: âncora não ouvida
const float LIMIAR_ENTRADA      = -70.0;   // histerese: entra DENTRO_ALCANCE
const float LIMIAR_SAIDA        = -85.0;   // histerese: volta a FORA_ALCANCE
const int   JANELA_MEDIA        = 5;       // média móvel por âncora
const unsigned long INTERVALO_AMOSTRA   = 100;
const unsigned long INTERVALO_HEARTBEAT = 500;   // real: 60–90 s, comprimido
const unsigned long VALIDADE_ESTADO     = 4000;  // resposta do servidor expira
const unsigned long DURACAO_AVISO       = 6000;  // aviso fica na tela
const int   MAX_FILA            = 60;      // 30 s de heartbeats retidos
const unsigned long DEBOUNCE    = 50;

// --------------------------------------------------------------------------
enum Regiao   { REG_INDETERMINADA = 0, REG_DENTRO = 1, REG_FORA = 2 };
enum Anomalia { ANOM_NENHUMA = 0, ANOM_DUPLICATA = 1, ANOM_FORA_DE_ORDEM = 2, ANOM_SALTO = 3 };
const char* NOME_REGIAO[]   = { "INDETERMINADA", "DENTRO_ALCANCE", "FORA_ALCANCE" };
const char* NOME_ANOMALIA[] = { "nenhuma", "duplicata", "fora-de-ordem", "salto" };

// --------------------------------------------------------------------------
// Estado mantido
// --------------------------------------------------------------------------
float janela[3][JANELA_MEDIA];
int   preenchida[3] = { 0, 0, 0 };
int   indice[3]     = { 0, 0, 0 };
float rssi[3];                      // filtrado
bool  ouvida[3]     = { false, false, false };
unsigned int amostrasInvalidas = 0;

Regiao regiao = REG_INDETERMINADA;

char bootId[5];
unsigned long sequencia = 0;

// resposta do servidor
String estadoServidor   = "";
float  percentual       = 0, orcamentoRestante = 0;
long   ultimoEstadoN    = -1;
unsigned long estadoRecebidoMs = 0;
bool   sessaoEncerrada  = false;

// avisos: idempotência pelos últimos ids exibidos
String avisosVistos[8];
int    avisosIdx = 0;
String avisoTexto = "";
unsigned long avisoDesdeMs = 0;

// teste adversarial e rede
Anomalia proximaAnomalia = ANOM_DUPLICATA;
Anomalia anomaliaArmada  = ANOM_NENHUMA;
bool   redeSimuladaCaida = false;
String ultimoPayload     = "";      // para a duplicata
bool   temRetido         = false;   // para o fora de ordem
String payloadRetido     = "";

struct Pendente {
  unsigned long seq, tempoMs;
  float r[3];
  bool  o[3];
  uint8_t regiao;
};
Pendente fila[MAX_FILA];
int filaInicio = 0, filaTamanho = 0;
unsigned int descartadosFila = 0;

unsigned long ultimaAmostraMs = 0, ultimoHeartbeatMs = 0;

WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_SSD1306 display(128, 64, &Wire, -1);
bool temDisplay = false;

// ==========================================================================
// ENTRADA, VALIDAÇÃO E FILTRO
// ==========================================================================
float lerRssiBruto(int i) {
  int cru = analogRead(PINO_POT[i]);            // 0..4095
  return RSSI_POT_MIN + (cru / 4095.0) * (RSSI_POT_MAX - RSSI_POT_MIN);
}

/* Leitura AUSENTE: abaixo de -100 dBm o aparelho não ouviu a âncora. Não é
 * um número baixo para entrar na média — é falta de dado. A janela daquela
 * âncora é esvaziada para que valores velhos não se misturem aos novos
 * quando ela voltar a ser ouvida. */
void amostrar() {
  for (int i = 0; i < 3; i++) {
    float bruto = lerRssiBruto(i);

    if (isnan(bruto) || bruto > -30.0) {         // fisicamente impossível
      amostrasInvalidas++;
      continue;
    }
    if (bruto < RSSI_NAO_OUVIDA) {
      if (ouvida[i]) Serial.printf("[LEITURA] ancora %s deixou de ser ouvida\n", ID_ANCORA[i]);
      ouvida[i] = false;
      preenchida[i] = 0; indice[i] = 0;
      continue;
    }

    janela[i][indice[i]] = bruto;
    indice[i] = (indice[i] + 1) % JANELA_MEDIA;
    if (preenchida[i] < JANELA_MEDIA) preenchida[i]++;
    float soma = 0;
    for (int k = 0; k < preenchida[i]; k++) soma += janela[i][k];
    rssi[i] = soma / preenchida[i];
    if (!ouvida[i]) Serial.printf("[LEITURA] ancora %s ouvida\n", ID_ANCORA[i]);
    ouvida[i] = true;
  }
}

/* Melhor sinal entre as âncoras ouvidas com a janela cheia. */
bool melhorRssi(float* melhor) {
  bool tem = false;
  for (int i = 0; i < 3; i++) {
    if (ouvida[i] && preenchida[i] == JANELA_MEDIA && (!tem || rssi[i] > *melhor)) {
      *melhor = rssi[i]; tem = true;
    }
  }
  return tem;
}

// ==========================================================================
// REGRA LOCAL — região de rádio com HISTERESE
// ==========================================================================
/* Entra em DENTRO_ALCANCE acima de -70 dBm e só volta a FORA_ALCANCE abaixo
 * de -85 dBm. Entre os dois, mantém: quem senta na borda do alcance não
 * oscila. É o que o iOS faz no monitoramento de região. A persistência de
 * 30 s e o polígono da sala ficam no servidor, que conhece a sala. */
void atualizarRegiao() {
  float melhor;
  bool algumaCheia = false;
  for (int i = 0; i < 3; i++) if (preenchida[i] == JANELA_MEDIA) algumaCheia = true;
  bool nenhumaOuvida = !ouvida[0] && !ouvida[1] && !ouvida[2];

  Regiao nova = regiao;
  if (nenhumaOuvida)                       nova = REG_FORA;
  else if (!melhorRssi(&melhor))           nova = algumaCheia ? regiao : REG_INDETERMINADA;
  else if (melhor > LIMIAR_ENTRADA)        nova = REG_DENTRO;
  else if (melhor < LIMIAR_SAIDA)          nova = REG_FORA;
  else if (regiao == REG_INDETERMINADA)    nova = REG_FORA;   // faixa morta sem histórico
  // senão: faixa morta, mantém

  if (nova != regiao) {
    Serial.printf("[REGIAO] %s -> %s\n", NOME_REGIAO[regiao], NOME_REGIAO[nova]);
    regiao = nova;
  }
}

// ==========================================================================
// HEARTBEAT
// ==========================================================================
String montarJson(unsigned long seq, unsigned long tempoMs, const float* r,
                  const bool* o, uint8_t reg, bool bufferizado, Anomalia anom) {
  char anc[200] = "";
  float melhor = -999; bool tem = false;
  for (int i = 0; i < 3; i++) {
    char item[64];
    if (o[i]) snprintf(item, sizeof(item), "{\"id\":\"%s\",\"rssi\":%.1f}", ID_ANCORA[i], r[i]);
    else      snprintf(item, sizeof(item), "{\"id\":\"%s\",\"rssi\":null}", ID_ANCORA[i]);
    strcat(anc, item);
    if (i < 2) strcat(anc, ",");
    if (o[i] && (!tem || r[i] > melhor)) { melhor = r[i]; tem = true; }
  }
  char valor[12];
  if (tem) snprintf(valor, sizeof(valor), "%.1f", melhor);
  else     strcpy(valor, "null");

  char buf[640];
  snprintf(buf, sizeof(buf),
    "{\"eventType\":\"presenca.heartbeat.v1\","
    "\"eventId\":\"%s#%s#%lu\",\"deviceId\":\"%s\",\"entityId\":\"%s\","
    "\"aluno\":\"%s\",\"bootId\":\"%s\",\"eventTimeMs\":%lu,\"sequence\":%lu,"
    "\"value\":%s,\"unit\":\"dBm\",\"state\":\"%s\",\"ancoras\":[%s],"
    "\"amostrasInvalidas\":%u,\"bufferizado\":%s,\"anomaliaInjetada\":\"%s\"}",
    DEVICE_ID, bootId, seq, DEVICE_ID, ENTITY_ID, ALUNO, bootId, tempoMs, seq,
    valor, NOME_REGIAO[reg], anc, amostrasInvalidas,
    bufferizado ? "true" : "false", NOME_ANOMALIA[anom]);
  return String(buf);
}

void enfileirar(unsigned long seq, unsigned long tempoMs) {
  if (filaTamanho >= MAX_FILA) {
    // Teto: descarta o MAIS ANTIGO e registra. O servidor verá um salto na
    // sequência — o intervalo aparece como sem evidência, não como vazio.
    filaInicio = (filaInicio + 1) % MAX_FILA;
    filaTamanho--; descartadosFila++;
    Serial.printf("[FILA] cheia: heartbeat mais antigo descartado (total %u)\n", descartadosFila);
  }
  Pendente& p = fila[(filaInicio + filaTamanho) % MAX_FILA];
  p.seq = seq; p.tempoMs = tempoMs; p.regiao = regiao;
  for (int i = 0; i < 3; i++) { p.r[i] = rssi[i]; p.o[i] = ouvida[i]; }
  filaTamanho++;
}

void drenarFila() {
  int enviados = 0;
  while (filaTamanho > 0 && mqtt.connected()) {
    Pendente& p = fila[filaInicio];
    // bufferizado=true e eventTimeMs ORIGINAL: o servidor recebe o passado,
    // não o presente, e recalcula a sessão.
    String j = montarJson(p.seq, p.tempoMs, p.r, p.o, p.regiao, true, ANOM_NENHUMA);
    if (!mqtt.publish(TOPICO_HEARTBEAT, j.c_str())) break;
    filaInicio = (filaInicio + 1) % MAX_FILA;
    filaTamanho--; enviados++;
    mqtt.loop();
  }
  if (enviados) Serial.printf("[RETRY] %d heartbeat(s) retidos entregues com atraso\n", enviados);
}

bool enviar(const String& j) {
  if (redeSimuladaCaida || !mqtt.connected()) return false;
  return mqtt.publish(TOPICO_HEARTBEAT, j.c_str());
}

void publicarHeartbeat() {
  unsigned long agora = millis();
  Anomalia anom = anomaliaArmada;
  anomaliaArmada = ANOM_NENHUMA;

  // ---- teste adversarial: DUPLICATA reenvia o último payload idêntico ----
  if (anom == ANOM_DUPLICATA && ultimoPayload.length()) {
    Serial.println("\n>>> ADVERSARIAL: reenviando o ultimo heartbeat (mesmo eventId)");
    Serial.println(ultimoPayload);
    enviar(ultimoPayload);
    return;
  }

  if (anom == ANOM_SALTO) {
    Serial.printf("\n>>> ADVERSARIAL: salto de %lu para %lu (5 numeros nunca enviados)\n",
                  sequencia, sequencia + 6);
    sequencia += 5;
  }
  sequencia++;

  String j = montarJson(sequencia, agora, rssi, ouvida, regiao, false, anom);
  Serial.println(j);                                   // requisito 5.2

  if (redeSimuladaCaida || !mqtt.connected()) {
    enfileirar(sequencia, agora);
    Serial.printf("[REDE] indisponivel: heartbeat seq=%lu retido (fila %d/%d)\n",
                  sequencia, filaTamanho, MAX_FILA);
    return;
  }

  // ---- FORA DE ORDEM: segura este e o entrega depois do próximo ----
  if (anom == ANOM_FORA_DE_ORDEM) {
    Serial.printf("\n>>> ADVERSARIAL: segurando seq=%lu para entregar depois de %lu\n",
                  sequencia, sequencia + 1);
    payloadRetido = j; temRetido = true;
    return;
  }

  enviar(j);
  ultimoPayload = j;
  if (temRetido) {
    Serial.println(">>> ADVERSARIAL: entregando agora o heartbeat retido (fora de ordem)");
    enviar(payloadRetido);
    temRetido = false;
  }
}

// ==========================================================================
// RESPOSTAS DO SERVIDOR
// ==========================================================================
String campoTexto(const String& m, const char* campo) {
  String chave = String("\"") + campo + "\":\"";
  int p = m.indexOf(chave);
  if (p < 0) return "";
  int ini = p + chave.length();
  int fim = m.indexOf('"', ini);
  return fim > ini ? m.substring(ini, fim) : "";
}

float campoNumero(const String& m, const char* campo, float padrao) {
  String chave = String("\"") + campo + "\":";
  int p = m.indexOf(chave);
  return p < 0 ? padrao : m.substring(p + chave.length()).toFloat();
}

void aoReceberEstado(const String& m) {
  // estadoId = srv-204#n. Resposta mais velha que a última aplicada é
  // ignorada: o estado nunca anda para trás por reentrega.
  String id = campoTexto(m, "estadoId");
  long n = id.substring(id.indexOf('#') + 1).toInt();
  // Uma queda grande no número significa servidor reiniciado: aceita.
  if (n <= ultimoEstadoN && ultimoEstadoN - n < 50) return;
  ultimoEstadoN = n;

  String novo = campoTexto(m, "estado");
  if (novo.length() == 0) { Serial.println("[ESTADO] invalido: sem campo estado"); return; }
  if (novo != estadoServidor)
    Serial.printf("[ESTADO] servidor decidiu: %s -> %s\n",
                  estadoServidor.length() ? estadoServidor.c_str() : "-", novo.c_str());
  estadoServidor    = novo;
  percentual        = campoNumero(m, "percentual", 0);
  orcamentoRestante = campoNumero(m, "orcamentoRestanteS", 0);
  sessaoEncerrada   = m.indexOf("\"encerrada\":true") >= 0;
  estadoRecebidoMs  = millis();
}

void aoReceberAviso(const String& m) {
  String id = campoTexto(m, "avisoId");
  for (int i = 0; i < 8; i++) {
    if (avisosVistos[i] == id) {                       // idempotência
      Serial.printf("[AVISO] %s ja exibido, ignorado\n", id.c_str());
      return;
    }
  }
  avisosVistos[avisosIdx] = id; avisosIdx = (avisosIdx + 1) % 8;
  avisoTexto   = campoTexto(m, "texto");
  avisoDesdeMs = millis();
  Serial.printf("[AVISO] %s: %s\n", campoTexto(m, "tipo").c_str(), avisoTexto.c_str());
  tone(PINO_BUZZER, 1760, 400);                        // o aparelho vibra/toca
}

void aoReceber(char* topico, byte* carga, unsigned int tamanho) {
  String m; m.reserve(tamanho);
  for (unsigned int i = 0; i < tamanho; i++) m += (char)carga[i];
  if (strcmp(topico, TOPICO_ESTADO) == 0) aoReceberEstado(m);
  else if (strcmp(topico, TOPICO_AVISO) == 0) aoReceberAviso(m);
}

// ==========================================================================
// ATUAÇÃO
// ==========================================================================
bool estadoValido() {
  return estadoServidor.length() && (millis() - estadoRecebidoMs) <= VALIDADE_ESTADO;
}

void atuar() {
  unsigned long agora = millis();
  bool valido  = estadoValido();
  bool emAviso = avisoTexto.length() && agora - avisoDesdeMs < DURACAO_AVISO;
  bool pisca   = (agora / 250) % 2;

  // Comportamento seguro: resposta expirada NÃO continua acesa como se fosse
  // atual. Sem dado válido, nenhum LED de estado — só o display explica.
  digitalWrite(PINO_LED_VERDE,    valido && estadoServidor == "PRESENTE");
  digitalWrite(PINO_LED_AMARELO,  emAviso ? pisca : (valido && estadoServidor == "AUSENCIA_TOLERADA"));
  digitalWrite(PINO_LED_VERMELHO, valido && estadoServidor == "FORA");

  if (!temDisplay) return;
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.printf("%s  seq %lu", ALUNO, sequencia);

  display.setTextSize(2);
  display.setCursor(0, 11);
  if (redeSimuladaCaida)                display.print("REDE OFF");
  else if (!valido)                     display.print("SEM RESP.");
  else if (estadoServidor == "AUSENCIA_TOLERADA") display.print("AUSENCIA");
  else                                  display.print(estadoServidor);

  display.setTextSize(1);
  if (emAviso) {
    display.setCursor(0, 30);
    display.print(avisoTexto);                         // quebra de linha automática
  } else {
    display.setCursor(0, 30);
    if (redeSimuladaCaida) display.printf("fila %d/%d retidos", filaTamanho, MAX_FILA);
    else display.printf("acum %.0f%%  orc %.0fs%s", percentual, orcamentoRestante,
                        sessaoEncerrada ? " FIM" : "");
    display.setCursor(0, 42);
    for (int i = 0; i < 3; i++) {
      if (ouvida[i]) display.printf("%c%.0f ", 'A' + i, rssi[i]);
      else           display.printf("%c-- ", 'A' + i);
    }
    display.setCursor(0, 54);
    display.print(NOME_REGIAO[regiao]);
  }
  display.display();
}

// ==========================================================================
// BOTÕES
// ==========================================================================
void lerBotoes() {
  static bool ultAnom = HIGH, ultRede = HIGH;
  static unsigned long tAnom = 0, tRede = 0;
  unsigned long agora = millis();

  bool bAnom = digitalRead(PINO_BTN_ANOMALIA);
  if (bAnom != ultAnom && agora - tAnom > DEBOUNCE) {
    tAnom = agora;
    if (bAnom == LOW) {
      anomaliaArmada = proximaAnomalia;
      Serial.printf("\n### anomalia armada: %s (aplica no proximo heartbeat)\n",
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
      Serial.printf("\n### rede simulada: %s\n", redeSimuladaCaida ? "INDISPONIVEL" : "RESTABELECIDA");
      if (!redeSimuladaCaida) drenarFila();
    }
    ultRede = bRede;
  }
}

// ==========================================================================
void conectarMqtt() {
  if (redeSimuladaCaida || mqtt.connected()) return;
  String id = String(DEVICE_ID) + "-" + bootId;
  if (mqtt.connect(id.c_str())) {
    mqtt.subscribe(TOPICO_ESTADO);
    mqtt.subscribe(TOPICO_AVISO, 1);
    Serial.printf("[MQTT] conectado; assinando estado e aviso de %s\n", ALUNO);
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
  pinMode(PINO_BUZZER,       OUTPUT);

  snprintf(bootId, sizeof(bootId), "%04x", (unsigned)(esp_random() & 0xffff));

  Wire.begin(21, 22);
  temDisplay = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (temDisplay) { display.clearDisplay(); display.display(); }

  Serial.println("\n=== Presenca / aparelho do estudante ===");
  Serial.printf("aparelho=%s  aluno=%s  boot=%s\n", DEVICE_ID, ALUNO, bootId);
  Serial.println("POT A/B/C = RSSI das ancoras | azul = anomalia de sequencia | vermelho = queda de rede");

  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  Serial.print("[WIFI] conectando");
  while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
  Serial.printf(" ok: %s\n", WiFi.localIP().toString().c_str());

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(aoReceber);
  mqtt.setBufferSize(768);               // heartbeat passa dos 256 bytes padrão
  conectarMqtt();
}

void loop() {
  unsigned long agora = millis();

  lerBotoes();
  if (!redeSimuladaCaida) { conectarMqtt(); mqtt.loop(); }

  if (agora - ultimaAmostraMs >= INTERVALO_AMOSTRA) {
    ultimaAmostraMs = agora;
    amostrar();
    atualizarRegiao();
    atuar();
  }

  if (agora - ultimoHeartbeatMs >= INTERVALO_HEARTBEAT) {
    ultimoHeartbeatMs = agora;
    publicarHeartbeat();
  }
}
