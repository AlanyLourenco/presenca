# Guia do Marco 3 — para apresentar sozinha (16/10)

Slides: [`apresentacao/Marco3-Slides.pdf`](apresentacao/Marco3-Slides.pdf). Explicação completa: [`documentacao/Marco3-Seguranca.pdf`](documentacao/Marco3-Seguranca.pdf).

## Antes de sair de casa

- [x] `segredos.json` preenchido e `python configurar.py` rodado sem "ATENÇÃO".
- [ ] APK novo instalado no celular (**Presença M3**, ícone separado do P1).
- [ ] Ensaio completo uma vez: âncora + servidor + app + `ataques.py todos`.
- [x] Teste de carga com o broker feito (números já no slide "Quantos").
- [ ] Celular com dados móveis e **hotspot** funcionando: a rede da faculdade bloqueia as
      portas 8883/8084 do broker.

## Na sala — montar (5 min)

1. Ligue o **hotspot do celular** e conecte o notebook nele.
2. Ligue o **Bluetooth** do notebook.
3. Abra **três** janelas do PowerShell. Em todas:

```powershell
cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\marco-03"
```

| Janela | Comando | Deve aparecer |
|---|---|---|
| 1 · âncora | `cd ancora` → `python ancora.py` | `rádio: TRANSMITINDO` e um token a cada 12 s |
| 2 · servidor | `cd servidor` → `python servidor.py` | `Conectado ao s0e8218a…emqxsl.com, porta 8084 (MQTT sobre WebSocket com TLS, usuário presenca-servidor)` e a chave pública |
| 3 · intruso | `cd ataques` | (fica parada até a parte dos ataques) |

Se a janela 2 disser **"O broker RECUSOU a conexão"**: senha errada no `segredos.json`.
Se ficar parada sem "Conectado": a rede bloqueia a porta → confira o hotspot.

## Roteiro

### 1. O protótipo virou o sistema (slides 1–2)
Fale do pedido do professor: o protótipo com o notebook e o celular agora é o oficial.

### 2. O problema (slide 3) — ao vivo
Janela 3: `python ataques.py publico`
Vai aparecer **CONSEGUIU** em laranja e mensagens de terceiros. Fala: *"sem senha, qualquer
um lê e escreve; o wss só cifra o caminho, não diz quem fala."*
(Se a rede bloquear, aparece "a conexão nem abriu": siga para o slide.)

### 3. As camadas (slides 4–8)
Só slides. No slide do **envelope**, se quiser, mostre `servidor/seguranca.py` no VS Code.

### 4. Funcionando (o laço)
1. Celular → **Presença M3** → **Área do administrador** → turma → **Publicar** →
   **Calibrar a 1 m** (parada a 1 m do notebook, 8 s) → **Iniciar aula agora**.
2. **Entrar numa turma** com o código.
3. Na tela da turma, mostre o cartão **Segurança**: "Eu sou tok-…", "Canal: TLS (wss) com
   usuário presenca-app", "Nenhuma mensagem falsa recebida".
4. Janela 2: aparece `+ APARELHO tok-… se identificou (chave …)` e as linhas da aula.
5. Afaste-se mais de 1 m → amarelo (tolerância) → volte.

### 5. Os ataques (slide 9) — ao vivo, com a aula rodando
Janela 3, um por vez, e aponte onde olhar:

| Comando | Olhar em | Vai aparecer |
|---|---|---|
| `python ataques.py senha` | janela 3 | três **BLOQUEADO** e um **CONECTOU** (o certo) |
| `python ataques.py forjar` | janela 2 | `x RECUSADA SEM ASSINATURA`, `IDENTIDADE TROCADA`, `TOKEN VENCIDO` |
| `python ataques.py estado` | celular | "Recusei 2 mensagem(ns) falsa(s)" e a porcentagem **não** vira 100 % |
| `python ataques.py turma` | celular | "Turma recusada: turma assinada por outro administrador" |
| `python ataques.py repetir` | janela 2 | `! REPETIDA` (demora ~1 min: deixe por último ou pule) |

Fecho: na janela 2 digite `p` + Enter → o resumo mostra **"Segurança: recusadas …"**.

### 6. Perguntas do professor (slides 10–13)
- **Quantos aparelhos?** A âncora é farol, sem limite. Números do servidor no slide.
- **E o processo inverso?** `escutar.py` mede (opcional ao vivo:
  `cd ..\ancora` → `python escutar.py`; pare a `ancora.py` antes se o Bluetooth reclamar).
- **Arduino?** Sketch pronto, não testado em placa — diga isso.
- **Distância?** Modelo agora; medição real é o próximo passo.

### 7. Limites e próximos passos (slides 14–15)

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| App: "Âncora não ouvida" | `ancora.py` mostra TRANSMITINDO? Localização do celular ligada? |
| App sem conexão (indicador vermelho) | dados móveis do celular; senha do app (rodar `configurar.py` e gerar APK de novo) |
| Servidor recusa TUDO com TOKEN VENCIDO | relógio do notebook errado: Configurações > Hora > Sincronizar agora |
| Servidor recusa com IDENTIDADE TROCADA o celular de verdade | não deveria: anote e mostre os testes (`python -m pytest testes -q`) |
| Nada conecta | hotspot; se não houver, apresente pelos slides e pelos testes |

## Comandos de prova (se pedirem)

```powershell
cd servidor ; python -m pytest testes -q          # 49 passed
cd ..\app ; npm test                              # 22 pass
cd ..\ataques ; python carga.py 200 --sem-rede    # capacidade do servidor
```
