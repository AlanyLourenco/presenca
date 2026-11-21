# Guia do vídeo do Marco 4 (20/11)

Como no Marco 3: as telas (terminais, navegador e o celular, espelhado no PC) são gravadas e você
narra por cima. Você não aparece filmada nas cenas físicas. Cada cena abaixo diz **o que
aparece** e **o que falar**. Pode falar com as suas palavras; errou, repita a frase, que fica a
última. Duração alvo: **10 a 12 min**.

**Montagem do Marco 4:** uma âncora (o **notebook**) e **dois celulares na mesma aula**: o seu
celular de verdade (professor + aluno A) e um **celular simulado** (aluno B), que roda no PC, fala
pelo mesmo broker e entra na aula que você iniciar no app.

## Antes de gravar

- [ ] APK novo (`presenca-m4.apk`) instalado no celular: **Presença M4**.
- [ ] No celular: Bluetooth, localização e notificações ligados; *Configurações → Apps →
      Presença M4 → Bateria → Sem restrições* (senão o Android para o app com a tela apagada).
- [ ] Notebook na tomada, **hotspot** do celular ligado (a rede da faculdade bloqueia o broker).
- [ ] Relógio do notebook sincronizado (*Configurações → Hora → Sincronizar agora*).
- [ ] `python ataques\celulares.py --limpar --ws` (tira do broker cadastros simulados velhos).

## Montar (5 min)

```powershell
cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\marco-04"
.\subir.ps1
```

Abre o banco e duas janelas: **servidor** (`Conectado ao …emqxsl.com, porta 8084` e
`Gravando em: PostgreSQL/TimescaleDB`) e **âncora** (`rádio: TRANSMITINDO`, token a cada 12 s).
Abra no navegador http://127.0.0.1:8090/ (o relatório). Deixe aberta uma terceira janela do
PowerShell em `marco-04\ataques` (é dela que sai o celular simulado).

No celular: **Área do administrador** → crie a turma (anote o **código**, ex.: `ABC234`) →
**Publicar para os estudantes** → **Calibrar** a 1 m do notebook. Depois **Entrar numa turma**
→ o código → nome e matrícula → **Enviar ao professor**. (Se já estiver feito, pule.)

---

## Cena 1 · Abertura (≈ 40 s)
**[na tela: título "Marco 4 — Sistema completo", depois a tabela dos seis eixos do README]**

> Olá, professor. Eu sou a Alany, e este é o vídeo do Marco 4 do Presença. No Marco 3 eu deixei o
> caminho seguro. Neste marco eu fechei o sistema inteiro, seguindo as respostas que o senhor deu
> às minhas perguntas: heartbeat a cada cinco segundos, sensores do celular, um atuador, banco
> temporal em PostgreSQL, relatório para o professor, testes com dois celulares, testes de falha e
> a documentação para reproduzir tudo. Vou seguir os seis eixos do marco, nesta ordem.

## Cena 2 · Como funciona (≈ 1 min)
**[na tela: o diagrama do README]**

> A âncora é um farol Bluetooth: ela só transmite um código que muda a cada doze segundos, e
> nunca sabe quem está na sala. Neste marco a âncora é o notebook. O sistema já aceita mais de
> uma, cada uma com a sua calibração, e a mesma âncora em ESP32 está pronta no repositório.
> O celular do aluno mede o sinal e, a cada cinco segundos, manda ao broker um heartbeat
> assinado, com o código que ouviu e os dados dos sensores. O servidor confere a assinatura e o
> código, calcula a permanência a partir do histórico, grava tudo no PostgreSQL e devolve ao
> celular o estado e os avisos. O professor vê o relatório no próprio app.

## Cena 3 · Subindo tudo (≈ 40 s)
**[na tela: PowerShell rodando `.\subir.ps1`; as janelas do servidor e da âncora abrindo]**

> Um comando sobe tudo: o banco, o servidor e a âncora do notebook. O banco é um PostgreSQL com
> a extensão TimescaleDB, numa pasta, sem instalador e sem Docker, porque o meu notebook tem
> oito gigas de memória. Para quem preferir Docker, o projeto também tem o docker-compose.

## Cena 4 · A aula com dois celulares (≈ 2 min 30 s) — eixo 1
**[na tela: o celular toca em Iniciar aula agora; a janela 3 roda o simulado; depois o celular e o servidor lado a lado]**

