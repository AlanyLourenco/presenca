"""Figuras anotadas do guia. Coordenadas no frame original de cada captura."""

from anotacoes import arvore, codigo

F = {}

# ===========================================================================
# VS CODE - PASTAS
# ===========================================================================
F["vs-raiz"] = arvore(
    "vs-v00.jpg", (56, 70, 360, 275),
    [(1, 106, 1, ".impeccable"), (2, 128, 1, "docs"), (3, 150, 1, "marco-02"),
     (4, 172, 1, ".gitignore"), (5, 194, 1, "atividade-01.md"), (6, 216, 1, "atividade-02.md"),
     (7, 238, 1, "CLAUDE.md"), (8, 260, 1, "README.md")],
    [(1, ".impeccable/", "Configuração da ferramenta de revisão de design usada na apresentação. Não faz parte do sistema; pode ignorar."),
     (2, "docs/", "Tem o <code>projeto-tecnico.md</code>, a especificação completa (o nosso SDD): parâmetros, protocolo, máquina de estados, alternativas rejeitadas. É de lá que saíram todos os números do Marco 2."),
     (3, "marco-02/", "<strong>Tudo o que você vai apresentar.</strong> As próximas figuras abrem esta pasta."),
     (4, ".gitignore", "Lista o que o Git não guarda (logs, configurações locais, cache do Python)."),
     (5, "atividade-01.md", "Entrega da Atividade 01: a análise do problema."),
     (6, "atividade-02.md", "Entrega da Atividade 02: a modelagem."),
     (7, "CLAUDE.md", "Notas de trabalho do projeto (decisões fechadas, parâmetros). Fica fora do Git de propósito."),
     (8, "README.md", "Apresentação do projeto Presença para quem abre o repositório.")],
    "A raiz do projeto no VS Code.", "Explorador do VS Code com a raiz projeto-presenca")

F["vs-marco02"] = arvore(
    "vs-v01-marco02.jpg", (56, 138, 360, 360),
    [(1, 172, 2, "aparelho"), (2, 194, 2, "apresentacao"), (3, 216, 2, "co2-ancora"),
     (4, 238, 2, "co2-gateway"), (5, 260, 2, "contrato"), (6, 282, 2, "evidencias"),
     (7, 304, 2, "servidor"), (8, 326, 2, "GUIA.md"), (9, 348, 2, "README.md")],
    [(1, "aparelho/", "<strong>O que roda no Wokwi</strong>: o ESP32 que faz o papel do celular do estudante. Produtor da fronteira principal."),
     (2, "apresentacao/", "Este guia (HTML e PDF) e o que o gera."),
     (3, "co2-ancora/", "O ESP32 da <em>segunda</em> fronteira: a âncora que mede CO₂ (Parte II)."),
     (4, "co2-gateway/", "O Python da segunda fronteira: recebe o CO₂ e alerta incoerência. É o “gateway” que você vai rodar com <code>python consumidor.py</code>."),
     (5, "contrato/", "<strong>O idioma</strong> que aparelho e servidor falam: os schemas JSON versionados e exemplos."),
     (6, "evidencias/", "Prints e logs dos testes que eu já rodei no Wokwi."),
     (7, "servidor/", "<strong>O que roda no seu notebook</strong>: o servidor de permanência em Python. Consumidor da fronteira principal."),
     (8, "GUIA.md", "Guia em texto da fronteira de CO₂."),
     (9, "README.md", "Resumo do Marco 2 em uma página: o que é, como rodar, o que foi validado.")],
    "Dentro de <code>marco-02/</code>: uma pasta por peça.", "Explorador do VS Code com marco-02 aberta")

F["vs-aparelho"] = arvore(
    "vs-v02-aparelho.jpg", (56, 160, 360, 250),
    [(1, 194, 3, "diagram.json"), (2, 216, 3, "libraries.txt"), (3, 238, 3, "sketch.ino")],
    [(1, "diagram.json", "O circuito escrito em texto: cada peça (ESP32, 3 potenciômetros, 2 botões, 3 LEDs, 3 resistores, buzzer, OLED), onde fica na tela e cada fio. O Wokwi desenha o circuito a partir dele."),
     (2, "libraries.txt", "As bibliotecas que o Wokwi baixa: <code>PubSubClient</code> (MQTT), <code>Adafruit GFX</code> e <code>Adafruit SSD1306</code> (display)."),
     (3, "sketch.ino", "O programa do ESP32, em C++ (~535 linhas). Lê o sinal, filtra, decide a região, manda o heartbeat, recebe o estado e acende LEDs, OLED e buzzer.")],
    "<code>aparelho/</code>: são exatamente os 3 arquivos do projeto no Wokwi.", "Pasta aparelho no VS Code")

