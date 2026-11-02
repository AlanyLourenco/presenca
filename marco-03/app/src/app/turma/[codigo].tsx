import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Switch, Text, Vibration, View } from 'react-native';
import { DISTANCIA_LIMITE_M, HISTERESE_DB, MQTT_USUARIO, SALA_PADRAO } from '@/lib/config';
import {
  apagarTurma, historico, obterTurma, registrarAula, registrarAviso, salvarTurma,
  ultimosAvisos,
  type TurmaLocal,
} from '@/lib/db';
import { minhaIdentidade, type Eu } from '@/lib/identidade';
import { notificar, prepararNotificacoes } from '@/lib/notificacoes';
import { acompanharTurma } from '@/lib/rede-turma';
import { aulaEmAndamento, DIAS, proximaAula } from '@/lib/turma';
import { useAparelho, type AvisoServidor, type EstadoServidor } from '@/lib/usar-aparelho';
import { Botao, Cartao, Chip, IndicadorConexao, Linha, Tela, Texto, Titulo, estilos } from '@/ui/componentes';
import { espaco, useCores, type Cores } from '@/ui/tema';

const PRESENCA_MINIMA = 75;   // % — o mesmo do servidor
const NOME_REGIAO = {
  DENTRO_ALCANCE: `perto (até ${DISTANCIA_LIMITE_M} m) — na sala`,
  FORA_ALCANCE: `longe (mais de ${DISTANCIA_LIMITE_M} m) — fora da sala`,
  INDETERMINADA: 'medindo…',
};
const SEM_CALIBRAR = 'o administrador ainda não calibrou a âncora — sem isso o app não sabe o que é perto';
const NOME_BLE = {
  'iniciando': 'ligando o Bluetooth…',
  'sem-permissao': 'sem permissão para usar o Bluetooth — libere em Configurações > Apps > Presença M3',
  'desligado': 'o Bluetooth do celular está desligado',
  'escutando': 'escutando a âncora',
  'erro': 'não foi possível iniciar a varredura Bluetooth',
};
const NOME_ANOMALIA = { 'duplicata': 'repetida', 'fora-de-ordem': 'fora de ordem', 'salto': 'salto', 'nenhuma': '' };

const num = (x: number, casas = 0) => x.toFixed(casas).replace('.', ',');

