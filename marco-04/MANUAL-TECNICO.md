# Manual técnico — Presença, Marco 4

Para quem vai manter, estender ou auditar o sistema. Como instalar: [`INSTALACAO.md`](INSTALACAO.md).
Visão geral e entrega: [`README.md`](README.md).

## 1. Componentes

| Componente | Onde | Linguagem | Papel |
|---|---|---|---|
| Âncora anc-pc-1 | `ancora/ancora.py` | Python (WinRT Bluetooth) | farol BLE no notebook |
| (extensão) anc-pc-2 | `esp32-ancora/esp32-ancora.ino` | C++ (Arduino, ESP32) | o mesmo farol numa placa de tomada; fora da sala do Marco 4 |
| App | `app/` | TypeScript (React Native / Expo SDK 57) | aluno: mede, sente, atua; professor: turma, calibração, relatório, comandos |
| Broker | EMQX Cloud Serverless | — | MQTT com TLS (8883) e WebSocket com TLS (8084), senha por papel |
| Servidor | `servidor/` | Python 3.10+ | confere, decide a permanência, grava, publica relatório, API |
| Banco | `banco/schema.sql` | PostgreSQL 16 + TimescaleDB 2.17 | eventos temporais + dados relacionais |
| Contratos | `contrato/v1/*.schema.json` | JSON Schema 2020-12 | formato de cada mensagem |

### Módulos do servidor

| Arquivo | Responsabilidade |
|---|---|
| `permanencia.py` | **regra pura** (sem rede, sem relógio): classificação de cada heartbeat e máquina de estados, refeita sobre o log inteiro a cada mensagem |
| `seguranca.py` | envelope assinado (Ed25519), token da âncora (HMAC), identidade a partir da chave |
| `servidor.py` | MQTT, validação, sessões, avisos, comandos, vigia (silêncio, âncora muda), recuperação, painel no terminal |
| `banco.py` | `Banco` (PostgreSQL, fila de gravação, leitura com tempo limite) e `BancoMemoria` (mesma interface, testes e `--sem-banco`) |
| `relatorio.py` | monta `presenca.relatorio.v1` e o CSV, funções puras |
| `api.py` | HTTP em `127.0.0.1:8090` |

### Módulos do app (`app/src/lib`)

| Arquivo | Responsabilidade |
|---|---|
| `ble.ts`, `usar-ancora.ts` | busca BLE (com filtro do fabricante em segundo plano), leitura e calibração por âncora |
| `aparelho.ts` | medidor de RSSI multiâncora (média móvel + histerese), montagem do heartbeat v3, fila sem rede |
| `usar-aparelho.ts` | o relógio de 5 s (`bater()`): heartbeat + sensor, chamado pela tela **e** pela tarefa de segundo plano |
| `segundo-plano.ts` | tarefa `presenca-batida-em-segundo-plano` (serviço em primeiro plano do Android) |
| `sensores.ts`, `usar-sensores.ts` | acelerômetro (variância a 10 Hz) e bateria → `presenca.sensor.v1` |
| `comandos.ts`, `usar-comandos.ts` | confere o comando, executa (vibrar, notificação, lanterna) e confirma |
| `relatorio.ts` | abre e confere o relatório, gera o CSV |
| `assinatura.ts`, `identidade.ts` | chave Ed25519 do aparelho (armazenamento seguro) e envelope |
| `turma.ts`, `rede-turma.ts`, `db.ts` | turma assinada pelo professor, grade, SQLite local |

## 2. Tópicos MQTT

Base: `ufg/ssu/presenca/alany/m4`. `<sala>` = `sala-pc`.

| Tópico | Quem publica → quem lê | Contrato | QoS / retido |
|---|---|---|---|
| `<base>/<sala>/heartbeat` | celular → servidor | `presenca.heartbeat.v3` | 0 |
| `<base>/<sala>/sensor` | celular → servidor | `presenca.sensor.v1` | 0 |
| `<base>/<sala>/estado/<aluno>` | servidor → celular | `presenca.estado.v1` | 1 |
| `<base>/<sala>/aviso/<aluno>` | servidor → celular | `presenca.aviso.v1` | 1 |
| `<base>/<sala>/comando/<aluno>` | servidor ou professor → celular | `presenca.comando.v1` | 1 |
| `<base>/<sala>/comando-ack/<aluno>` | celular → servidor e professor | `presenca.comando.ack.v1` | 1 |
| `<base>/cadastro/<aluno>` | celular → servidor | `presenca.cadastro.v1` | 1, **retido** |
| `<base>/relatorio/<turma>` | servidor → app do professor | `presenca.relatorio.v1` | 1, **retido** |
| `<base>/turma/<codigo>` | professor → celulares | `presenca.turma.v1` | 1, **retido** |