F["vs-servidor"] = arvore(
    "vs-v03b-servidor.jpg", (56, 358, 360, 625),
    [(1, 392, 3, "__pycache__"), (2, 414, 3, ".pytest_cache"), (3, 436, 3, "testes"),
     (4, 480, 4, "test_permanencia.py"), (5, 502, 4, "test_servidor.py"), (6, 546, 3, "config.exemplo.json"),
     (7, 568, 3, "permanencia.py"), (8, 590, 3, "requirements.txt"), (9, 612, 3, "servidor.py")],
    [(1, "__pycache__/", "Criada sozinha pelo Python. Ignore."),
     (2, ".pytest_cache/", "Criada sozinha pelo pytest. Ignore."),
     (3, "testes/", "Os 34 testes automáticos."),
     (4, "test_permanencia.py", "23 testes da regra: trilateração, polígono, persistência, orçamento, requalificação, estorno, avisos, cálculo retroativo."),
     (5, "test_servidor.py", "11 testes do servidor inteiro com um MQTT falso: contrato, duplicata, fora de ordem, salto, lacuna, reboot, atrasados."),
     (6, "config.exemplo.json", "Broker, tópicos, <strong>parâmetros</strong> (com a escala 1:30) e a <strong>planta da sala</strong> (polígono e posição das âncoras)."),
     (7, "permanencia.py", "<strong>A regra</strong>: localização e máquina de estados. Não tem rede nem relógio; recebe o log e devolve o estado."),
     (8, "requirements.txt", "O que instalar: <code>paho-mqtt</code> e <code>jsonschema</code>."),
     (9, "servidor.py", "<strong>O programa que você roda</strong>: conecta no broker, valida, deduplica, chama a regra, publica estado e avisos, detecta silêncio.")],
    "<code>servidor/</code>: o consumidor da fronteira principal.", "Pasta servidor no VS Code")

F["vs-contrato"] = arvore(
    "vs-c01-validar.jpg", (56, 116, 360, 400),
    [(1, 150, 3, "v1"), (2, 172, 4, "exemplos"), (3, 278, 4, "gateway.contagem.v1.schema.json"),
     (4, 300, 4, "presenca.aviso.v1.schema.json"), (5, 322, 4, "presenca.estado.v1.schema.json"),
     (6, 344, 4, "presenca.heartbeat.v1.schema.json"), (7, 366, 4, "sala.ambiente.v1.schema.json"),
     (8, 388, 3, "validar.py")],
    [(1, "v1/", "A versão 1 do contrato. A versão faz parte do nome: uma mudança incompatível vira <code>v2</code> sem quebrar quem ainda usa a <code>v1</code>."),
     (2, "exemplos/", "Mensagens reais, gravadas durante os testes, uma por situação. Todas passam pela validação."),
     (3, "gateway.contagem.v1", "(CO₂) Comando do gateway para a âncora: quantos estudantes o rádio declara."),
     (4, "presenca.aviso.v1", "Servidor → aparelho: os avisos de 10 min, 13 min, limite esgotado e fim da aula."),
     (5, "presenca.estado.v1", "Servidor → aparelho: o estado decidido, acumulado, orçamento, posição."),
     (6, "presenca.heartbeat.v1", "<strong>Aparelho → servidor</strong>: o RSSI das 3 âncoras, a região, a sequência. O servidor valida cada heartbeat contra este arquivo."),
     (7, "sala.ambiente.v1", "(CO₂) Âncora → gateway: o CO₂ medido e o estado da verificação cruzada."),
     (8, "validar.py", "Script para você <strong>mostrar o contrato funcionando</strong>: valida todos os exemplos e mostra uma mensagem inválida sendo rejeitada.")],
    "<code>contrato/</code>: o combinado entre os dois lados, em arquivo.", "Pasta contrato no VS Code", margem=60)

F["vs-co2"] = arvore(
    "vs-v05b-co2.jpg", (56, 270, 360, 515),
    [(1, 304, 3, "diagram.json"), (2, 348, 3, "sketch.ino"), (3, 414, 3, "config.exemplo.json"),
     (4, 436, 3, "config.json"), (5, 458, 3, "consumidor.py"), (6, 480, 3, "recebidos.log"), (7, 502, 3, "requirements.txt")],
    [(1, "co2-ancora/diagram.json", "Circuito da âncora de CO₂: 1 potenciômetro (CO₂), 2 botões, 3 LEDs, OLED."),
     (2, "co2-ancora/sketch.ino", "Programa da âncora: mede CO₂, histerese, verificação cruzada com a contagem do rádio."),
     (3, "config.exemplo.json", "Modelo de configuração do gateway."),
     (4, "config.json", "A configuração que ele usa de fato (começa declarando 25 estudantes). Fica fora do Git."),
     (5, "consumidor.py", "<strong>O gateway de CO₂</strong>: <code>python consumidor.py</code>. Recebe, valida, deduplica e dispara o alerta de incoerência."),
     (6, "recebidos.log", "Criado ao rodar: uma linha por evento recebido."),
     (7, "requirements.txt", "O que instalar (o mesmo do servidor).")],
    "<code>co2-ancora/</code> e <code>co2-gateway/</code>: a segunda fronteira.", "Pastas co2-ancora e co2-gateway no VS Code")