export default function AulaDoEstudante() {
  const { codigo } = useLocalSearchParams<{ codigo: string }>();
  const db = useSQLiteContext();
  const c = useCores();
  const [turma, setTurma] = useState<TurmaLocal | null>(null);
  const [eu, setEu] = useState<Eu | null>(null);
  const [relogio, setRelogio] = useState(new Date());
  const [avisos, setAvisos] = useState<{ aviso_id: string; texto: string; recebido_em: number }[]>([]);
  const [aulas, setAulas] = useState<{ id: number; encerrada_em: number; percentual: number }[]>([]);
  const [avisoNaTela, setAvisoNaTela] = useState<string | null>(null);
  const [turmaRecusada, setTurmaRecusada] = useState('');

  const recarregar = useCallback(async () => {
    setTurma(await obterTurma(db, codigo, 'aluno'));
    setAvisos(await ultimosAvisos(db, codigo));
    setAulas(await historico(db, codigo));
  }, [db, codigo]);

  useEffect(() => {
    recarregar();
    minhaIdentidade().then(setEu);
    prepararNotificacoes();
    const t = setInterval(() => setRelogio(new Date()), 1000);
    // O admin pode mudar a grade ou iniciar uma aula agora: grava e mostra.
    const parar = acompanharTurma(codigo, async (nova) => {
      await salvarTurma(db, nova, 'aluno', nova.publicadoEmMs);
      setTurma(await obterTurma(db, codigo, 'aluno'));
    }, setTurmaRecusada);
    return () => { clearInterval(t); parar(); };
  }, [codigo, db, recarregar]);

  const aula = turma ? aulaEmAndamento(turma, relogio) : null;
  const ativo = !!aula;

  // Tela acesa durante a aula: em segundo plano o JavaScript pausa.
  useEffect(() => {
    if (!ativo) return;
    activateKeepAwakeAsync('aula');
    return () => { deactivateKeepAwake('aula'); };
  }, [ativo]);

  const aoAviso = useCallback(async (a: AvisoServidor) => {
    if (!(await registrarAviso(db, codigo, a))) return;      // já mostrado: não toca de novo
    setAvisoNaTela(a.texto);
    Vibration.vibrate([0, 400, 200, 400]);
    notificar(a.tipo === 'FIM_DA_AULA' ? 'Fim da aula' : 'Presença', a.texto);
    setAvisos(await ultimosAvisos(db, codigo));
  }, [db, codigo]);

  const aoEncerrar = useCallback(async (e: EstadoServidor) => {
    await registrarAula(db, codigo, e);
    setAulas(await historico(db, codigo));
  }, [db, codigo]);

  // O limiar de 1 m vem da turma, calibrado pelo administrador. O estudante
  // não calibra: se pudesse, bastaria calibrar de longe para ficar "perto".
  const limiar = turma?.limiar1mDbm ?? null;
  const ap = useAparelho({ eu, sala: turma?.sala ?? SALA_PADRAO, ativo, limiar, aoAviso, aoEncerrar });

  if (!turma) return null;

  const prox = proximaAula(turma.periodos, relogio);

  function sair() {
    Alert.alert('Sair da turma?', 'Para voltar, será preciso o código ou o QR de novo.', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Sair', style: 'destructive', onPress: async () => {
        await apagarTurma(db, codigo, 'aluno');
        router.back();
      } },
    ]);
  }

  return (
    <Tela>
      <Stack.Screen options={{ title: turma.nome }} />
      <View style={{ gap: espaco.xs }}>
        <Texto suave>{turma.sala} · código {turma.codigo}</Texto>
        <IndicadorConexao />
      </View>

      {/* ---------------- situação ---------------- */}
      <Situacao c={c} ativo={ativo} ap={ap} aula={aula} prox={prox} />

      {avisoNaTela && (
        <Cartao estilo={{ borderColor: c.tolerancia, borderWidth: 2 }}>
          <Titulo>Aviso</Titulo>
          <Texto>{avisoNaTela}</Texto>
          <Botao titulo="Entendi" tipo="secundario" onPress={() => setAvisoNaTela(null)} />
        </Cartao>
      )}

      {/* ---------------- sinal ---------------- */}
      <Cartao>
        <Titulo>Âncora: o notebook</Titulo>
        <Texto suave tamanho={13}>{NOME_BLE[ap.estadoBle]}</Texto>
        {ap.leitura.rssi === null ? (
          <>
            <Text style={{ color: c.fora, fontSize: 16, fontWeight: '700' }}>Âncora não ouvida</Text>
            {ap.estadoBle === 'escutando' && (
              <Texto tamanho={14}>
                {ap.leitura.qualquerPorSegundo > 0
                  ? `O Bluetooth do celular está funcionando (vê ${num(ap.leitura.qualquerPorSegundo)} anúncios/s de outros aparelhos), mas nenhum é a âncora. Confira se o ancora.py mostra TRANSMITINDO.`
                  : 'O celular não está vendo nenhum aparelho Bluetooth. Ligue a LOCALIZAÇÃO do celular e confira as permissões do app.'}
              </Texto>
            )}
          </>
        ) : (
          <>
            <Text style={[estilos.numeroGrande, { color: c.texto }]}>{num(ap.leitura.rssi)} dBm</Text>
            {ap.leitura.distancia !== null && (
              <Texto>
                Distância estimada: <Text style={{ fontWeight: '700' }}>{num(ap.leitura.distancia, 1)} m</Text>
              </Texto>
            )}
          </>
        )}
        <Text style={{ color: ap.leitura.regiao === 'DENTRO_ALCANCE' ? c.presente : ap.leitura.regiao === 'FORA_ALCANCE' ? c.fora : c.tolerancia,
                       fontWeight: '700', fontSize: 15 }}>
          {limiar === null && ap.leitura.rssi !== null ? SEM_CALIBRAR : NOME_REGIAO[ap.leitura.regiao]}
        </Text>
        <Texto suave tamanho={12}>
          âncora: {num(ap.leitura.porSegundo)} anúncios/s · todos os aparelhos: {num(ap.leitura.qualquerPorSegundo)}/s
          {ap.leitura.token ? ` · token ${ap.leitura.token}` : ''}
          {limiar === null ? ' · sem calibração' : ` · limiar ${limiar} dBm (definido pelo admin), sai ${HISTERESE_DB} dB abaixo`}
        </Texto>
      </Cartao>

      {/* ---------------- segurança (Marco 3) ---------------- */}
      <Cartao>
        <Titulo>Segurança</Titulo>
        <Texto tamanho={14}>
          Canal: TLS (wss) com usuário <Text style={{ fontWeight: '700' }}>{MQTT_USUARIO}</Text>
        </Texto>
        {eu && (
          <Texto tamanho={14}>
            Eu sou <Text style={{ fontWeight: '700' }}>{eu.aluno}</Text> · chave {eu.chavePublica.slice(0, 12)}…
          </Texto>
        )}
        <Texto suave tamanho={12}>
          Cada mensagem sai assinada com a chave deste celular e leva o token que a âncora anuncia agora.
          Só aceito estado e avisos assinados pelo servidor.
        </Texto>
        <Text style={{ color: ap.recusadas.total || turmaRecusada ? c.fora : c.presente, fontWeight: '700', fontSize: 14 }}>
          {ap.recusadas.total
            ? `Recusei ${ap.recusadas.total} mensagem(ns) falsa(s) — última: ${ap.recusadas.motivo}`
            : 'Nenhuma mensagem falsa recebida'}
        </Text>
        {!!turmaRecusada && (
          <Text style={{ color: c.fora, fontWeight: '700', fontSize: 14 }}>Turma recusada: {turmaRecusada}</Text>
        )}
      </Cartao>

      {/* ---------------- testes de falha ---------------- */}
      {ativo && (
        <Cartao>
          <Titulo>Testes de falha</Titulo>
          <Texto suave tamanho={13}>
            Enviadas: {ap.envio.sequencia} · guardadas sem rede: {ap.envio.fila}
            {ap.envio.descartados ? ` · descartadas: ${ap.envio.descartados}` : ''}
          </Texto>
          <Linha gap={espaco.m}>
            <Switch value={ap.redeCaida} onValueChange={ap.alternarRede} />
            <Texto>Simular queda de rede</Texto>
          </Linha>
          <Botao
            titulo={`Enviar mensagem ${NOME_ANOMALIA[ap.proximaAnomalia]}`}
            tipo="secundario"
            onPress={() => ap.armarAnomalia()}
          />
        </Cartao>
      )}

      {/* ---------------- avisos e histórico ---------------- */}
      {avisos.length > 0 && (
        <Cartao>
          <Titulo>Últimos avisos</Titulo>
          {avisos.map((a) => (
            <Texto key={a.aviso_id} tamanho={14}>
              <Text style={{ color: c.suave }}>{new Date(a.recebido_em).toTimeString().slice(0, 5)}  </Text>
              {a.texto}
            </Texto>
          ))}
        </Cartao>
      )}
      {aulas.length > 0 && (
        <Cartao>
          <Titulo>Aulas registradas neste aparelho</Titulo>
          {aulas.map((a) => (
            <Texto key={a.id} tamanho={14}>
              {new Date(a.encerrada_em).toLocaleDateString('pt-BR')} {new Date(a.encerrada_em).toTimeString().slice(0, 5)} —{' '}
              <Text style={{ color: a.percentual >= PRESENCA_MINIMA ? c.presente : c.fora, fontWeight: '700' }}>
                {num(a.percentual)} %
              </Text>
            </Texto>
          ))}
        </Cartao>
      )}

      <Botao titulo="Sair da turma" tipo="perigo" onPress={sair} />
    </Tela>
  );
}

