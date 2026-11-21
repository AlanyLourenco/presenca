# Âncora ESP32 (anc-pc-2)

A segunda âncora da sala. Faz o mesmo que [`../ancora/ancora.py`](../ancora/ancora.py) faz no
notebook: anuncia por Bluetooth um token que muda a cada 12 s. Mostra que a âncora da parede é
uma plaquinha de R$ 30 ligada numa tomada USB, e não precisa de computador.

Placa: **ESP32 DOIT DevKit V1** (ESP32-WROOM-32, USB-C). Qualquer ESP32 com Bluetooth LE serve.

## 1. Segredo e Wi-Fi (no PC)

1. Em `marco-04\segredos.json`, preencha `"wifi": {"nome": "...", "senha": "..."}`. O Wi-Fi tem
   que ser de **2,4 GHz** (o ESP32 não pega 5 GHz); o hotspot do celular serve.
2. `python configurar.py` → gera `esp32-ancora\segredos.h` com o Wi-Fi e o segredo da
   `anc-pc-2` (o mesmo que o servidor usa para conferir o token). Este arquivo **não vai para
   o git**.

O Wi-Fi é só para acertar o relógio (NTP): sem hora certa não há janela de 12 s. A âncora não
manda nada pela rede e nunca fala com o broker.

## 2. Gravar

**Arduino IDE 2:**

1. *Arquivo → Preferências → URLs adicionais*:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. *Ferramentas → Placa → Gerenciador de placas* → instale **esp32** (Espressif Systems, 3.x).
3. Abra `esp32-ancora\esp32-ancora.ino`. Placa: **DOIT ESP32 DEVKIT V1**. Porta: a COM que
   aparecer ao ligar o cabo (se não aparecer nenhuma, instale o driver **CP210x** ou **CH340**,
   conforme o chip USB da placa).
4. **Carregar**. Se ficar em `Connecting....`, segure o botão **BOOT** da placa até começar.

**Ou `arduino-cli`:**

```powershell
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 esp32-ancora
arduino-cli upload  --fqbn esp32:esp32:esp32doit-devkit-v1 -p COM5 esp32-ancora   # a sua porta
```

## 3. Conferir

Monitor serial a **115200**:

```
Wi-Fi.... ok
Hora (NTP).. ok
janela 149595431  token 3fa2c917
janela 149595432  token 81d04b6e
```

Uma linha nova a cada 12 s. Depois, pode ligar a placa em qualquer carregador USB.

## 4. Usar na aula

1. App → *Área do administrador* → a turma → a âncora **anc-pc-2** aparece ao lado da
   **anc-pc-1** → **Calibrar** a 1 m dela.
2. O celular do aluno passa a contar "dentro" perto de **qualquer** das duas âncoras.
3. No servidor, os heartbeats que ouvem a ESP32 trazem o token dela e são aceitos. Se ela for
   desligada no meio da aula, aparece `! ÂNCORA MUDA anc-pc-2`.

## Modo escuta (medição)

`MODO_ESCUTA = true` no começo do sketch troca o papel: o ESP32 conta quantos aparelhos
Bluetooth ouve em volta e mostra o RSSI de cada um. Serve só para medir ("quantos dispositivos
um ESP32 ouve?"); na aula ele fica `false`.

| Problema | O que fazer |
|---|---|
| fica em `Wi-Fi....` | rede de 5 GHz, ou nome/senha errados → corrija `segredos.json` e rode `configurar.py` de novo |
| fica em `Hora (NTP)....` | a rede bloqueia NTP → use o hotspot do celular |
| servidor recusa com `TOKEN VENCIDO` só para a anc-pc-2 | `segredos.h` antigo → `python configurar.py` e grave de novo |
