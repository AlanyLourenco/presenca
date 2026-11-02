# Presença — aplicativo do celular

O celular do estudante substitui o ESP32 que fazia esse papel no Marco 2. O app fala
exatamente o mesmo protocolo (`presenca.heartbeat.v1` → servidor → `presenca.estado.v1` e
`presenca.aviso.v1`), então o servidor de `marco-02/servidor/` atende o celular sem mudar
nada no contrato. O mesmo app tem a **área do administrador**, que cria as turmas e define
os horários das aulas.

Feito em Expo (SDK 57) para rodar no **Expo Go**, sem instalar nada além dele no celular.

## Rodar no celular

1. Instale o **Expo Go** no celular (Play Store / App Store).
2. No computador:

   ```bash
   cd app
   npm install
   npx expo start
   ```

3. Leia o QR que aparece no terminal: no Android, pelo próprio Expo Go; no iPhone, pela câmera.
   Celular e computador precisam estar **na mesma rede Wi-Fi**. Se a rede não deixar (a da
   faculdade costuma bloquear), use `npx expo start --tunnel`.

4. Em outro terminal, o servidor (WebSocket, porque o celular fala por WebSocket seguro):

   ```bash
   cd marco-02/servidor
   python servidor.py --ws
   ```

## O roteiro de uso

**Administrador** (`Área do administrador` na tela inicial):

1. Na primeira vez, cria um PIN. Ele fica só neste celular, guardado como hash.
2. `Nova turma` → nome, sala, horários (dia da semana, início, fim).
3. `Publicar para os estudantes`. A tela mostra o **código** e o **QR**.
4. `Iniciar aula agora` começa uma aula de demonstração de 100 s, fora da grade
   (a aula de 50 min no tempo comprimido do servidor).

**Estudante:**

1. `Entrar numa turma` → digita o código ou `Ler o QR da turma`. Uma vez por semestre.
2. Abre a turma. Fora do horário, a tela mostra a próxima aula. No horário (ou durante a
   aula de demonstração), o app passa a mandar heartbeat sozinho e mostra o que o
   servidor decidiu: na sala, usando a tolerância ou fora, a porcentagem e a tolerância
   restante.
3. Os avisos de 10 min, 13 min, limite esgotado e fim da aula chegam como notificação e
   vibração.

## Onde está cada coisa

| Arquivo | O que faz |
|---|---|
| `src/lib/aparelho.ts` | A lógica do ESP32 portada: média móvel, âncora não ouvida, histerese −70/−85, heartbeat, fila sem rede, anomalias |
| `src/lib/usar-aparelho.ts` | O `loop()`: amostra a cada 100 ms, heartbeat a cada 500 ms durante a aula, escuta estado e aviso |
| `src/lib/turma.ts` | Código da turma, QR, grade de horários, "tem aula agora?" |
| `src/lib/rede-turma.ts` | Turma publicada como mensagem retida (`presenca.turma.v1`) |
| `src/lib/mqtt.ts` | Conexão MQTT sobre WebSocket seguro (paho-mqtt, JavaScript puro) |
| `src/lib/db.ts` | Banco local SQLite: turmas, avisos já mostrados, resultado de cada aula |
| `src/lib/identidade.ts` | Chave do aparelho no armazenamento seguro, pseudônimo `tok-…`, PIN do admin |
| `src/app/` | As telas (Expo Router): início, entrar, ler QR, aula, admin |

Testes da lógica pura: `npm test`. Typecheck: `npm run typecheck`.

## O que o Expo Go não deixa fazer — e como ficou

| Projeto | No Expo Go | Para o app instalado (build de desenvolvimento) |
|---|---|---|
| Medir o RSSI das âncoras por Bluetooth | **Não há Bluetooth no Expo Go.** Três controles deslizantes fazem o papel dos potenciômetros, com as mesmas posições (dentro, corredor, fora) | `react-native-ble-plx` lendo o anúncio das âncoras |
| Par de chaves no cofre de hardware | Chave aleatória de 32 bytes no `expo-secure-store` (cifrado pelo Keystore/Keychain); o pseudônimo é o hash dela | Chave gerada no Keystore / Secure Enclave e heartbeat assinado |
| Heartbeat com o app em segundo plano | O JavaScript pausa: a tela fica acesa durante a aula. Fechar o app gera **SILÊNCIO** no servidor, como no projeto (`app_morto`) | Tarefa em segundo plano / monitoramento de região |
| Notificação push | Notificação **local**, disparada quando o aviso chega pela conexão aberta | Push |

## Limites desta versão

- O servidor usa os tempos comprimidos (`escala` 30): uma aula dura 100 s nele. Para uma aula
  da grade em tempo real, o servidor precisa de `escala` 1.
- A grade de horários chega ao celular do estudante; o servidor ainda não a lê. Ele abre a
  sessão no primeiro heartbeat de cada aluno.
- O broker é público: a turma publicada não leva nome de aluno, e o servidor só vê o
  pseudônimo. Ligar pseudônimo e matrícula fica para o painel do professor.
