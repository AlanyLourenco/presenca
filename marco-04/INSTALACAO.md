# Instalação — do computador vazio até a aula rodando

Testado em Windows 11, num notebook de 8 GB de RAM. Os comandos são do PowerShell, rodados
dentro da pasta `marco-04`.

## 0. O que precisa estar instalado

| Programa | Versão usada | Para quê |
|---|---|---|
| Python | 3.10 ou mais nova | servidor, âncora do notebook, simuladores, testes |
| Node.js | 20 ou mais nova (usado: 24) | app e testes do app |
| JDK (Temurin) | 17 | só para **gerar o APK** |
| Android SDK | platform 36, build-tools 36, NDK 27 (em `C:\Android\sdk`) | só para **gerar o APK** |
| Bluetooth | o do notebook | âncora `anc-pc-1` |
| Arduino IDE 2 (ou `arduino-cli`) | com o pacote "esp32" da Espressif | só para a extensão com ESP32 (não usada no Marco 4) |

O **banco não exige instalação**: o script do passo 3 baixa um PostgreSQL portátil.
Docker é opcional.

## 1. Broker MQTT (uma vez)

1. Crie uma conta em https://cloud-intl.emqx.com → **EMQX Broker → New → Serverless**
   (plano grátis, limite de gasto US$ 0). Copie o **Address** (`xxxx.emqxsl.com`).
2. **Access Control → Authentication**: crie os usuários `presenca-servidor` e
   `presenca-app`, cada um com a sua senha.

## 2. Segredos (uma vez)

```powershell
pip install -r servidor\requirements.txt -r ancora\requirements.txt
python configurar.py     # 1ª vez: cria segredos.json — preencha broker, senhas e (se for usar a ESP32) o Wi-Fi
python configurar.py     # 2ª vez: gera o segredo de cada âncora, a chave do servidor,
                         #         app\src\lib\segredos.ts e esp32-ancora\segredos.h
```

Deve terminar sem nenhuma linha "ATENÇÃO". `segredos.json`, `servidor\chave-servidor.pem`,
`app\src\lib\segredos.ts` e `esp32-ancora\segredos.h` **não vão para o git**.

`python servidor\testar_rede.py` diz se a rede alcança o broker. A rede da faculdade bloqueia
as portas 8883 e 8084: use o **hotspot do celular**.

## 3. Banco de dados

**Sem Docker (recomendado em PC com pouca memória):**

```powershell
.\banco\banco.ps1            # 1ª vez: baixa ~310 MB, monta C:\presenca-pg e cria o banco
.\banco\banco.ps1 estado     # ligado? quantas linhas?
.\banco\banco.ps1 desligar
```

É um PostgreSQL 16.6 + TimescaleDB 2.17.2 numa pasta (`C:\presenca-pg`; outra pasta: variável
`PRESENCA_PG`). Não tem instalador nem serviço do Windows e não precisa de administrador; só
ocupa memória enquanto está ligado. O schema (`banco\schema.sql`) é aplicado toda vez que liga:
cria o que falta e não apaga nada.

**Com Docker (alternativa):**

```powershell
docker compose up -d banco                 # só o banco
docker compose --profile tudo up -d        # banco + servidor em contêiner
```

Os dois jeitos usam a mesma porta (`55432`), usuário e senha (`presenca`/`presenca`): o
servidor não muda nada. Não ligue os dois ao mesmo tempo.

**Sem banco nenhum** (só para testar rápido): `python servidor.py --sem-banco` guarda em memória.

## 4. App do celular: gerar o APK a partir do código

```powershell
cd app ; npm install --legacy-peer-deps ; cd ..
powershell -ExecutionPolicy Bypass -File .\gerar-apk.ps1      # → marco-04\presenca-m4.apk
```

A primeira compilação leva de 15 a 30 min (o Gradle baixa dependências). A compilação nativa
quebra com espaço ou acento no caminho, então o script espelha o app em `C:\presenca-m4` e
compila lá. Gera só `arm64-v8a`, a arquitetura de praticamente todo celular atual.

Mande o APK para o celular (cabo, Drive, WhatsApp) e instale. O app aparece como
**Presença M4** e convive com as versões dos marcos anteriores. Na primeira abertura, permita
**Bluetooth (dispositivos próximos)**, **notificações**, **localização** e **câmera**:

