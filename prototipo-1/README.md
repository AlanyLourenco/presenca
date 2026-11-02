# Protótipo 1 — o notebook como âncora

Primeiro protótipo com **rádio de verdade**. O notebook anuncia por Bluetooth Low Energy,
como faria uma âncora ESP32 na parede. O celular do estudante mede a intensidade desse sinal
(RSSI, em dBm) e decide se está **a até 1 m do notebook** (na sala) ou mais longe (fora). O
servidor de permanência faz o resto: tolerância, avisos e porcentagem da aula.

Nada do projeto anterior foi alterado: `app/` e `marco-02/` continuam iguais. Esta pasta tem
cópias próprias, e os tópicos MQTT ficam em `ufg/ssu/presenca/alany/proto1/...` para não se
misturar com o Marco 2.

```
prototipo-1/
├── ancora/      o notebook anunciando por Bluetooth (Python + API do Windows)
├── app/         cópia do app, lendo o Bluetooth de verdade (precisa de APK)
├── servidor/    cópia do servidor, com a regra de uma âncora só
├── contrato/    cópia dos contratos (o servidor valida contra eles)
└── gerar-apk.ps1
```

## O que muda em relação ao app do Expo Go

| | App do Expo Go (`app/`) | Protótipo 1 |
|---|---|---|
| Âncora | três, simuladas por controles deslizantes | uma, real: o notebook |
| Sinal | número escolhido na tela | RSSI medido pelo rádio do celular |
| Onde roda | Expo Go | APK instalado (o Expo Go não tem Bluetooth) |
| Dentro/fora | trilateração + polígono no servidor | limiar calibrado a 1 m, decidido no celular |

**Simplificação declarada:** com uma âncora não existe trilateração. A regra vira um raio:
"mais forte que o sinal medido a 1 m é dentro". O projeto rejeita o raio para a sala real
(rádio atravessa parede; uma sala é um polígono). Aqui é o recorte do protótipo.

## Como roda — passo a passo

São três coisas ao mesmo tempo: a âncora e o servidor no notebook, e o app no celular.

### 1. Âncora (Terminal 1)

Ligue o **Bluetooth do notebook** (Configurações > Bluetooth e dispositivos).

```powershell
cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\prototipo-1\ancora"
pip install -r requirements.txt
python ancora.py
```

Deve aparecer `rádio: TRANSMITINDO` e um token novo a cada 12 s.

### 2. Servidor (Terminal 2)

```powershell
cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\prototipo-1\servidor"
pip install -r requirements.txt
python servidor.py
```

Este servidor já fala por WebSocket (`"transporte": "websockets"` no config), sem `--ws`.

### 3. APK (só quando o app mudar)

```powershell
cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\prototipo-1"
powershell -ExecutionPolicy Bypass -File .\gerar-apk.ps1
```

Sai `prototipo-1\presenca-p1.apk`. Passe para o celular (cabo USB, Google Drive, WhatsApp…),
toque no arquivo e permita "instalar apps de fontes desconhecidas" quando o Android pedir.
O app aparece como **Presença P1**, separado do Expo Go.

O APK é autônomo: não precisa de `npx expo start` nem de estar no mesmo Wi-Fi. Só precisa de
internet (para o broker) e do Bluetooth ligado.

### 4. No celular

1. Abra **Presença P1** e permita **Dispositivos próximos** e **Localização** (o Android exige
   as duas para ler anúncios Bluetooth). Deixe a localização do celular ligada.
2. **Área do administrador** → crie a turma (a sala já vem como `sala-pc`) → **Publicar**.
3. **Entrar numa turma** com o código.
4. Na tela da turma aparece o sinal do notebook em dBm e a distância estimada.
5. **Calibrar a 1 m** (na Área do administrador, dentro da turma): fique a 1 m do notebook,
   parada, e toque em **Calibrar** (8 s). O valor é publicado com a turma.
6. Admin → **Iniciar aula agora**. Volte para a turma:
   - perto do notebook → verde, **"Na sala — contando"**;
   - afaste-se mais de 1 m → depois de alguns segundos, **amarelo**: usando a tolerância;
   - fique longe → chegam os avisos (vibração e cartão na tela).

No Terminal 2 o servidor mostra cada mensagem: `na sala` / `fora da sala`.

## Quem calibra

**Só o administrador.** O limiar de 1 m faz parte da turma (`limiar1mDbm` em
`presenca.turma.v1`) e chega ao celular do estudante junto com a grade. Se o próprio
estudante pudesse calibrar, bastaria ficar a 2 m, calibrar, e "2 m" passaria a ser "perto".
Sem calibração, o app do estudante não decide perto nem longe: o servidor recebe
`INDETERMINADA` e não conta nada.

Limite: o RSSI varia de um modelo de celular para outro, e a calibração é feita com o celular
do admin. No protótipo, com um celular só, isso não aparece.

## Os números

| | Valor | Onde |
|---|---|---|
| Distância-limite | 1 m (limiar = mediana do RSSI na calibração do admin) | `app/src/lib/config.ts` |
| Histerese | entra acima do limiar, sai 5 dB abaixo | `HISTERESE_DB` |
| Filtro | mediana dos anúncios dos últimos 2 s | `BLE_JANELA_MS` |
| Âncora calada | 4 s sem anúncio = não ouvida = fora | `BLE_SUMIU_MS` |
| Token da âncora | renova a cada 12 s | `ancora/ancora.py` |
| Aula | 100 s (50 min ÷ escala 30), tolerância 30 s, avisos aos 20 s e 26 s | `servidor/config.exemplo.json` |

**Por que mediana e não média:** o RSSI de Bluetooth oscila 5 a 10 dB de um pacote para o
outro (reflexo, corpo, orientação do celular). Um pacote ruim isolado puxa a média; a mediana
o ignora.

**Limite honesto do "1 m":** RSSI não é régua. A mesma distância dá valores diferentes com o
celular no bolso ou na mão, ou com uma pessoa no meio. Por isso a calibração é feita na
posição de uso, e a fronteira real fica entre uns 0,7 m e 1,5 m.

## Testes

```powershell
cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\prototipo-1\app"
npm test

cd "D:\SOFTWARE PARA COMPUTAÇÃO UBÍQUA\projeto-presenca\prototipo-1\servidor"
python -m pytest testes -q
```
