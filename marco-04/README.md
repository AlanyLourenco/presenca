# Marco 4 — Sistema completo

O Presença mede a **permanência** do estudante na sala (tempo acumulado ao longo da aula, não
presença num instante) com âncoras Bluetooth, o celular do aluno e um servidor. O Marco 3 deixou
o caminho seguro (TLS, senha por papel, toda mensagem assinada). O Marco 4 fecha o sistema:
**a âncora do notebook, o celular de verdade junto com celulares simulados, sensores do celular,
atuador, banco temporal, relatório para o professor, testes de falha e documentação para
reproduzir tudo do zero.**

> **Outros documentos:** instalação passo a passo em [`INSTALACAO.md`](INSTALACAO.md) ·
> como funciona por dentro em [`MANUAL-TECNICO.md`](MANUAL-TECNICO.md) ·
> roteiro do vídeo em [`GUIA.md`](GUIA.md) ·
> segurança (herdada do Marco 3) em [`../marco-03/README.md`](../marco-03/README.md).

```
  âncora anc-pc-1 (notebook) ─┐  Bluetooth: token HMAC a cada 12 s
                              ▼
  celular do aluno (app Presença M4) ── heartbeat v3 + sensor a cada 5 s, assinados ──┐
    · mede o sinal da âncora, lê acelerômetro e bateria                                │
    · roda em segundo plano, com a tela apagada                                        ▼
    · executa comandos (vibrar, chamar, lanterna) e confirma        broker EMQX Cloud (TLS + senha)
                                                                                       │
  celular do professor (mesmo app, área do administrador)                              ▼
    · publica a turma, calibra, inicia a aula                 servidor de permanência (Python)
    · vê o relatório, exporta CSV, manda comandos       ◄──── · decide PRESENTE / tolerância / FORA
                                                              · grava tudo no PostgreSQL + TimescaleDB
                                                              · API e página de relatório (porta 8090)
```

## O que o professor pediu, e onde está

Respostas do professor às perguntas do grupo, organizadas pelos seis eixos do Marco 4:

| Eixo | Pedido | Onde está | Situação |
|---|---|---|---|
| 1 · Fluxo completo | âncora → celular → broker → servidor → banco → relatório, de ponta a ponta | [§1](#1-fluxo-completo-e-integração) | feito e testado (celulares simulados pelo broker real; no vídeo, um celular de verdade junto com um simulado) |
| 1 · Fluxo completo | **2 âncoras**, testar com **2 celulares**, demo de **2 min** | [§1](#1-fluxo-completo-e-integração) | **1 âncora** (o notebook), por decisão do Marco 4: o sistema aceita várias (limiar por âncora, com teste) e o sketch da ESP32 está pronto como extensão. **2 celulares**: o de verdade + um simulado na mesma aula. Demo de 2 min: feito |
| 1 · Fluxo completo | **heartbeat a cada 5 s** | `INTERVALO_HEARTBEAT_MS = 5000` (app) · `intervalo_heartbeat_s: 5` (servidor) | feito |
| 2 · App móvel | app lê **pelo menos 1 sensor** do celular e o dado vai ao broker | [§2](#2-o-app-móvel-e-a-contribuição-dele) | acelerômetro + bateria, contrato `presenca.sensor.v1` |
| 2 · App móvel | **atuador** = operação enviada ao celular | [§2](#2-o-app-móvel-e-a-contribuição-dele) | vibrar, chamar ("Estou aqui"), lanterna; com confirmação assinada |
| 2 · App móvel | funcionar em **segundo plano**, tela apagada | [§2](#2-o-app-móvel-e-a-contribuição-dele) | serviço em primeiro plano do Android |
| 2 · App móvel | admin dentro do app | área do administrador | feito |
| 3 · Persistência | banco **temporal e normal — PostgreSQL**; guardar **todos** os eventos e comprimir | [§3](#3-persistência-eventos-e-dados-processados) | PostgreSQL 16 + TimescaleDB 2.17 |
| 3 · Persistência | **LGPD** | [§3](#lgpd) | nome à parte, pseudônimo nos eventos, direito de eliminação |
| 3 · Persistência | **API de consulta** ("é bom") | [§3](#api-de-consulta) | API HTTP + página de relatório |
| 3 · Persistência | **relatório de presença** para o professor, com exportação | [§3](#relatório-do-professor) | no app (CSV compartilhável) e no navegador |
| 4 · Arquitetura | mudanças desde o Marco 3 | [§4](#4-o-que-mudou-na-arquitetura-desde-o-marco-3) | — |
| 5 · Testes e falhas | testes **unitários e de funcionalidade**; tratamento de falhas e recuperação | [§5](#5-testes-falhas-e-recuperação) | 81 testes no servidor, 38 no app, teste ao vivo de falhas |
| 6 · Documentação | **instalação + manual técnico**; gerar o app a partir do código | [`INSTALACAO.md`](INSTALACAO.md) · [`MANUAL-TECNICO.md`](MANUAL-TECNICO.md) | feito |
| 6 · Documentação | **Docker** ("é bom") | [`docker-compose.yml`](docker-compose.yml) | opcional: há também o banco portátil, sem Docker |
| — | credenciais para o professor testar | usuário próprio no broker, enviado pelo e-mail institucional | — |

---

## 1. Fluxo completo e integração

Uma aula, do começo ao fim:

1. O **professor** abre a área do administrador no app, publica a turma (assinada com a chave dele),
   calibra cada âncora a 1 m e toca em **Iniciar aula agora**. Na demonstração, a aula de 50 min
   dura **2 min** (escala 25: 1 s da demo = 25 s de aula).
2. Cada **âncora** anuncia por Bluetooth um token que muda a cada 12 s (HMAC do segredo dela com a
   janela de tempo). Ela só transmite: nunca escuta nem conhece aparelho nenhum.
3. O **celular do aluno** ouve as âncoras, decide se está perto de alguma (limiar calibrado por
   âncora) e, a cada **5 s**, publica um **heartbeat v3** com o RSSI e o token de cada âncora, mais
   um **sensor** (movimento do acelerômetro e bateria). Tudo assinado com a chave Ed25519 do celular.
4. O **servidor** confere assinatura, contrato e token; calcula a permanência **retroativamente
   sobre o log** (nunca soma ao vivo); manda ao celular o estado e os avisos (assinados);
   grava cada mensagem, aceita ou recusada, no banco.
5. O **relatório** da turma é refeito a cada 5 s, publicado retido no broker (o app do professor
   lê) e servido em `http://127.0.0.1:8090/`.

**Uma âncora: o notebook.** No Marco 4 a sala tem uma âncora, `anc-pc-1`
([`ancora/ancora.py`](ancora/ancora.py)). Com menos de 3 âncoras não há trilateração: vale a região
decidida no celular, com o limiar calibrado a 1 m. O sistema já aceita mais âncoras, cada uma com
o seu limiar ("dentro se perto de **qualquer** uma", com teste). A mesma âncora numa placa ESP32
está pronta em [`esp32-ancora/`](esp32-ancora/) como extensão: para usar, basta acrescentar
`anc-pc-2` na sala do servidor e do app.

**Celulares simulados:** [`ataques/celulares.py`](ataques/celulares.py) simula N celulares,
cada um com a própria chave, pelo broker de verdade, com um roteiro (um fica, um sai e volta com
o celular parado, um sai e não volta). Com `--turma <código>`, ele entra **na mesma aula** que o
professor iniciou no app (lê a turma retida no broker): assim o celular de verdade e um simulado
formam os dois celulares da demonstração e aparecem juntos no relatório.

## 2. O app móvel e a contribuição dele

App **Presença M4** (React Native/Expo, Android), em [`app/`](app/). O celular não é só um
"leitor": ele é o sensor principal do sistema.

| O que o celular faz | Como |
|---|---|
| mede o sinal da âncora e decide "perto / longe" | Bluetooth (BLE), limiar calibrado a 1 m (um por âncora, se houver mais) |
| **lê sensores** e manda ao broker | acelerômetro (variância do movimento: o celular ficou parado a aula toda?) e bateria (nível, carregando) → `presenca.sensor.v1` a cada 5 s |
| **atua** quando o professor manda | `presenca.comando.v1`: **vibrar**, **chamar** (notificação com "Estou aqui"), **lanterna** (pisca 6 vezes). Responde com `presenca.comando.ack.v1` assinado: *executado*, *respondido*, *recusado* ou *vencido* |
| roda em **segundo plano**, com a tela apagada | serviço em primeiro plano do Android, que mantém o relógio do heartbeat. Ele usa o serviço de localização só porque o Android exige isso para um serviço desse tipo; **a localização é descartada** (GPS foi rejeitado no projeto). Com o app em segundo plano, a busca Bluetooth usa filtro do fabricante (`0xFFFF` + `PRS1`), que o Android permite |
| guarda o que não conseguiu enviar | fila local de 72 heartbeats (6 min) reenviada quando a rede volta, marcada `bufferizado` |
| informa nome e matrícula **uma vez** | `presenca.cadastro.v1`, publicado **retido** no broker: chega ao servidor mesmo se ele estiver fora do ar na hora |
| (professor) relatório e comandos | tela de relatório com exportação **CSV** (compartilhar por WhatsApp, e-mail, Drive) e botões Vibrar / Chamar / Lanterna por aluno, com o retorno de cada um |

Por que o acelerômetro: empréstimo de aparelho (um colega leva o celular de quem faltou) é um
limite conhecido do projeto. Um celular **parado a aula inteira** é um sinal para o professor
revisar. O relatório marca "celular parado", sem punir sozinho.

## 3. Persistência: eventos e dados processados

**PostgreSQL 16 + TimescaleDB 2.17**, um banco só com as duas naturezas que o professor pediu
([`banco/schema.sql`](banco/schema.sql)):

| Tipo | Tabelas | Para quê |
|---|---|---|
| **temporal** (hypertables) | `eventos` (todo heartbeat, cru, com a classificação do servidor) · `sensores` · `recusas` | auditoria completa; recalcular uma aula a partir do log |
| **normal** (relacional) | `alunos` (pseudônimo + chave pública) · `identificacao` (nome e matrícula) · `sessoes` (a aula de um aluno: resultado e estado) · `comandos` (o que o atuador mandou e a confirmação) | relatório, recuperação, LGPD |

- **Todos os eventos ficam**, inclusive duplicados e recusados (com a classificação).
- **Compressão:** depois de 7 dias, os pedaços de `eventos` e `sensores` são comprimidos,
  agrupados por aluno (`segmentby = aluno`): heartbeats do mesmo aluno são muito parecidos e
  comprimem bem.
- **Retenção:** 180 dias (um semestre e pouco), depois disso o TimescaleDB apaga sozinho.
- **Fila de gravação:** o servidor grava numa thread própria. Se o banco cai ou trava, as
  gravações esperam em memória e entram na ordem quando ele volta; a presença continua sendo
  decidida o tempo todo.
- **Sem Docker:** [`banco/banco.ps1`](banco/banco.ps1) liga um PostgreSQL portátil (uma pasta,
  sem instalador, ~40 MB de RAM). Com Docker: `docker compose up -d banco`. Os dois usam a
  mesma porta (55432).

### LGPD

| Princípio | Como |
|---|---|
| minimização | os eventos guardam só o **pseudônimo** (`tok-` + hash da chave pública); nunca MAC, IMEI ou localização |
| separação | nome e matrícula ficam na tabela `identificacao`, à parte do histórico |
| direito de eliminação (art. 18, VI) | `DELETE /api/alunos/<aluno>` apaga tudo daquele pseudônimo (eventos, sensores, sessões, comandos, identificação) **e** o cadastro retido no broker |
| retenção limitada | 180 dias |
| segurança | TLS, senha por papel, toda mensagem assinada (Marco 3); o banco só escuta em `localhost` |

### API de consulta

[`servidor/api.py`](servidor/api.py), em `http://127.0.0.1:8090`:

| Método e caminho | Devolve |
|---|---|
| `GET /` | página do relatório (atualiza a cada 5 s) |
| `GET /api/saude` | banco online?, fila de gravação, broker conectado, aulas abertas, celulares em silêncio, âncoras mudas |
| `GET /api/turmas/<TURMA>/relatorio` | relatório da turma (`presenca.relatorio.v1`) |
| `GET /api/turmas/<TURMA>/relatorio.csv` | o mesmo em CSV (abre direto no Excel em português) |
| `GET /api/alunos/<aluno>/historico` | as aulas daquele aluno |
| `POST /api/alunos/<aluno>/comando` `{"tipo": "vibrar"\|"chamar"\|"lanterna"}` | manda o atuador; devolve o `comandoId` |
| `DELETE /api/alunos/<aluno>` | eliminação (LGPD) |

### Relatório do professor

Por aula e por aluno: nome, matrícula, situação, percentual, resultado (presente / falta / em
andamento), tempo dentro, saídas perdoadas, número de mensagens, **celular parado** e última
bateria. No app (tela Relatório, com **Exportar lista da turma (CSV)**) e no navegador.

## 4. O que mudou na arquitetura desde o Marco 3

| Antes (Marco 3) | Agora (Marco 4) | Por quê |
|---|---|---|
| 1 âncora, limiar único | 1 âncora (notebook), mas a turma leva **um limiar por âncora** e a regra aceita várias; sketch da ESP32 pronto | preparar a sala para mais âncoras sem mudar o protocolo |
| heartbeat a cada 0,5 s, só com a tela ligada | **5 s**, também em segundo plano | pedido do professor; bateria |
| heartbeat v2 | **v3**: traz turma e `aulaId` (aula nova = sessão nova) | relatório por turma e por aula |
| log em arquivo | **PostgreSQL + TimescaleDB**, com fila de gravação | persistência pedida; aguentar banco fora |
| estado só em memória | aula **recuperada do banco** quando o servidor reinicia | o acumulador é derivado do log: recuperar = reler o log |
| atuação = aviso/vibração automáticos | + **comandos do professor** (vibrar, chamar, lanterna) com **confirmação assinada** | pedido do professor (atuador) |
| — | sensores do celular (acelerômetro, bateria) | pedido do professor |
| — | silêncio do celular: o servidor diz se é **provável bateria** (última leitura ≤ 5 % e sem carregar) | distinguir bateria de saída sem adivinhar pelo sinal |
| — | **âncora muda**: os celulares falam, mas ninguém ouve a âncora há 15 s | âncora desligada ou sem energia |
| — | cadastro (nome) e relatório (retidos no broker), API HTTP | relatório para o professor |
| tolerância de tokens só ao vivo | heartbeat **bufferizado** aceita token de até 6 min atrás (= fila do app) | não recusar o que ficou preso sem rede |

## 5. Testes, falhas e recuperação

```powershell
cd servidor ; python -m pytest testes -q     # 81 passed (com o banco ligado; sem ele, os de PostgreSQL são pulados)
cd ..\app ; npm test                          # 38 pass
```

**Unitários:** regra de permanência, contratos (JSON Schema), assinatura, token,
relatório, CSV, sensores, comandos, turma.
**De funcionalidade:** aula inteira com 2 alunos; aula nova = sessão nova; reinício do
servidor no meio da aula (o resultado é **igual** ao de não ter reiniciado); repetida continua
repetida depois de reiniciar; aviso não é reenviado; comando assinado, confirmação e
confirmação forjada recusada; cadastro em nome de outro recusado; eliminação LGPD; e, contra
o PostgreSQL de verdade, grava/recupera/apaga, banco fora (fila), banco travado (a gravação
não atrasa as mensagens) e leitura travada (desiste em 3 s).

**Teste ao vivo de falhas**, pelo broker real, com 2 celulares simulados numa aula de 2 min:

| Falha provocada | O que o sistema fez |
|---|---|
| servidor morto aos 35 s, religado aos 47 s | `↺ RECUPERADA … mensagens relidas do banco`; a aula continuou de onde estava; os nomes voltaram pelos cadastros retidos |
| banco **congelado** por 20 s ([`ataques/travar_banco.py`](ataques/travar_banco.py)) | gravações na fila, nenhuma mensagem recusada, nenhum alarme falso; tudo gravado quando ele voltou |
| celular que para de mandar | `SILÊNCIO` depois de 15 s ("provável BATERIA" se a última leitura era ≤ 5 %); nada é decidido sem mensagem |
| âncora desligada | `ÂNCORA MUDA` |
| sem rede no celular | fila local de 6 min, reenviada e aceita como `bufferizado` |
| ataques (Marco 3) | [`ataques/ataques.py`](ataques/ataques.py): sem senha, sem assinatura, identidade trocada, token vencido, repetição, estado e turma falsos — todos recusados |

Dois defeitos foram **achados pelo teste ao vivo** e corrigidos (com teste novo para cada um):
com o banco travado, (1) a gravação e (2) a montagem do relatório seguravam o processamento,
as mensagens chegavam atrasadas e o token vencia. Agora a gravação tem thread própria e
nenhuma leitura do banco é feita segurando a trava do servidor.

## 6. Documentação e reprodução

- [`INSTALACAO.md`](INSTALACAO.md): do computador vazio até a aula rodando, incluindo
  **gerar o APK a partir do código**.
- [`MANUAL-TECNICO.md`](MANUAL-TECNICO.md): componentes, contratos, tópicos, banco, regra de
  permanência, segurança, falhas.
- [`contrato/v1/`](contrato/v1/): JSON Schema de cada mensagem.

## Estrutura

```
marco-04/
├── subir.ps1        liga banco + servidor + âncora (sem Docker)
├── desligar.ps1     desliga tudo o que o subir.ps1 ligou
├── banco/           schema.sql (PostgreSQL + TimescaleDB) · banco.ps1 (banco portátil)
├── servidor/        servidor.py · permanencia.py · seguranca.py · banco.py · api.py · relatorio.py · testes/
├── ancora/          ancora.py (âncora anc-pc-1 no notebook) · escutar.py (medição)
├── esp32-ancora/    extensão: a mesma âncora numa ESP32 (anc-pc-2), fora da demo do Marco 4
├── app/             app "Presença M4" (React Native/Expo)
├── contrato/v1/     JSON Schemas de todas as mensagens
├── ataques/         celulares.py (celulares simulados) · travar_banco.py · ataques.py · carga.py
├── medicoes/        distância × RSSI
├── docker-compose.yml   alternativa com Docker (banco; servidor com --profile tudo)
├── configurar.py    gera os segredos locais
└── gerar-apk.ps1    gera o APK
```

## Limites declarados

- **ACL por tópico** no broker ainda não está ligada: a senha do app está no APK; quem a extrai
  publica mensagens (recusadas pela assinatura) e lê pseudônimos.
- **Relay** do token (alguém na sala retransmitindo ao vivo para quem está em casa) continua
  possível; é um limite aceito do projeto.
- A chave do celular fica no armazenamento seguro do Android (cifrado pelo Keystore), **não
  dentro do chip**: um celular com root a extrai.
- Empréstimo de aparelho é **mitigado** (celular parado no relatório), não resolvido.
- Uma âncora só: não há trilateração (a pertinência ao polígono só vale com 3 ou mais) e, se o
  notebook desligar, ninguém é contado (o servidor avisa `ÂNCORA MUDA`).
- O servidor e a âncora do notebook precisam de relógio certo.