- **Localização:** o Android exige essa permissão para manter o app ativo em segundo plano.
  A posição não é lida.
- **Câmera:** é só para a lanterna do atuador.

Para desenvolver sem gerar APK: `cd app ; npx expo start` (as partes nativas, como Bluetooth
e segundo plano, precisam do APK).

## 5. Âncoras

**anc-pc-1 — o notebook:** Bluetooth ligado e `cd ancora ; python ancora.py`. Deve aparecer
`rádio: TRANSMITINDO` e um token novo a cada 12 s.

**Extensão (fora do Marco 4) — anc-pc-2 numa ESP32 DOIT DevKit V1:** veja
[`esp32-ancora/LEIA-ME.md`](esp32-ancora/LEIA-ME.md); acrescente `"anc-pc-2": [3, 0]` em
`servidor/config.exemplo.json → sala.ancoras` e `'anc-pc-2'` em `SALAS` (`app/src/lib/config.ts`).
Em resumo: Wi-Fi em `segredos.json` → `python configurar.py` → abrir
`esp32-ancora\esp32-ancora.ino` no Arduino IDE, placa **DOIT ESP32 DEVKIT V1** → gravar.
Ligada numa tomada USB qualquer, ela pega a hora por NTP e começa a anunciar.

## 6. Subir tudo

```powershell
.\subir.ps1                # banco + janela do servidor + janela da âncora do notebook
.\subir.ps1 -SemAncora     # sem a âncora do notebook
.\subir.ps1 -Tls           # servidor pela porta 8883 em vez de 8084
.\desligar.ps1             # no fim: para servidor, âncora e simulados e desliga o banco
.\desligar.ps1 -FicaBanco  # para os programas e deixa o banco ligado
```

A janela do servidor deve mostrar `Conectado ao …emqxsl.com, porta 8084` e
`Gravando em: PostgreSQL/TimescaleDB`. Relatório: http://127.0.0.1:8090/

## 7. Usar

**Professor** (app → *Área do administrador*):

1. Criar a turma → **Publicar**. O app mostra o código e o QR da turma.
2. **Calibrar a 1 m** cada âncora: fique a 1 m dela por 8 s.
3. **Iniciar aula agora**. Na demonstração, a aula de 50 min dura 2 min.
4. **Relatório**: percentual de cada aluno, **Exportar lista da turma (CSV)**, e os botões
   **Vibrar / Chamar / Lanterna** por aluno.

**Aluno** (app → *Entrar numa turma*): ler o QR ou digitar o código, informar nome e matrícula
uma vez e ligar **Continuar contando com a tela apagada**.

**Sem celulares** (para ver o fluxo inteiro só com o PC):

```powershell
cd ataques
python celulares.py 2 --ws                  # 2 celulares simulados numa aula de 2 min
python celulares.py 1 --turma ABC234 --ws   # 1 simulado NA AULA que o professor iniciou no app
python celulares.py --limpar --ws   # se sobrar cadastro simulado no broker
```

## 8. Conferir

```powershell
cd servidor ; python -m pytest testes -q     # 81 passed (banco ligado; sem ele, os 5 de PostgreSQL são pulados)
cd ..\app ; npm test                          # 38 pass
```

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| servidor: "O broker RECUSOU a conexão" | senha errada em `segredos.json` |
| servidor parado sem "Conectado" | a rede bloqueia 8084/8883 → hotspot |
| servidor: "banco fora do ar" | rode `.\banco\banco.ps1`; o servidor continua e grava quando o banco voltar |
| `banco.ps1`: "o banco não ligou" | veja `C:\presenca-pg\banco.log`; porta 55432 ocupada (o Docker ligado?) |
| app: "Âncora não ouvida" | âncora transmitindo? Bluetooth e localização do celular ligados? |
| servidor recusa tudo com TOKEN VENCIDO | relógio do notebook errado: Configurações → Hora → Sincronizar agora |
| app para de mandar com a tela apagada | ligar **Continuar contando com a tela apagada** e tirar o app da economia de bateria do Android |
| `gerar-apk.ps1` com erro estranho | apague `C:\presenca-m4\android` e rode de novo |