F["vs-evidencias"] = arvore(
    "vs-v06-evidencias.jpg", (56, 122, 360, 435),
    [(1, 157, 3, "componentes"), (2, 179, 3, "presenca"), (3, 201, 4, "componentes"),
     (4, 223, 4, "01-normal-presente.jpg"), (5, 377, 4, "log-serial-aparelho.txt"),
     (6, 399, 4, "log-servidor.txt"), (7, 421, 4, "recebidos.jsonl")],
    [(1, "componentes/", "Fotos da âncora de CO₂ (Parte II)."),
     (2, "presenca/", "Tudo da execução da fronteira principal no Wokwi, em 25/09/2026."),
     (3, "presenca/componentes/", "Recortes de cada peça e ampliações do OLED."),
     (4, "01… a 07….jpg", "Uma captura do Wokwi por cenário testado (normal, sala vizinha, avisos, rede fora, fim da aula, limite esgotado)."),
     (5, "log-serial-aparelho.txt", "Tudo o que o ESP32 escreveu no monitor serial."),
     (6, "log-servidor.txt", "Tudo o que o servidor escreveu no terminal."),
     (7, "recebidos.jsonl", "Cada heartbeat recebido, com o carimbo do servidor e o que ele concluiu.")],
    "<code>evidencias/</code>: a prova de que rodou.", "Pasta evidencias no VS Code")

F["vs-apresentacao"] = arvore(
    "vs-v07b-apresentacao.jpg", (56, 248, 360, 425),
    [(1, 282, 3, "fontes"), (2, 370, 3, "apresentacao-marco-02.html"), (3, 392, 3, "apresentacao-marco-02.pdf"),
     (4, 414, 3, "montar.py")],
    [(1, "fontes/", "O texto deste guia, as imagens e os estilos. É aqui que se edita."),
     (2, ".html", "Este guia para abrir no navegador (funciona sem internet)."),
     (3, ".pdf", "Este guia em PDF."),
     (4, "montar.py", "Junta as fontes e gera o HTML e o PDF: <code>python montar.py</code>.")],
    "<code>apresentacao/</code>.", "Pasta apresentacao no VS Code", margem=60)

# ===========================================================================
# WOKWI - TELAS
# ===========================================================================
F["wk-tela"] = {
    "img": "w01-abrir.jpg", "alt": "Tela do Wokwi ao abrir o projeto do aparelho",
    "legenda": "O que aparece ao abrir <b>wokwi.com/projects/476110187626906625</b>.",
    "marcas": [
        ("seta", 1, (140, 34), (120, 200)), ("seta", 2, (282, 34), (470, 200)),
        ("seta", 3, (58, 76), (58, 150)), ("seta", 4, (161, 76), (161, 150)),
        ("seta", 5, (264, 76), (264, 150)), ("seta", 6, (377, 76), (377, 150)),
        ("seta", 7, (470, 300), (560, 330)), ("seta", 8, (711, 120), (711, 168)),
        ("seta", 9, (758, 120), (758, 168)), ("seta", 10, (806, 120), (806, 168)),
        ("seta", 11, (960, 240), (1300, 140)), ("seta", 12, (900, 470), (960, 510)),
        ("seta", 13, (684, 300), (640, 255)), ("seta", 14, (1265, 548), (1265, 505)),
    ],
    "itens": [
        (1, "SAVE", "Salva o projeto. <strong>No dia, não precisa</strong>: o projeto já está salvo. Se mexer em algo e salvar, a mudança fica pública."),
        (2, "SHARE", "Copia o link do projeto."),
        (3, "sketch.ino", "O programa do ESP32. Clique aqui para mostrar o código."),
        (4, "diagram.json", "O circuito em texto."),
        (5, "libraries.txt", "As bibliotecas."),
        (6, "Library Manager", "Onde se adicionam bibliotecas. Não precisa mexer."),
        (7, "Editor", "O código. Dá para rolar e mostrar cada parte (seção 8 deste guia)."),
        (8, "▶ Play", "<strong>Liga a simulação.</strong> Na primeira vez compila (pode demorar até 1 min na fila do plano gratuito)."),
        (9, "+", "Adiciona peças. Não mexa."),
        (10, "⋮", "Menu da simulação."),
        (11, "Circuito", "As peças. Roda do mouse aproxima e afasta; arrastar o fundo move a vista."),
        (12, "Monitor serial", "Tudo o que o ESP32 escreve: os heartbeats em JSON, as mudanças de região, os avisos, a rede. Mostre para a banca."),
        (13, "Divisória", "Arraste para dar mais espaço ao circuito ou ao código. A divisória entre circuito e monitor também se arrasta."),
        (14, "Botões do monitor", "Gráfico, pausar a rolagem, limpar e recolher."),
    ]}

