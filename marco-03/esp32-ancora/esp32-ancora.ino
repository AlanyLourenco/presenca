/*
 * Projeto Presença — Marco 3
 * ÂNCORA ESP32 (prova de conceito em Arduino) — o mesmo farol que o notebook.
 *
 * Faz exatamente o que marco-03/ancora/ancora.py faz, para mostrar que a âncora
 * da parede é um ESP32 de R$ 30 e não precisa do notebook:
 *
 *   - anuncia por Bluetooth LE, código de empresa 0xFFFF (testes), dados
 *       "PRS1" | nº da âncora | token (4 bytes)
 *   - token = HMAC-SHA256(segredo, "anc-pc-1|<janela de 12 s>"), cortado em
 *     4 bytes — o servidor calcula o mesmo e confere (servidor/seguranca.py)
 *   - pega a hora certa por NTP no Wi-Fi (sem hora certa não há janela)
 *
 * MODO_ESCUTA = true troca o papel, SÓ PARA MEDIR (processo inverso): o ESP32
 * varre os anúncios em volta, conta quantos aparelhos distintos ouve e mostra
 * o RSSI de cada um no Serial. Responde "quantos dispositivos um ESP32 ouve".
 *
 * Placa: "ESP32 Dev Module" (núcleo esp32 da Espressif 3.x). Bibliotecas
 * já vêm no núcleo: BLEDevice e mbedtls.
 * NÃO TESTADO EM HARDWARE ainda (não havia ESP32 em mãos): é a prova de
 * conceito para quando houver. O notebook faz o papel dele nos testes.
 */
#include <WiFi.h>
#include <time.h>
#include <BLEDevice.h>
#include <BLEAdvertising.h>
#include <BLEScan.h>
#include "mbedtls/md.h"

// ---- configuração ----------------------------------------------------------
const bool   MODO_ESCUTA = false;          // true = mede em vez de anunciar
const char*  WIFI_NOME   = "COLE-AQUI";
const char*  WIFI_SENHA  = "COLE-AQUI";
const uint8_t ANCORA     = 1;              // anc-pc-1
const char*  NOME_ANCORA = "anc-pc-1";
// O MESMO segredo de segredos.json > ancoras > anc-pc-1 (64 caracteres hex).
const char*  SEGREDO_HEX = "COLE-AQUI-O-SEGREDO-DA-ANCORA";
const uint32_t TOKEN_S   = 12;
const uint16_t EMPRESA   = 0xFFFF;
const uint8_t PREFIXO[4] = {'P', 'R', 'S', '1'};

// ---- token -----------------------------------------------------------------
uint8_t segredo[32];

void hexParaBytes(const char* hex, uint8_t* saida, size_t n) {
  for (size_t i = 0; i < n; i++) {
    char par[3] = {hex[2 * i], hex[2 * i + 1], 0};
    saida[i] = (uint8_t)strtoul(par, nullptr, 16);
  }
}

void tokenDaJanela(uint32_t janela, uint8_t token[4]) {
  char msg[48];
  snprintf(msg, sizeof msg, "%s|%lu", NOME_ANCORA, (unsigned long)janela);
  uint8_t h[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), 1);
  mbedtls_md_hmac_starts(&ctx, segredo, sizeof segredo);
  mbedtls_md_hmac_update(&ctx, (const uint8_t*)msg, strlen(msg));
  mbedtls_md_hmac_finish(&ctx, h);
  mbedtls_md_free(&ctx);
  memcpy(token, h, 4);
}

// ---- farol -----------------------------------------------------------------
BLEAdvertising* anuncio;
uint32_t janelaAtual = 0;

void anunciar(uint32_t janela) {
  uint8_t token[4];
  tokenDaJanela(janela, token);
  // manufacturer data: 2 bytes do código de empresa (little-endian) + dados
  String dados;
  dados += (char)(EMPRESA & 0xFF);
  dados += (char)(EMPRESA >> 8);
  for (uint8_t b : PREFIXO) dados += (char)b;
  dados += (char)ANCORA;
  for (uint8_t b : token) dados += (char)b;

  BLEAdvertisementData ad;
  ad.setFlags(0x06);                       // geral, sem BR/EDR
  ad.setManufacturerData(dados);
  anuncio->stop();
  anuncio->setAdvertisementData(ad);
  anuncio->start();
  Serial.printf("janela %lu  token %02x%02x%02x%02x\n", (unsigned long)janela,
                token[0], token[1], token[2], token[3]);
}

// ---- modo escuta (medição) -------------------------------------------------
BLEScan* varredura;
uint32_t maximo = 0;

void escutar() {
  BLEScanResults* r = varredura->start(3, false);   // 3 s de varredura
  uint32_t n = r->getCount();
  maximo = max(maximo, n);
  Serial.printf("\naparelhos ouvidos em 3 s: %lu (máximo: %lu)\n", (unsigned long)n, (unsigned long)maximo);
  for (uint32_t i = 0; i < n && i < 20; i++) {
    BLEAdvertisedDevice d = r->getDevice(i);
    Serial.printf("  %s  %4d dBm  %s\n", d.getAddress().toString().c_str(), d.getRSSI(),
                  d.haveName() ? d.getName().c_str() : "");
  }
  varredura->clearResults();
}

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  BLEDevice::init("");
  if (MODO_ESCUTA) {
    varredura = BLEDevice::getScan();
    varredura->setActiveScan(true);
    varredura->setInterval(100);
    varredura->setWindow(99);
    Serial.println("Modo ESCUTA: contando aparelhos Bluetooth em volta.");
    return;
  }
  hexParaBytes(SEGREDO_HEX, segredo, sizeof segredo);
  WiFi.begin(WIFI_NOME, WIFI_SENHA);
  Serial.print("Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print('.'); }
  configTime(0, 0, "pool.ntp.org", "a.st1.ntp.br");
  Serial.print("\nHora (NTP)");
  while (time(nullptr) < 1700000000) { delay(300); Serial.print('.'); }
  Serial.println(" ok");
  anuncio = BLEDevice::getAdvertising();
  anuncio->setMinInterval(0x20);           // 20 ms: muitas amostras de RSSI por segundo
  anuncio->setMaxInterval(0x40);
}

void loop() {
  if (MODO_ESCUTA) { escutar(); return; }
  uint32_t janela = (uint32_t)(time(nullptr) / TOKEN_S);
  if (janela != janelaAtual) {             // a janela segue o relógio, como no servidor
    janelaAtual = janela;
    anunciar(janela);
  }
  delay(100);
}