Toda carga vai dentro de um `seguranca.envelope.v1` (§5). O tópico entra na assinatura: uma
mensagem copiada para outro tópico não confere.

## 3. Contratos (`contrato/v1`)

| Contrato | Campos principais |
|---|---|
| `presenca.heartbeat.v3` | `eventId` (`device#boot#seq`), `aluno`, `turma`, `aulaId`, `bootId`, `sequence`, `eventTimeMs`, `state` (`DENTRO_ALCANCE`/`FORA_ALCANCE`), `ancoras[] {id, rssi, token}`, `bufferizado` |
| `presenca.sensor.v1` | `sensorId`, `aluno`, `turma`, `acelerometro {movimento, amostras, parado}`, `bateria {nivel 0–1, carregando}` |
| `presenca.comando.v1` | `comandoId`, `aluno`, `turma`, `tipo` (`vibrar`\|`chamar`\|`lanterna`), `texto`, `emitidoEmMs`, `validadeS` (5–600) |
| `presenca.comando.ack.v1` | `comandoId`, `aluno`, `resultado` (`executado`\|`respondido`\|`recusado`\|`vencido`), `emMs`, `detalhe` |
| `presenca.cadastro.v1` | `aluno`, `turma`, `nome`, `matricula`, `emMs` |
| `presenca.relatorio.v1` | `turma`, `geradoEmMs`, `aulas[] {aulaId, inicioMs, emAndamento, alunos[] {aluno, nome, matricula, estado, percentual, aprovado, dentroS, perdoadoS, mensagens, celularParado, bateria, ultimoContatoMs}}` |
| `presenca.turma.v1` | grade, sala, âncoras, `limiares` por âncora (calibração), aula de demonstração |

O servidor aceita heartbeat **v2** (Marco 3) e **v3**. Os exemplos em `contrato/v1/exemplos`
são validados pelos testes.

## 4. Regra de permanência

Parâmetros em valores **reais**, divididos por `escala` (padrão 25: aula de 50 min = 120 s):

| Parâmetro | Valor real | Na demo (÷25) |
|---|---|---|
| persistência para entrar/sair | 30 s | 1,2 s |
| orçamento de ausência por sessão | 15 min | 36 s |
| avisos | 10 e 13 min fora | 24 s e 31 s |
| requalificação no retorno | `min(30 min, restante)` | — |
| duração da aula | 50 min | 120 s |
| presença mínima | 75 % | 75 % |

Estados: `FORA` · `PRESENTE` · `AUSENCIA_TOLERADA`. A cada heartbeat aceito, o servidor
**refaz a linha do tempo inteira** a partir do log da sessão (`permanencia.py`). Duplicado,
atrasado ou fora de ordem entra na posição certa e o resultado é o mesmo; por isso recuperar
depois de reiniciar é só reler os eventos do banco.

**Dentro ou fora**, com menos de 3 âncoras: vale a região decidida no celular. O celular faz a
média móvel do RSSI de cada âncora (5 amostras) e compara com o limiar **daquela âncora**,
calibrado a 1 m: **dentro** se qualquer âncora está acima do seu limiar; **fora** se todas as
ouvidas estão 5 dB abaixo (ou nenhuma é ouvida); entre os dois, mantém a anterior. Sem
calibração nenhuma, a região é indeterminada e o servidor trata como neutra. Com 3 ou mais, o
servidor faz trilateração e testa se o ponto está no polígono da sala (`sala.poligono`).

**Sessão** = (aluno, `aulaId`). Um `aulaId` novo abre sessão nova.

## 5. Segurança (herdada do Marco 3)

