# Presença P1 — app do protótipo 1

Cópia do app de `../../app/` em que o sinal da âncora vem do **Bluetooth de verdade**: o
notebook anuncia (`../ancora/ancora.py`) e o celular mede o RSSI. Por usar Bluetooth, roda
como **APK** e não no Expo Go. Como gerar e usar: [`../README.md`](../README.md).

O que mudou em relação ao app original:

| Arquivo | Mudança |
|---|---|
| `src/lib/ble.ts` | **novo** — permissões, varredura contínua, lê o anúncio `PRS1` da âncora |
| `src/lib/aparelho.ts` | `MedidorBle`: mediana dos últimos 2 s, limiar calibrado a 1 m, histerese de 5 dB, âncora calada = fora |
| `src/lib/usar-aparelho.ts` | escuta o Bluetooth o tempo todo e calibra; heartbeat só na aula |
| `src/lib/config.ts` | tópicos em `.../proto1/`, sala `sala-pc` com a âncora `anc-pc-1`, constantes do Bluetooth |
| `src/lib/db.ts` | tabela `ajustes` (guarda a calibração) |
| `src/app/turma/[codigo].tsx` | cartão do sinal real + calibração, no lugar dos controles deslizantes |
| `plugins/ble-sem-never-for-location.js` | **novo** — tira a marca que faz o Android esconder anúncios de farol |
| `app.json` | nome **Presença P1**, pacote `br.ufg.presenca.p1`, plugin do Bluetooth |

Testes: `npm test` (inclui os do `MedidorBle`). Typecheck: `npm run typecheck`.
