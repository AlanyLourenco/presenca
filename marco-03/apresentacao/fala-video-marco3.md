# Fala do vídeo do Marco 3 — Presença

## 1. Abertura

Olá, professor. Eu sou a Alany Gabriely, e este é o vídeo do Marco 3 do Presença. O projeto é individual, por isso sou só eu no vídeo.

No Marco 2, o senhor pediu que o protótipo, com o notebook como âncora Bluetooth e o celular de verdade, virasse o sistema oficial. Foi o que eu fiz. O tema deste marco é segurança: vou mostrar cada ponto pedido em aula, como resolvi e a prova rodando.

## 2. O mapa da entrega

Esta tabela é o mapa do vídeo. São os sete pontos anotados para o Marco 3.

Segurança, que é o tema; canal criptografado; autenticação M Q T T; todo dispositivo tem que falar quem é; atuação com autenticação; o processo inverso, com produtor e consumidor dos dois lados; e redes de sensores.

Seis estão prontos e testados. A rede de sensores funciona de ponta a ponta, mas com uma âncora física só; eu explico isso no final.

## 3. Como o sistema funciona

Rapidamente, como funciona. A âncora é o notebook anunciando por Bluetooth: ela só transmite, não escuta ninguém. O celular mede a força desse sinal e decide se está a até um metro. As mensagens passam pelo broker M Q T T, e o servidor calcula a permanência e devolve o estado e os avisos para o celular.

A regra de presença é a mesma do Marco 2. O que mudou é como cada peça prova quem é.

## 4. Do que proteger

Antes de proteger, eu listei do que proteger. São quatro ataques, de fora para dentro: alguém no Wi-Fi lendo as mensagens; alguém entrando no broker e publicando o que quiser; alguém falando em nome de outro aluno, ou fingindo ser o servidor; e o próprio aluno dizendo que está na sala estando em casa.

## 5. As quatro camadas

E esta é a resposta inteira: quatro camadas, uma para cada ataque. T L S, para ninguém ler no caminho. Senha no broker, para só entrar quem tem. Assinatura, para cada aparelho provar quem é. E o token da âncora, que prova que o celular está ouvindo a âncora agora.

O ponto principal: a senha do app vai dentro do A P K, então todo celular tem a mesma. Ela separa quem é do sistema de quem é de fora, mas não separa um aluno do outro. Por isso a identidade tem que estar na mensagem, e não só na conexão.

## 6. O problema do broker público

Até o Marco 2 eu usava o broker público da HiveMQ. Este é o meu script de ataque contra ele: conecta sem usuário nem senha, publica um heartbeat falso dentro dos meus tópicos, e o broker aceita.

E mesmo usando W S S, que é cifrado, a cifra só protege o caminho; ela não diz quem está falando.

## 7. Por que EMQX

O HiveMQ com senha deixou de ter plano gratuito, então migrei para o EMQX Cloud Serverless: gratuito, com T L S obrigatório e senha por usuário. Para o código, trocar de broker é trocar o endereço.

## 8. Canal criptografado

Canal criptografado: T L S, o mesmo cadeado do HTTPS. Ele cifra tudo, então quem está na rede não vê nem a senha. E o certificado prova que o broker é mesmo o broker.

Neste print do console do EMQX, só existem as portas cifradas, oito oito oito três e oito zero oito quatro. E no código não há caminho sem T L S.

## 9. Autenticação M Q T T

Autenticação M Q T T: dois usuários, um por papel. O usuário presença servidor, só no servidor; o usuário presença app, em todos os celulares. As senhas são aleatórias, de vinte caracteres, guardadas fora do git.

Aqui está o cadastro no EMQX, e aqui as duas conexões durante o ensaio, cada uma com o seu usuário.

## 10. Ao vivo: o intruso tenta entrar

Agora o intruso tenta entrar no broker novo. Sem T L S: a porta nem existe. Com T L S, mas sem senha: recusado. Com a senha errada: recusado. E com a senha certa, conecta. Isso prova que quem barra é a senha.

## 11. A assinatura

Agora, "todo dispositivo tem que falar quem é". Cada aparelho tem um par de chaves Ed dois cinco cinco um nove.

A chave privada é como um carimbo que nunca sai do aparelho. A chave pública vai junto da mensagem e serve para qualquer um conferir: sim, ou recusa. Se alguém mudar um byte da mensagem, a assinatura não confere.

E o nome do aluno, "tók" com oito caracteres, é calculado da própria chave pública: não precisa de cadastro, e ninguém usa esse nome sem a chave privada.

## 12. O envelope