| Camada | Como |
|---|---|
| canal | TLS obrigatório (8883 ou 8084/WSS); o broker não atende sem TLS |
| quem conecta | usuário e senha por papel no EMQX (`presenca-servidor`, `presenca-app`) |
| quem escreveu | `seguranca.envelope.v1`: carga + tópico + `de` + chave pública, assinados com **Ed25519**. O aluno é `tok-` + 8 hex do SHA-256 da chave: ninguém assina em nome de outro |
| esteve na sala agora | token da âncora = 4 bytes de `HMAC-SHA256(segredo, "<âncora>\|<janela de 12 s>")`. Ao vivo aceita a janela anterior, a atual e a seguinte; heartbeat `bufferizado` aceita até **31 janelas atrás** (6,2 min, a fila do app é 6 min) |
| quem manda no celular | o app só executa estado, aviso e comando assinados pela chave do **servidor** (embutida no APK) ou do **professor** (vinda na turma); comando tem validade e não repete |
| repetição | `eventId` já visto na sessão = `REPETIDA`, gravada mas não conta |

Recusas (`SEM ASSINATURA`, `ASSINATURA FALSA`, `ENVELOPE MALFORMADO`, `IDENTIDADE TROCADA`,
`TOKEN VENCIDO`, `ÂNCORA DESCONHECIDA`, `FORA DO CONTRATO`) vão para a tabela `recusas`.

## 6. Banco de dados

Esquema em `banco/schema.sql`, idempotente (pode rodar de novo; só cria o que falta).

| Tabela | Tipo | Chave / partição | Conteúdo |
|---|---|---|---|
| `eventos` | hypertable | `recebido_em` | todo heartbeat (cru em `carga jsonb`) + classificação, `t_linha`, estado derivado |
| `sensores` | hypertable | `recebido_em` | movimento, parado, bateria, carregando |
| `recusas` | hypertable | `recebido_em` | tópico, motivo, detalhe |
| `alunos` | normal | `aluno` | chave pública, device, primeira/última vez visto |
| `identificacao` | normal | (`aluno`, `turma`) | nome, matrícula — dado pessoal, à parte |
| `sessoes` | normal | `id` | turma, `aula_id`, estado, acumulado, percentual, aprovado, avisos enviados, contagem |
| `comandos` | normal | `comando_id` | tipo, texto, de quem, confirmação e resultado |

Compressão (`segmentby = aluno`, `orderby = recebido_em`) depois de 7 dias em `eventos` e
`sensores`; retenção de 180 dias nas três hypertables.

### Gravação e leitura no servidor

- **Gravação:** quem processa a mensagem só **enfileira** (`_gravar`) e segue. Uma thread
  própria (`banco-escritor`) esvazia a fila com uma conexão só dela. Banco fora: as gravações
  esperam (até 50 000) e entram na ordem quando ele volta; reconexão a cada 5 s.
- **Leitura:** cada consulta roda numa thread com **tempo limite de 3 s**. Banco travado: a
  leitura devolve "banco fora" e a conexão presa é abandonada.
- **Travas:** `srv.trava` protege o estado das sessões; **nenhuma leitura do banco é feita
  segurando ela** (relatório, API, eliminação). `banco.trava_fila` protege só a fila.
- **Recuperação:** ao ligar, `sessoes_abertas(3 h)` + `eventos_da_sessao` → `reconstruir()`
  refaz cada sessão com o mesmo log (inclusive os `eventId` já vistos e os avisos já mandados).

Conexão: `PRESENCA_DSN` ou `config.json → banco.dsn`
(padrão `postgresql://presenca:presenca@localhost:55432/presenca`).

## 7. Vigia e falhas

O vigia roda a cada 1 s:

| Situação | Detecção | Saída |
|---|---|---|
| celular em silêncio | nada dele há `silencio_s` (15 s) com aula aberta | `… SILÊNCIO`; "provável BATERIA" se a última leitura era ≤ `bateria_baixa` (5 %) e sem carregar. Nada é decidido sem mensagem |
| âncora muda | há celulares falando, mas ninguém a ouve há 15 s | `! ÂNCORA MUDA` |
| banco | fila com pendências | acorda o escritor |
| relatório | turma com novidade | republica `relatorio/<turma>` (retido, assinado) a cada 5 s, **fora** da trava |

