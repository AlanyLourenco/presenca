# Roteiro de narração — vídeo do Marco 3 (Presença)

Este é o único texto a seguir. Leia de cima para baixo: a ordem é a do vídeo.
Você aparece no quadrado do canto o tempo todo. O que está entre colchetes, **[na tela: …]**,
não é para ler: é só para você saber o que vai aparecer enquanto fala.

Pode falar com as suas palavras. Errou? Repita a frase; eu fico com a última.

---

## 1. Abertura
**[na tela: título "Segurança em quatro camadas" e seu nome]**

Olá, professor. Eu sou a Alany Gabriely, e este é o vídeo do Marco 3 do Presença. O projeto é
individual, então sou só eu aqui.

No Marco 2, o senhor pediu que o protótipo, com o notebook como âncora Bluetooth e um celular de
verdade, virasse o sistema oficial. Foi o que eu fiz. O tema deste marco é segurança: vou mostrar
cada ponto pedido em aula, como eu resolvi e a prova rodando — no celular, nos terminais e no
console do broker.

## 2. O mapa da entrega
**[na tela: lista dos 7 pontos]**

Esta é a lista dos sete pontos anotados para o Marco 3: segurança, que é o tema; canal
criptografado; autenticação MQTT; todo dispositivo tem que dizer quem é; atuação com autenticação;
processo inverso, com produtor e consumidor dos dois lados; e redes de sensores.

Seis estão prontos e testados. A rede de sensores funciona de ponta a ponta, mas com uma âncora
física só; eu explico isso no final.

## 3. Como o sistema funciona
**[na tela: diagrama âncora → celular → broker → servidor]**

A âncora é o notebook anunciando por Bluetooth: ela só transmite, não escuta ninguém. O celular
mede a força desse sinal e decide se está a até um metro. As mensagens passam pelo broker MQTT, e
o servidor calcula a permanência e devolve o estado e os avisos para o celular. A regra de presença
é a mesma do Marco 2. O que mudou é como cada peça prova quem é.

## 4. Do que proteger
**[na tela: os quatro ataques]**

Antes de proteger, eu listei do que proteger. São quatro ataques: alguém no Wi-Fi lendo as
mensagens; alguém entrando no broker e publicando o que quiser; alguém falando em nome de outro
aluno, ou fingindo ser o servidor; e o próprio aluno dizendo que está na sala estando em casa.

## 5. As quatro camadas
**[na tela: as quatro camadas]**

E esta é a resposta: uma camada para cada ataque. TLS, para ninguém ler no caminho. Senha no
broker, para só entrar quem tem. Assinatura, para cada aparelho provar quem é. E o token da âncora,
que prova que o celular está ouvindo a âncora agora.

O ponto principal: a senha do app vai dentro do APK, então todo celular tem a mesma. Ela separa
quem é do sistema de quem é de fora, mas não separa um aluno do outro. Por isso a identidade tem
que estar na mensagem, e não só na conexão.

## 6. Ao vivo: o broker antigo aceita qualquer um
**[na tela: terminal rodando `ataques.py publico` — aparece CONSEGUIU duas vezes]**

Até o Marco 2 eu usava o broker público da HiveMQ. Este é o meu script de ataque contra ele:
conecta sem usuário e sem senha — conseguiu. E publica um heartbeat falso dentro dos meus tópicos —
conseguiu de novo. Qualquer pessoa no mundo pode ler e escrever ali.

## 7. Por que troquei para o EMQX
**[na tela: navegador Chrome, tela "Sobre o Chrome", depois o console do EMQX]**

O HiveMQ com senha deixou de ter plano gratuito, então migrei para o EMQX Cloud Serverless. Estou
no Google Chrome, no console do EMQX. Aqui na visão geral só existem portas cifradas: 8883, MQTT com
TLS, e 8084, WebSocket com TLS. Não há porta sem cifra. E as sessões: duas conectadas agora.

## 8. Ao vivo: autenticação MQTT
**[na tela: lista de usuários do EMQX, depois a lista de clientes conectados]**

Autenticação MQTT: dois usuários, um por papel. Presenca-servidor, só no servidor; presenca-app, em
todos os celulares. As senhas são aleatórias, de vinte caracteres, guardadas fora do git. E aqui os
clientes conectados neste momento: o servidor e o celular, cada um com o seu usuário.

## 9. Ao vivo: o intruso tenta entrar no broker novo
**[na tela: terminal rodando `ataques.py senha` — BLOQUEADO três vezes, CONECTOU no fim]**

Agora o intruso tenta entrar no EMQX. Sem TLS: a conexão nem abre. Com TLS, mas sem senha:
bloqueado. Com a senha errada: bloqueado. E com a senha certa, conecta. Isso prova que quem barra é
a senha.

## 10. A assinatura
**[na tela: animação do par de chaves]**

Agora, "todo dispositivo tem que dizer quem é". Cada aparelho tem um par de chaves Ed25519. A chave
privada é como um carimbo que nunca sai do aparelho. A chave pública vai junto da mensagem e serve
para qualquer um conferir. Se alguém mudar um byte da mensagem, a assinatura não confere.

E o nome do aluno, "tók" com oito caracteres, é calculado da própria chave pública: não precisa de
cadastro, e ninguém usa esse nome sem a chave privada.

## 11. O envelope
**[na tela: o envelope da mensagem]**