F["wk-rodando"] = {
    "img": "w02-rodando.jpg", "alt": "Wokwi com a simulação rodando: PRESENTE no OLED, LED verde e heartbeat no monitor serial",
    "legenda": "Depois do ▶: a simulação rodando.",
    "marcas": [
        ("seta", 1, (1215, 100), (1170, 140)), ("seta", 2, (1330, 100), (1330, 140)),
        ("seta", 3, (711, 120), (711, 168)), ("seta", 4, (758, 120), (758, 168)),
        ("seta", 5, (806, 120), (806, 168)), ("seta", 6, (854, 110), (905, 150)),
        ("seta", 7, (1175, 205), (1300, 260)), ("seta", 8, (1209, 293), (1300, 310)),
        ("seta", 9, (880, 455), (1300, 450)),
    ],
    "itens": [
        (1, "Relógio da simulação", "Tempo <em>simulado</em> desde o boot. Anda mais devagar que o real."),
        (2, "Velocidade", "Quanto do tempo real a simulação consegue acompanhar (fica entre 10 % e 80 %). É normal."),
        (3, "↻ Reiniciar", "Reinicia o ESP32 (novo boot). <strong>Não</strong> devolve os potenciômetros à posição inicial."),
        (4, "■ Parar", "Desliga a simulação."),
        (5, "❚❚ Pausar", "Congela. Não use durante um teste: o servidor vai acusar silêncio."),
        (6, "Wi-Fi", "Aparece quando o ESP32 conectou na rede <code>Wokwi-GUEST</code>."),
        (7, "OLED", "O que o estudante vê: estado decidido pelo servidor, acumulado, orçamento, RSSI das 3 âncoras, região."),
        (8, "LED verde", "PRESENTE, decidido pelo servidor."),
        (9, "Heartbeat no serial", "O JSON que foi enviado. Aponte o <code>eventId</code> (aparelho#boot#sequência)."),
    ]}

_CIRC = [
    ("seta", 1, (602, 118), (578, 150)), ("seta", 2, (602, 213), (578, 245)),
    ("seta", 3, (602, 308), (578, 345)), ("seta", 4, (606, 408), (578, 440)),
    ("seta", 5, (606, 485), (578, 520)), ("seta", 6, (830, 250), (760, 200)),
    ("seta", 7, (1095, 150), (1150, 150)), ("seta", 8, (1085, 265), (1150, 265)),
    ("seta", 9, (1085, 332), (1150, 332)), ("seta", 10, (1085, 400), (1150, 400)),
    ("seta", 11, (1005, 342), (960, 380)), ("seta", 12, (1085, 490), (1150, 490)),
    ("seta", 13, (740, 283), (700, 240)),
]
F["wk-circuito"] = {
    "img": "w03-circuito.jpg", "corte": (560, 80, 1200, 560),
    "alt": "Circuito do aparelho ampliado com cada peça numerada",
    "legenda": "O circuito do aparelho, peça por peça (vista ampliada, simulação rodando).",
    "marcas": _CIRC,
    "itens": [
        (1, "Potenciômetro A", "RSSI da âncora A (parede oeste), no pino <code>GPIO34</code>."),
        (2, "Potenciômetro B", "RSSI da âncora B (parede leste), no <code>GPIO35</code>."),
        (3, "Potenciômetro C", "RSSI da âncora C (parede norte), no <code>GPIO32</code>."),
        (4, "Botão azul ANOMALIA", "<code>GPIO25</code>. Cada aperto arma a próxima anomalia: duplicata → fora de ordem → salto."),
        (5, "Botão vermelho REDE OFF", "<code>GPIO26</code>. Derruba e restabelece a rede simulada."),
        (6, "ESP32", "O “celular”. Wi-Fi, MQTT, a lógica do <code>sketch.ino</code>."),
        (7, "OLED SSD1306", "Display I²C (SDA 21, SCL 22)."),
        (8, "LED verde", "<code>GPIO14</code>: PRESENTE."),
        (9, "LED amarelo", "<code>GPIO27</code>: AUSÊNCIA TOLERADA; pisca quando chega um aviso."),
        (10, "LED vermelho", "<code>GPIO13</code>: FORA."),
        (11, "Resistores de 220 Ω", "Um por LED, para limitar a corrente (~6 mA)."),
        (12, "Buzzer", "<code>GPIO18</code>: toca quando chega um aviso (a notificação do celular)."),
        (13, "Fios dos potenciômetros", "Verde, azul e violeta levam o sinal de cada potenciômetro ao ESP32; vermelho é 3,3 V e preto é GND."),
    ]}

F["wk-vizinha"] = {
    "img": "w04-vizinha.jpg", "corte": (560, 80, 1200, 460),
    "alt": "Circuito com os potenciômetros na posição de sala vizinha: OLED com AUSENCIA e LED amarelo",
    "legenda": "Sinal forte vindo de fora da sala: o servidor decide AUSÊNCIA.",
    "marcas": [("seta", 1, (602, 118), (578, 150)), ("seta", 2, (602, 213), (578, 245)),
               ("seta", 3, (602, 308), (578, 345)), ("seta", 4, (1060, 160), (1150, 175)),
               ("seta", 5, (1085, 332), (1150, 332))],
    "itens": [
        (1, "A", "Mais fraco (a âncora A está longe, do outro lado da sala)."),
        (2, "B", "Forte: o estudante está perto da parede leste, mas do lado de fora."),
        (3, "C", "Médio."),
        (4, "OLED", "<code>AUSENCIA</code>, com a região ainda <code>DENTRO_ALCANCE</code>: o aparelho acha que está no alcance, mas o servidor trilaterou e o ponto caiu fora do polígono."),
        (5, "LED amarelo", "AUSÊNCIA TOLERADA: o tempo ainda conta, mas consome o orçamento."),
    ]}