| Falha | Comportamento | Teste |
|---|---|---|
| servidor reinicia | sessão recuperada do banco, resultado igual | `test_servidor_reiniciado_recupera_a_aula_e_continua_igual` |
| banco cai | fila em memória | `test_pg_banco_fora_guarda_na_fila_e_grava_quando_volta` |
| banco trava (gravação) | processamento não espera | `test_pg_banco_travado_nao_atrasa_as_mensagens` |
| banco trava (leitura) | desiste em 3 s | `test_pg_leitura_travada_desiste_no_tempo_limite`, `test_pg_relatorio_lento_nao_segura_as_mensagens` |
| servidor fora quando o aluno se cadastra | cadastro retido reentregue | `test_cadastro_retido_reentregue_nao_conta_como_sinal_de_vida` |
| celular sem rede | fila de 72 heartbeats, reenviados `bufferizado` | testes do app (`aparelho.test.ts`) |

Ferramentas: `ataques/travar_banco.py` (congela o PostgreSQL), `ataques/celulares.py`
(N celulares simulados), `ataques/ataques.py` (ataques do Marco 3), `ataques/carga.py` (carga).

## 8. API HTTP

Ver a tabela em [`README.md` §3](README.md#api-de-consulta). Só escuta em `127.0.0.1`
(`config.json → api.host`). Respostas em JSON; o CSV usa `;` e vírgula decimal (Excel em
português) e começa com BOM.

## 9. Configuração (`servidor/config.exemplo.json`)

| Chave | Padrão | Significado |
|---|---|---|
| `transporte` | `websockets` | `websockets` (8084) ou `tls` (8883); `--ws`/`--tls` na linha de comando |
| `topico_*` | `ufg/ssu/presenca/alany/m4/…` | tópicos (§2) |
| `intervalo_heartbeat_s` | 5 | o que o servidor espera do celular |
| `parametros.escala` | 25 | compressão do tempo da demo |
| `sala.ancoras` | anc-pc-1 [0,0] | âncoras da sala e posição (m) para a trilateração; a ESP32 entra como `"anc-pc-2": [3, 0]` |
| `sala.poligono` | retângulo −1…4 × −1…1 | planta da sala |
| `banco.dsn` | localhost:55432 | conexão |
| `api` | ligada, 127.0.0.1:8090 | API e página |
| `recuperar_horas` | 3 | até quanto tempo atrás uma sessão aberta é recuperada |
| `silencio_s`, `bateria_baixa` | 15, 0,05 | vigia |
| `relatorio_a_cada_s` | 5 | republicação do relatório |

Teclas do servidor (com Enter): `p` resumo · `r` relatório · `c <aluno|todos> <vibrar|chamar|lanterna> [texto]`
· `b` banco · `n` aula nova · `q` sair. Opções: `--sem-banco`, `--quieto`, `--ws`, `--tls`.

## 10. Segredos

Gerados por `configurar.py`, **fora do git**: `segredos.json` (broker, senhas, segredo de cada
âncora, Wi-Fi da ESP32), `servidor/chave-servidor.pem` (chave privada Ed25519 do servidor),
`app/src/lib/segredos.ts` (broker, senha do papel app, chave **pública** do servidor),
`esp32-ancora/segredos.h`. Trocar o segredo de uma âncora exige regravar a ESP32 (ou reiniciar
`ancora.py`) e reiniciar o servidor.

## 11. Testes

| Onde | Quantos | Cobre |
|---|---|---|
| `servidor/testes/test_permanencia.py` | 24 | regra de permanência pura (estados, orçamento, avisos, atraso, fora de ordem) |
| `servidor/testes/test_servidor.py` | 24 | servidor com a segurança do Marco 3: assinatura, identidade, token, repetição, janela do token (ao vivo e da fila de 6 min), ataques |
| `servidor/testes/test_uma_ancora.py` | 3 | sala com uma âncora |
| `servidor/testes/test_marco4.py` | 30 | contratos v3/sensor/comando/cadastro/relatório, sessões por aula, persistência, recuperação, sensores, atuador, relatório e CSV, duas âncoras, LGPD, PostgreSQL real (5, pulados sem banco) |
| total do servidor | **81** | `cd servidor ; python -m pytest testes -q` |
| `app/src/lib/*.test.ts` | **38** | medidor BLE, assinatura, turma, sensores, comandos, relatório, fila sem rede — `cd app ; npm test` |
