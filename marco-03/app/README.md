# Presença M3 — o app do estudante (Marco 3)

App React Native (Expo SDK 57) do celular do estudante e do administrador da turma. Mede o
sinal Bluetooth da âncora, decide se está a até 1 m, manda o heartbeat **assinado** e só
aceita estado, avisos e turma **assinados por quem deveria**. Por usar Bluetooth, roda como
**APK** (não no Expo Go). Como gerar e usar: [`../README.md`](../README.md).

| Arquivo | O que faz |
|---|---|
| `src/lib/assinatura.ts` | envelope `seguranca.envelope.v1`: assina e confere (Ed25519); pseudônimo = hash da chave |
| `src/lib/identidade.ts` | par de chaves do aparelho, guardado no armazenamento seguro |
| `src/lib/mqtt.ts` | conexão com o broker: `wss://` (TLS) com usuário e senha |
| `src/lib/ble.ts` | varredura Bluetooth; lê o anúncio `PRS1` e o token da âncora |
| `src/lib/aparelho.ts` | filtro do sinal, limiar de 1 m, heartbeat `presenca.heartbeat.v2` com o token |
| `src/lib/usar-aparelho.ts` | laço da aula: assina o heartbeat, confere estado e avisos do servidor |
| `src/lib/rede-turma.ts` | turma assinada pelo admin; o aluno fixa a chave do admin no pareamento |
| `src/lib/segredos.ts` | **gerado** por `../configurar.py`; fica fora do git |
| `src/app/turma/[codigo].tsx` | tela da turma, com o cartão **Segurança** |
| `plugins/ble-sem-never-for-location.js` | ajuste do Android para não esconder anúncios de farol |

```powershell
npm install --legacy-peer-deps
npm test             # 22 testes (inclui assinatura conferida contra o Python)
npm run typecheck
```