F["wk-co2"] = {
    "img": "w-co2-incoerente.jpg", "corte": (683, 78, 1366, 520),
    "alt": "Wokwi da âncora de CO₂ com o LED vermelho INCOERENTE aceso",
    "legenda": "O projeto de CO₂ (<b>wokwi.com/projects/476001394839038977</b>) acusando incoerência.",
    "marcas": [("seta", 1, (800, 207), (730, 250)), ("seta", 2, (790, 376), (720, 330)),
               ("seta", 3, (790, 467), (720, 500)), ("seta", 4, (1000, 330), (1100, 270)),
               ("seta", 5, (1218, 240), (1150, 290)), ("seta", 6, (1240, 325), (1330, 290)),
               ("seta", 7, (1240, 397), (1330, 360)), ("seta", 8, (1240, 467), (1330, 440)),
               ("seta", 9, (1275, 91), (1210, 125))],
    "itens": [
        (1, "Potenciômetro", "CO₂ simulado, de 380 a 2200 ppm."),
        (2, "Botão azul", "Anomalia de sequência (duplicata → fora de ordem → salto)."),
        (3, "Botão vermelho", "Rede fora / de volta."),
        (4, "ESP32", "A âncora da sala."),
        (5, "OLED", "ppm, ocupação pelo CO₂, contagem do rádio, sequência, estado."),
        (6, "LED verde", "COERENTE."),
        (7, "LED amarelo", "ATENÇÃO (dados insuficientes ou transição)."),
        (8, "LED vermelho", "INCOERENTE: o rádio diz 25 estudantes, o CO₂ diz sala vazia."),
        (9, "Relógio", "Tempo simulado."),
    ]}

# ===========================================================================
# WOKWI - CODIGO DO sketch.ino
# ===========================================================================
F["k01"] = codigo("k01-cabecalho.jpg", 1, [(1, 2, 8), (2, 10, 15), (3, 17, 22), (4, 24, 26)],
    [(1, "Identificação", "Projeto, aluna, responsabilidade e o teste adversarial da matrícula final 8."),
     (2, "Papel no sistema", "Por que o ESP32 é o celular: a âncora só transmite, quem mede é o aparelho."),
     (3, "Declaração da entrada simulada", "Exigida pela Atividade 03: potenciômetro não é rádio. Faixa −105 a −35 dBm; abaixo de −100 é “não ouvida”."),
     (4, "Limitação de tempo", "<code>eventTimeMs</code> é tempo desde o boot, não relógio real.")],
    "Linhas 1–26: o cabeçalho.", "Cabeçalho do sketch.ino no Wokwi")

F["k02"] = codigo("k02-identidade.jpg", 35, [(1, 38, 41), (2, 43, 44), (3, 46, 47), (4, 49, 51), (5, 56, 60)],
    [(1, "Identidade", "<code>apar-01</code> é o aparelho; <code>tok-7f3a</code> é o <em>pseudônimo</em> do aluno (nunca MAC ou nome); os ids das 3 âncoras."),
     (2, "Wi-Fi", "A rede do próprio Wokwi, com saída para a internet."),
     (3, "Broker MQTT", "O servidor público <code>broker.hivemq.com</code>, porta 1883."),
     (4, "Tópicos", "Onde publica o heartbeat e onde escuta o estado e o aviso — só os do próprio aluno."),
     (5, "Pinos", "Onde cada peça está ligada.")],
    "Linhas 35–60: identidade, rede e tópicos.", "Identidade e rede no sketch.ino")

F["k03"] = codigo("k03-pinos-parametros.jpg", 53, [(1, 56, 56), (2, 57, 58), (3, 59, 62), (4, 67, 69), (5, 70, 71), (6, 72, 74), (7, 75, 76), (8, 77, 78)],
    [(1, "Potenciômetros", "Nos pinos 34, 35 e 32 (ADC1, que funciona com Wi-Fi ligado)."),
     (2, "Botões", "25 (anomalia) e 26 (rede)."),
     (3, "LEDs e buzzer", "14 verde, 27 amarelo, 13 vermelho, 18 buzzer."),
     (4, "Escala do potenciômetro", "0–4095 vira −105 a −35 dBm; abaixo de −100 a âncora não foi ouvida."),
     (5, "<strong>Histerese</strong>", "Entra no alcance acima de −70 dBm, sai só abaixo de −85. <em>Bom lugar para uma alteração ao vivo.</em>"),
     (6, "Tempos", "Média de 5 amostras, uma amostra a cada 100 ms, heartbeat a cada 500 ms (no real, 60–90 s)."),
     (7, "Validade e aviso", "Resposta do servidor vale 4 s; aviso fica 6 s na tela."),
     (8, "Fila e debounce", "Até 60 heartbeats guardados sem rede; botão ignora repiques de 50 ms.")],
    "Linhas 53–78: pinos e parâmetros. Todos os números estão aqui, nenhum espalhado pelo código.", "Pinos e parâmetros")