Toda mensagem vai neste envelope: quem diz ser, a mensagem de sempre, intacta, e a assinatura. A
assinatura cobre também o tópico, então uma mensagem válida não pode ser copiada para o tópico de
outro aluno ou de outra sala. No servidor, cada heartbeat passa por quatro conferências —
assinatura, formato, nome contra a chave e token — antes de contar um segundo de presença.

## 12. Os quatro dispositivos
**[na tela: celular do aluno, âncora, servidor, celular do admin]**

O celular do aluno assina cada mensagem. A âncora prova com o token. O servidor assina o estado e os
avisos, e o celular confere com a chave fixada no app. E o celular do administrador assina a turma.
No broker, cada conexão diz o seu papel. Em cada mensagem, cada aparelho diz quem é.

## 13. O token da âncora — ao vivo
**[na tela: terminal da âncora, um token novo a cada 12 s]**

Falta um problema: a assinatura prova quem mandou, mas não de onde. A âncora resolve isso. Ela
anuncia um token HMAC, feito com um segredo que só ela e o servidor têm, sobre uma janela de doze
segundos do relógio. Olha aqui: um token, doze segundos depois outro, e outro. Os dois lados
calculam o mesmo valor sem conversar. Quem está em casa não ouve a âncora, então não tem o token.

## 14. Produtor e consumidor
**[na tela: setas indo e voltando entre celular e servidor]**

Isso também responde a dois pedidos: processo inverso e atuação com autenticação. O celular produz
o heartbeat assinado, e o servidor consome e confere. Depois o servidor produz o estado e os avisos,
também assinados, e o celular consome, confere e atua: vibra, notifica e mostra o aviso — mas só
quando a mensagem comprovadamente vem do servidor.

## 15. Ao vivo: a aula funcionando
**[na tela: tela do celular ao lado do terminal do servidor]**

Agora o sistema funcionando. Como administradora, eu publico a turma e calibro a um metro da
âncora. Inicio a aula e entro como aluna: o celular está na sala, contando.

No cartão Segurança aparece o canal, TLS com o usuário presenca-app; quem eu sou, o "tók" e o
começo da minha chave; e nenhuma mensagem falsa recebida.

Agora eu levo o celular para longe da âncora. Ele deixa de ouvir o sinal, entra na tolerância, e o
servidor manda os avisos — assinados — que o celular confere e mostra. Quando a tolerância acaba,
o tempo fora para de contar. Eu volto, e ele volta a contar.

No servidor, o resultado da aula com tudo o que aconteceu, segundo a segundo. Fui reprovada nesta
aula de propósito: fiquei fora mais do que a tolerância, e o sistema registrou exatamente isso.

## 16. Ao vivo: o atacante com a senha do app
**[na tela: terminal do atacante e terminal do servidor lado a lado]**

Agora o atacante tem a senha do app, como se tivesse descompilado o APK. Com ela, ele entra no
broker. Primeiro ele escuta e acha um aluno. Manda um heartbeat sem assinatura: recusado. Assina
com a chave dele, mas dizendo ser outro aluno: identidade trocada. Assina como ele mesmo, mas de
casa, com um token inventado: token vencido. Nenhum segundo de presença foi somado.

## 17. Ao vivo: o caminho de volta
**[na tela: tela do celular, cartão Segurança]**

E o caminho de volta. O atacante manda ao celular um estado falso: presente, cem por cento. O
celular recusou: a porcentagem não mudou. Depois, uma turma falsa com o limiar em menos cem dBm,
que faria todo mundo parecer perto, até de casa. Recusada: não é a chave do administrador que eu
guardei quando entrei na turma. E o cartão Segurança mostra as duas recusas, com o motivo.

## 18. Rede de sensores e quantos aparelhos
**[na tela: várias âncoras e celulares; número de capacidade]**

Redes de sensores. Cada celular é um sensor, medindo o sinal com o próprio rádio; as âncoras são
faróis fixos; e o servidor junta tudo, com uma sessão por aluno. Hoje funciona com uma âncora real,
o meu celular e celulares simulados no teste de carga, cada um com a sua chave. O formato já aceita
três âncoras; o que falta são as âncoras físicas.

E quantos aparelhos? A âncora é um farol, então não há limite nela. O limite que eu medi está no
broker gratuito: umas onze mensagens por segundo por conexão. Com um heartbeat por minuto, na aula
real, isso dá uns seiscentos e cinquenta celulares por conexão do servidor. Para mais, várias
cópias do servidor dividindo as mensagens. O sketch para ESP32 também está pronto, mas não foi
testado em placa, porque eu não tenho ESP32.

## 19. Ao vivo: testes
**[na tela: 49 testes do servidor e 22 do app passando]**

Tudo o que eu mostrei também está coberto por testes automáticos: quarenta e nove no servidor e
vinte e dois no app, todos passando.

## 20. Limites e fecho
**[na tela: a lista dos 7 pontos, todos marcados]**

Os limites: a chave fica protegida pelo Keystore, mas num celular com root dá para extrair. A senha
do app está no APK, e é exatamente por isso que existe a assinatura. O próximo passo é restringir
os tópicos por usuário no EMQX.

Então, o que este marco entrega: segurança em quatro camadas; canal cifrado; autenticação no
broker; todo dispositivo provando quem é; atuação só com mensagem autenticada, com produtor e
consumidor dos dois lados; e a rede de sensores funcionando com uma âncora. Obrigada, professor.