function Situacao({ c, ativo, ap, aula, prox }: {
  c: Cores; ativo: boolean; ap: ReturnType<typeof useAparelho>;
  aula: ReturnType<typeof aulaEmAndamento>; prox: Date | null;
}) {
  if (!ativo) {
    const e = ap.estado;
    return (
      <Cartao>
        <Titulo>Sem aula agora</Titulo>
        {e?.encerrada && (
          <Texto>
            Última aula: {num(e.percentual)} % —{' '}
            {e.percentual >= PRESENCA_MINIMA ? 'presença registrada' : `abaixo de ${PRESENCA_MINIMA} %`}
          </Texto>
        )}
        <Texto suave>
          {prox ? `Próxima: ${DIAS[prox.getDay()]}, ${prox.toLocaleDateString('pt-BR')} às ${prox.toTimeString().slice(0, 5)}. `
                : 'Nenhum horário na grade desta turma. '}
          O app começa a contar sozinho quando a aula começar — deixe-o aberto.
        </Texto>
      </Cartao>
    );
  }

  const restante = aula ? Math.max(0, Math.round((aula.fimMs - ap.agora) / 1000)) : 0;
  const rodape = aula?.tipo === 'demonstracao'
    ? `Aula de demonstração · termina em ${restante} s`
    : `Aula até ${aula && new Date(aula.fimMs).toTimeString().slice(0, 5)}`;

  if (!ap.estadoValido || !ap.estado) {
    return (
      <Cartao>
        <Titulo>{ap.redeCaida ? 'Sem rede' : 'Esperando o servidor…'}</Titulo>
        <Texto suave>
          {ap.redeCaida
            ? `As medições ficam guardadas (${ap.envio.fila}) e seguem quando a rede voltar.`
            : 'As medições estão sendo enviadas. Se nada aparecer, confira se o servidor está rodando.'}
        </Texto>
        <Texto suave tamanho={13}>{rodape}</Texto>
      </Cartao>
    );
  }

  const e = ap.estado;
  const cor = e.estado === 'PRESENTE' ? c.presente : e.estado === 'AUSENCIA_TOLERADA' ? c.tolerancia : c.fora;
  const titulo = e.encerrada ? 'Aula encerrada'
    : e.estado === 'PRESENTE' ? 'Na sala — contando'
    : e.estado === 'AUSENCIA_TOLERADA' ? 'Fora da sala — usando a tolerância'
    : e.acumuladoS > 0 ? 'Fora — este tempo não conta' : 'Ainda não entrou na sala';
  return (
    <Cartao estilo={{ borderColor: cor, borderWidth: 2 }}>
      <Text style={{ color: cor, fontSize: 20, fontWeight: '800' }}>{titulo}</Text>
      <Text style={[estilos.numeroGrande, { color: c.texto }]}>{num(e.percentual)} %</Text>
      <View style={{ height: 10, borderRadius: 5, backgroundColor: c.borda, overflow: 'hidden' }}>
        <View style={{ width: `${Math.min(100, e.percentual)}%`, height: '100%', backgroundColor: cor }} />
        <View style={{ position: 'absolute', left: `${PRESENCA_MINIMA}%`, top: 0, bottom: 0, width: 2, backgroundColor: c.texto }} />
      </View>
      <Texto suave tamanho={13}>
        Contou {num(e.acumuladoS, 1)} s de {num(e.tempoAulaS, 1)} s de aula · precisa de {PRESENCA_MINIMA} %
      </Texto>
      <Texto>
        Tolerância restante: <Text style={{ fontWeight: '700' }}>{num(e.orcamentoRestanteS, 1)} s</Text>
      </Texto>
      <Texto suave tamanho={13}>{rodape}</Texto>
    </Cartao>
  );
}