F["k04"] = codigo("k04-amostrar.jpg", 139, [(1, 142, 145), (2, 147, 150), (3, 155, 158), (4, 159, 164)],
    [(1, "lerRssiBruto", "Lê o ADC (0–4095) e converte para dBm."),
     (2, "Comentário", "Por que “não ouvida” não é um número baixo, é falta de dado."),
     (3, "Leitura impossível", "Acima de −30 dBm conta como inválida e é descartada."),
     (4, "<strong>Âncora não ouvida</strong>", "Abaixo de −100 dBm: marca como não ouvida e <em>esvazia a janela</em> daquela âncora.")],
    "Linhas 139–164: leitura e validação.", "Função amostrar")

F["k05"] = codigo("k05-media.jpg", 166, [(1, 166, 173), (2, 178, 186)],
    [(1, "Média móvel", "Guarda as 5 últimas leituras de cada âncora e tira a média: suaviza o ruído."),
     (2, "melhorRssi", "O maior sinal entre as âncoras ouvidas. É ele que vai na regra de região.")],
    "Linhas 166–186: filtro.", "Média móvel", y_primeira=126)

F["k06"] = codigo("k06-regiao.jpg", 186, [(1, 191, 194), (2, 202, 202), (3, 204, 204), (4, 205, 205), (5, 206, 207), (6, 209, 211)],
    [(1, "Explicação", "A regra local do aparelho."),
     (2, "Nenhuma ouvida", "Fora do alcance, sem discussão."),
     (3, "Entrada", "Melhor sinal acima de −70 dBm → <code>DENTRO_ALCANCE</code>."),
     (4, "Saída", "Abaixo de −85 dBm → <code>FORA_ALCANCE</code>."),
     (5, "Faixa morta", "Entre −85 e −70 mantém o que estava: <strong>isso é a histerese</strong>."),
     (6, "Serial", "Escreve <code>[REGIAO] X -> Y</code> quando muda.")],
    "Linhas 186–211: a regra local, com histerese.", "Função atualizarRegiao")

F["k07"] = codigo("k07-json.jpg", 215, [(1, 218, 219), (2, 220, 229), (3, 230, 232), (4, 234, 240)],
    [(1, "montarJson", "Monta o texto do heartbeat."),
     (2, "Âncoras", "Uma entrada por âncora; <code>null</code> quando não foi ouvida."),
     (3, "value", "O melhor sinal, ou <code>null</code>."),
     (4, "O contrato", "Os campos exatamente como no <code>presenca.heartbeat.v1.schema.json</code>. Repare no <code>eventId</code> = aparelho#boot#sequência.")],
    "Linhas 215–240: o heartbeat.", "Função montarJson")

F["k08"] = codigo("k08-fila.jpg", 245, [(1, 247, 259), (2, 248, 254), (3, 261, 270), (4, 265, 267)],
    [(1, "enfileirar", "Sem rede, guarda o heartbeat (sequência, tempo original, RSSI, região)."),
     (2, "Fila cheia", "Descarta o <em>mais antigo</em> e avisa: o servidor verá um salto."),
     (3, "drenarFila", "Quando a rede volta, envia tudo o que estava guardado."),
     (4, "bufferizado", "Vai com <code>bufferizado: true</code> e o tempo original: o servidor coloca no passado.")],
    "Linhas 245–270: a fila da queda de rede.", "Fila de retenção")

F["k09"] = codigo("k09-publicar-a.jpg", 279, [(1, 281, 284), (2, 286, 292), (3, 294, 298), (4, 299, 299), (5, 301, 302)],
    [(1, "publicarHeartbeat", "Roda a cada 500 ms. Lê qual anomalia está armada."),
     (2, "<strong>Duplicata</strong>", "Reenvia o último heartbeat idêntico (mesmo <code>eventId</code>)."),
     (3, "<strong>Salto</strong>", "Pula 5 números de sequência."),
     (4, "Sequência", "Normal: soma 1."),
     (5, "Monta e escreve", "O JSON vai para o monitor serial (exigência da Atividade 03, item 5.2).")],
    "Linhas 279–302: envio e teste adversarial (1).", "publicarHeartbeat parte 1")

F["k10"] = codigo("k10-publicar-b.jpg", 304, [(1, 304, 309), (2, 311, 317), (3, 319, 320), (4, 321, 325)],
    [(1, "Sem rede", "Guarda na fila e escreve <code>[REDE] indisponivel … retido</code>."),
     (2, "<strong>Fora de ordem</strong>", "Segura este heartbeat…"),
     (3, "Envio normal", "…envia o próximo…"),
     (4, "Entrega o retido", "…e só então entrega o que estava segurando: o N chega depois do N+1.")],
    "Linhas 304–325: envio e teste adversarial (2).", "publicarHeartbeat parte 2", y_primeira=107)