Toda mensagem vai neste envelope. Quem diz ser; a mensagem de sempre, intacta; e a assinatura.

A assinatura cobre também o tópico, então uma mensagem válida não pode ser copiada para o tópico de outro aluno, ou de outra sala. No servidor, cada heartbeat passa por quatro conferências, assinatura, formato, nome contra a chave e token, antes de contar um segundo de presença.

## 13. Os quatro dispositivos

Os quatro dispositivos. O celular do aluno assina cada mensagem. A âncora prova com o token. O servidor assina o estado e os avisos, e o celular confere com a chave fixada no app. E o celular do administrador assina a turma.

No broker, cada conexão diz o seu papel. Em cada mensagem, cada aparelho diz quem é.

## 14. O token da âncora

Falta um problema: a assinatura prova quem mandou, mas não de onde. A âncora resolve isso. Ela anuncia um token agá mac, feito com um segredo que só ela e o servidor têm, sobre uma janela de doze segundos do relógio. Os dois calculam o mesmo valor sem conversar.

## 15. Ao vivo: a âncora

Aqui está a âncora rodando: um token, doze segundos depois outro, e outro. O celular só repassa o que ouviu. Quem está em casa não ouve a âncora, então não tem o token.

## 16. Produtor e consumidor

Isso também responde a dois pedidos: processo inverso, e atuação com autenticação. Aqui os dois lados produzem e consomem.

O celular produz o heartbeat assinado, e o servidor consome e confere. Depois o servidor produz o estado e os avisos, também assinados, e o celular consome, confere e atua: vibra, notifica e mostra o aviso, mas só quando a mensagem comprovadamente vem do servidor.

## 17. Ao vivo: abrindo a aula

Agora o sistema funcionando. Vou abrir a aula pelo administrador, calibrar a um metro da âncora e entrar na turma como aluna.

No cartão Segurança aparece quem eu sou, "tók" e o começo da minha chave; o canal, T L S com o usuário presença app; e nenhuma mensagem falsa recebida.

E no servidor apareceu o meu aparelho se identificando, com a chave dele. Daqui em diante, cada mensagem chega assinada.

## 18. Ao vivo: o atacante com a senha do app

Agora o atacante tem a senha do app, como se tivesse descompilado o A P K. Com ela, ele entra no broker. Vamos ver o que o servidor faz.

Sem assinatura: recusado. Assinando com a própria chave, mas dizendo ser outro aluno: identidade trocada. Assinando como ele mesmo, mas de casa, com um token inventado: token vencido. Nenhum segundo de presença foi somado.

## 19. Ao vivo: o caminho de volta

E o caminho de volta. O atacante publica um estado falso dizendo "presente, cem por cento". O celular recusou: a porcentagem não mudou, e o cartão conta as mensagens falsas recusadas.

Agora uma turma falsa, com o limiar em menos cem dê bê eme, que faria todo mundo parecer perto, até de casa. O celular recusou: não é a chave do administrador que eu guardei quando entrei na turma.

E o resumo do servidor conta as mensagens recusadas, com o motivo de cada uma.

## 20. Rede de sensores

Redes de sensores. Cada celular é um sensor, medindo o sinal com o próprio rádio; as âncoras são faróis fixos; e o servidor junta tudo, com uma sessão por aluno.

Hoje funciona com uma âncora real, o meu celular e celulares simulados no teste de carga, cada um com a sua chave. O formato já aceita três âncoras; o que falta são as três âncoras físicas.

## 21. Quantos aparelhos

E quantos aparelhos? A âncora é um farol, então não há limite nela. O limite que eu medi está no broker gratuito: umas onze mensagens por segundo por conexão. Com um heartbeat por minuto, na aula real, isso dá uns seiscentos e cinquenta celulares por conexão do servidor. Para mais, várias cópias do servidor dividindo as mensagens.

O sketch para ESP trinta e dois também está pronto, mas não foi testado em placa, porque eu não tenho ESP trinta e dois.

## 22. Testes

Tudo o que eu mostrei também está coberto por testes automáticos: quarenta e nove no servidor e vinte e dois no app, todos passando.

## 23. Limites

Os limites: a chave fica cifrada pelo Keystore, mas num celular com root dá para extrair. A senha do app está no A P K, e é exatamente por isso que existe a assinatura. O próximo passo é restringir os tópicos por usuário no EMQX.

## 24. Fecho

Então, o que este marco entrega: segurança em quatro camadas; canal cifrado; autenticação no broker; todo dispositivo provando quem é; atuação só com mensagem autenticada, e produtor e consumidor dos dois lados; e a rede de sensores funcionando com uma âncora.

Obrigada, professor.