1. No celular (admin): **Iniciar aula agora**. Volte para a tela do aluno.
2. Na janela 3, **logo em seguida**: `python celulares.py 1 --turma ABC234 --ws` (o seu código).
   Deve aparecer `Entrando na aula que o professor iniciou: demo-…`.
3. Roteiro físico (a aula dura 2 min):
   - 0–30 s: celular perto do notebook → "Na sala — contando".
   - ~30 s: leve o **celular** para longe (outro cômodo) → "Fora da sala — usando a tolerância";
     o aviso chega no celular.
   - ~60 s: volte. Ele volta a contar.
   - ~80 s: apague a **tela** do celular (botão de energia) e espere uns 15 s.

> Eu inicio a aula. Na demonstração a aula de cinquenta minutos dura dois: um segundo aqui vale
> vinte e cinco de aula. O segundo aluno é um celular simulado que roda no notebook, com a
> própria chave, e entra na mesma aula pelo broker. No servidor aparece o heartbeat dos dois, a
> cada cinco segundos, com a situação e o tempo que contou.
> Agora eu levo o meu celular para longe. Ele sai da sala e passa a usar a tolerância, e o
> servidor manda o aviso, assinado, que chega no celular. Eu volto, e ele volta a contar.
> E agora eu apago a tela: ele continua mandando, porque o app roda em segundo plano.

## Cena 5 · Sensores do celular (≈ 50 s) — eixo 2
**[na tela: cartão "Sensores do celular" no app; linhas `sensor tok-…: mexendo · bateria …` no servidor]**

> O app lê dois sensores do celular: o acelerômetro e a bateria. A cada cinco segundos ele manda
> ao broker o quanto o celular se mexeu e o nível da bateria, também assinado. O servidor grava e
> usa os dois. Se um celular fica parado a aula inteira, o relatório marca "celular parado", porque
> pode ser um celular emprestado, deixado na sala. E se um celular para de falar e a última bateria
> era quase zero, o servidor diz que provavelmente foi a bateria, em vez de achar que o aluno saiu.

## Cena 6 · O atuador (≈ 1 min) — eixo 2
**[na tela: celular → Área do administrador → a turma → Relatório de presença e chamada → Chamar no aluno simulado; a janela 3 mostra o comando chegando; o celular mostra "respondeu: Estou aqui"]**

Depois, para atuar no **seu** celular: volte para a tela do aluno e, na janela do servidor,
digite `c tok-XXXXXXXX lanterna` + Enter (o seu pseudônimo aparece no cartão **Segurança** do
app e nas linhas do servidor). A lanterna do celular pisca e o servidor mostra a confirmação.

> O atuador é uma operação mandada ao celular. Na tela de relatório eu toco em "Chamar" no aluno
> simulado. O comando chega, ele toca em "Estou aqui", e a resposta volta assinada: eu vejo aqui
> que ele respondeu. O servidor também pode mandar: agora ele pede para o meu celular piscar a
> lanterna. O celular só obedece a comando assinado pelo professor ou pelo servidor; qualquer
> outro é recusado.

## Cena 7 · Relatório e banco (≈ 1 min 30 s) — eixo 3
**[na tela: celular → Exportar lista da turma (CSV) → menu de compartilhar; navegador em 127.0.0.1:8090; o CSV aberto no Excel; PowerShell com `.\banco\banco.ps1 estado`]**

> Quando a aula termina, o relatório mostra cada aluno, o percentual e o resultado. Eu exporto em
> CSV direto do celular e mando por onde quiser; abre no Excel. O mesmo relatório está numa
> página e numa API de consulta no servidor.
> No banco, os eventos ficam numa tabela temporal do TimescaleDB, que é PostgreSQL. Todos os
> heartbeats ficam, inclusive os repetidos e os recusados, e depois de sete dias eles são
> comprimidos, agrupados por aluno. As tabelas normais guardam os alunos, as aulas e os comandos.
> Para a LGPD, o nome fica separado do histórico, os eventos só têm um pseudônimo, e existe uma
> rota que apaga tudo de um aluno, até o cadastro guardado no broker.

## Cena 8 · Falhas e recuperação (≈ 2 min) — eixo 5
Comece uma aula nova (**Iniciar aula agora**, e de novo `python celulares.py 1 --turma ABC234 --ws`)
e, com ela rodando:

| Ação | Onde olhar | Vai aparecer |
|---|---|---|
| feche a janela do servidor e rode `cd servidor ; python servidor.py --ws` de novo | servidor | `↺ RECUPERADA aula … mensagens relidas do banco` e a aula continua |
| `python travar_banco.py 20` (janela 3, depois que o simulado acabar, ou numa 4ª janela) | servidor | nada de "RECUSADA": as gravações esperam na fila e entram quando o banco volta |
| celular → cartão **Testes de falha** → **Simular queda de rede** por ~30 s, depois desligue | servidor | os heartbeats guardados chegam juntos e são aceitos |
| feche a janela da âncora | servidor | `! ÂNCORA MUDA anc-pc-1` depois de 15 s |

> Agora as falhas. Eu derrubo o servidor no meio da aula e ligo de novo. Ele relê o histórico do
> banco e a aula continua exatamente de onde estava, porque a permanência é calculada a partir do
> histórico. Agora eu congelo o banco por vinte segundos: o servidor continua decidindo, guarda
> as gravações numa fila e grava tudo quando o banco volta. Esse teste ao vivo achou dois
> defeitos, que eu corrigi: com o banco travado, as mensagens ficavam esperando e eram recusadas
> por atraso. Agora isso tem teste automático.
> Sem rede, o celular guarda até seis minutos de heartbeats e manda depois. E se a âncora desliga,
> o servidor avisa que ninguém mais a ouve.

## Cena 9 · Testes (≈ 40 s) — eixo 5
**[na tela: `cd servidor ; python -m pytest testes -q` → 81 passed; `cd ..\app ; npm test` → 38 pass]**

> São oitenta e um testes no servidor e trinta e oito no app: unitários, da regra de presença,
> das assinaturas e dos contratos, e de funcionalidade, como uma aula inteira com dois alunos, o
> servidor reiniciando no meio, o banco fora do ar e a eliminação de um aluno.

## Cena 10 · O que mudou, documentação e limites (≈ 1 min) — eixos 4 e 6
**[na tela: tabela "O que mudou na arquitetura" do README; depois INSTALACAO.md e MANUAL-TECNICO.md]**

> Desde o Marco 3: heartbeat de cinco segundos também em segundo plano, a aula identificada em
> cada mensagem, banco PostgreSQL com recuperação, sensores, o atuador com confirmação, o
> relatório, e a sala preparada para mais de uma âncora. A documentação tem a instalação, do
> computador vazio até a aula rodando, incluindo gerar o aplicativo a partir do código, e o
> manual técnico.
> Os limites que eu declaro: uma âncora só, então sem trilateração; ainda não há regra de acesso
> por tópico no broker; alguém na sala retransmitindo o código ao vivo continua possível; e o
> empréstimo de celular é mitigado, não resolvido. Obrigada, professor.

---

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| App: "Âncora não ouvida" / "Ainda não entrou na sala" | âncora mostra TRANSMITINDO? Bluetooth e localização do celular ligados? Calibrou? |
| App: "O celular não está vendo nenhum aparelho Bluetooth", com tudo permitido | feche o app (tire dos recentes) e abra de novo: na 1ª abertura, depois de dar as permissões, a varredura só volta assim. Antes de gravar, abra o app uma vez |
| Simulado não diz "Entrando na aula que o professor iniciou" | rode logo depois de **Iniciar aula agora** e confira o código da turma |
| Celular para de mandar com a tela apagada | cartão **Tela apagada** ligado? Bateria do app "Sem restrições"? |
| Servidor recusa tudo com TOKEN VENCIDO | relógio do notebook: Sincronizar agora |
| "banco fora do ar" | `.\banco\banco.ps1`; o servidor continua e grava depois |
| "Sem conexão com o broker: o comando não saiu." | hotspot / dados móveis do celular |
| Nada conecta | grave as cenas 3, 7, 8 e 9 com `python celulares.py 2 --ws` no lugar do celular |

## Comandos de prova (se pedirem)

```powershell
cd servidor ; python -m pytest testes -q          # 81 passed
cd ..\app ; npm test                              # 38 pass
cd ..\ataques ; python celulares.py 2 --ws        # aula de 2 min com 2 celulares simulados
```