F["k11"] = codigo("k11-estado.jpg", 344, [(1, 346, 353), (2, 355, 359), (3, 360, 364)],
    [(1, "Resposta velha não vale", "Cada estado tem número; um número menor que o último é ignorado."),
     (2, "Estado do servidor", "Lê o estado e escreve <code>[ESTADO] servidor decidiu: X -> Y</code>."),
     (3, "Guarda", "Percentual, orçamento, se a aula acabou e <em>quando</em> chegou (para saber se ainda vale).")],
    "Linhas 344–365: recebendo o estado.", "aoReceberEstado")

F["k12"] = codigo("k12-aviso.jpg", 366, [(1, 367, 374), (2, 375, 379), (3, 380, 380), (4, 382, 387)],
    [(1, "<strong>Idempotência</strong>", "Guarda os 8 últimos avisos; se o mesmo chegar de novo, ignora."),
     (2, "Mostra", "Guarda o texto para o OLED e escreve <code>[AVISO] …</code>."),
     (3, "Buzzer", "Toca 400 ms: a notificação."),
     (4, "aoReceber", "Separa o que chegou: estado ou aviso.")],
    "Linhas 366–387: recebendo o aviso.", "aoReceberAviso")

F["k13"] = codigo("k13-atuar.jpg", 391, [(1, 392, 394), (2, 402, 406), (3, 408, 416)],
    [(1, "estadoValido", "Só vale se chegou há menos de 4 s."),
     (2, "<strong>Comportamento seguro</strong>", "Cada LED só acende se o estado é recente; resposta velha apaga tudo."),
     (3, "Display", "Escreve pseudônimo, estado, acumulado, RSSI, região ou o aviso.")],
    "Linhas 391–416: a atuação.", "Função atuar")

F["k14"] = codigo("k14-botoes.jpg", 443, [(1, 445, 448), (2, 450, 460), (3, 462, 468)],
    [(1, "lerBotoes", "Guarda o último estado de cada botão e quando mudou."),
     (2, "Azul", "Na borda de descida (apertou), arma a anomalia e passa para a próxima do ciclo."),
     (3, "Vermelho", "Alterna a rede; ao voltar, drena a fila.")],
    "Linhas 443–468: os botões, com debounce.", "Função lerBotoes")

F["k15"] = codigo("k15-setup.jpg", 474, [(1, 475, 484), (2, 486, 495), (3, 497, 497)],
    [(1, "conectarMqtt", "Conecta no broker e assina estado e aviso do próprio aluno."),
     (2, "setup: pinos", "Botões com pull-up interno; LEDs e buzzer como saída."),
     (3, "<strong>bootId</strong>", "Número aleatório a cada ligação: o reboot não vira duplicata.")],
    "Linhas 474–497: inicialização.", "setup e conectarMqtt")

F["k16"] = codigo("k16-loop.jpg", 511, [(1, 512, 515), (2, 521, 522), (3, 524, 529), (4, 531, 534)],
    [(1, "MQTT", "Broker, função que recebe e buffer de 768 bytes (o heartbeat passa de 256)."),
     (2, "Todo ciclo", "Lê os botões e mantém o MQTT vivo."),
     (3, "A cada 100 ms", "Amostra, atualiza a região, atua."),
     (4, "A cada 500 ms", "Publica o heartbeat.")],
    "Linhas 511–535: o laço principal.", "loop", y_primeira=107)

F["k17"] = codigo("k17-diagram.jpg", 1, [(1, 6, 12), (2, 13, 21)],
    [(1, "Uma peça", "Tipo (<code>wokwi-esp32-devkit-v1</code>), id, posição na tela."),
     (2, "Potenciômetro A", "Com <code>value: 714</code>: começa em −56 dBm, dentro da sala.")],
    "A aba <code>diagram.json</code>: o circuito em texto.", "diagram.json", corte=(0, 40, 683, 577), x_faixa=660, margem=46)

# ===========================================================================
# VS CODE - CODIGO PYTHON (legenda por numero de linha)
# ===========================================================================
def _vs(img, legenda, itens, alt):
    return {"img": img, "corte": (362, 62, 1058, 700), "itens": itens, "legenda": legenda, "alt": alt}

F["py-config"] = _vs("vs-c02-config.jpg", "<code>servidor/config.exemplo.json</code>", [
    (1, "Linhas 2–8", "Broker e os três tópicos (heartbeat, estado, aviso)."),
    (2, "Linhas 10–19", "<strong>Os parâmetros</strong> em valores reais (30 s, 900 s = 15 min…) e a <code>escala</code> 30 que divide todos. Mudar <code>escala</code> é a alteração ao vivo mais fácil."),
    (3, "Linhas 21–30", "A planta: polígono 12×9 m, posição das 3 âncoras e o modelo de propagação.")], "config.exemplo.json")
F["py-validacao"] = _vs("vs-c03-processar-validacao.jpg", "<code>servidor.py</code> — início do processamento", [
    (1, "Linhas 172–179", "Chegou uma mensagem: tenta ler o JSON."),
    (2, "Linhas 181–185", "Valida contra o contrato; se falhar, escreve <code>INVALIDO</code> e descarta."),
    (3, "Linhas 187–191", "O contador ingênuo, só para comparação."),
    (4, "Linha 196", "Pega <code>eventId</code>, sequência e boot.")], "servidor.py validação")
F["py-anomalias"] = _vs("vs-c04-processar-anomalias.jpg", "<code>servidor.py</code> — as três anomalias", [
    (1, "Linhas 198–203", "<strong>Duplicata</strong>: <code>eventId</code> já visto → descarta."),
    (2, "Linhas 209–222", "<strong>Fora de ordem</strong>: sequência menor que a maior vista → aceita e insere no lugar certo; se preenche uma lacuna, desconta o perdido."),
    (3, "Linhas 224–228", "<strong>Salto</strong>: sequência pulou → conta os perdidos e guarda a lacuna.")], "servidor.py anomalias")
F["py-calculo"] = _vs("vs-c05-processar-calculo.jpg", "<code>servidor.py</code> — do heartbeat à decisão", [
    (1, "Linhas 234–239", "Atrasado (<code>bufferizado</code>): avisa que entra no passado."),
    (2, "Linhas 241–248", "Registra, põe na linha do tempo, classifica (dentro/fora/neutro) e guarda no log."),
    (3, "Linha 251", "<strong>Refaz a sessão inteira</strong> com <code>calcular()</code>."),
    (4, "Linhas 256–258", "Mostra no terminal, publica o estado e os avisos.")], "servidor.py cálculo")
F["py-publicar"] = _vs("vs-c06-publicar.jpg", "<code>servidor.py</code> — respostas ao aparelho", [
    (1, "Linhas 269–290", "Monta o <code>presenca.estado.v1</code> e publica com <code>retain</code> no tópico do aluno."),
    (2, "Linhas 292–310", "Para cada aviso novo: monta o <code>presenca.aviso.v1</code>, publica com QoS 1 e imprime a faixa vermelha no terminal.")], "servidor.py publicar")
F["py-silencio"] = _vs("vs-c07-silencio.jpg", "<code>servidor.py</code> — silêncio", [
    (1, "Linhas 315–325", "A cada segundo olha o relógio real; sem heartbeat há 6 s, escreve <code>SILENCIO</code> e não decide nada.")], "servidor.py silêncio")
F["py-trilaterar"] = _vs("vs-c08-trilaterar.jpg", "<code>permanencia.py</code> — trilateração e polígono", [
    (1, "Linhas 103–124", "<strong>Trilateração</strong>: RSSI vira distância; três círculos viram um sistema linear; resolve (x, y)."),
    (2, "Linhas 126–138", "<strong>Polígono</strong>: conta quantas paredes uma semirreta atravessa (ímpar = dentro).")], "permanencia.py trilaterar")
F["py-classificar"] = _vs("vs-c09-classificar.jpg", "<code>permanencia.py</code> — o que um heartbeat diz", [
    (1, "Linhas 141–153", "A tabela da decisão, escrita no comentário."),
    (2, "Linhas 155–162", "Fora do alcance → fora; sem 3 âncoras → neutro; senão, o polígono decide.")], "permanencia.py classificar")
F["py-orcamento"] = _vs("vs-c10-orcamento.jpg", "<code>permanencia.py</code> — orçamento", [
    (1, "Linhas 234–239", "Credita a ausência anterior só se a presença durou a requalificação."),
    (2, "Linhas 241–257", "Durante a ausência: avisos de 20 s e 26 s e, ao esgotar, <strong>estorno</strong> e FORA.")], "permanencia.py orçamento")
F["py-maquina"] = _vs("vs-c11-maquina.jpg", "<code>permanencia.py</code> — a máquina de estados", [
    (1, "Linhas 278–280", "FORA → PRESENTE, datado no início real da condição."),
    (2, "Linhas 282–294", "PRESENTE → AUSÊNCIA (se há orçamento) ou → FORA (se não há)."),
    (3, "Linhas 296–304", "AUSÊNCIA → PRESENTE: consome o orçamento e deixa a ausência pendente de requalificação.")], "permanencia.py máquina")
F["py-fechamento"] = _vs("vs-c12-fechamento.jpg", "<code>permanencia.py</code> — fechamento", [
    (1, "Linhas 306–318", "No último instante: o que ainda não se confirmou vira <em>provisório</em>; o garantido nunca cai."),
    (2, "Linhas 327–330", "Fim da aula: ausência em curso não é creditada; emite o aviso final.")], "permanencia.py fechamento")
F["py-co2"] = _vs("vs-c13-co2-gateway.jpg", "<code>co2-gateway/consumidor.py</code>", [
    (1, "Linhas 173–182", "Recebe o evento de CO₂ e lê o JSON."),
    (2, "Linhas 185–189", "Valida contra <code>sala.ambiente.v1</code>."),
    (3, "Linhas 195–200", "Deduplica por <code>eventId</code>.")], "consumidor.py")
