import Slider from '@react-native-community/slider';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Switch, Text, Vibration, View } from 'react-native';
import { POSICOES, RSSI_MAX, RSSI_MIN, RSSI_NAO_OUVIDA } from '@/lib/config';
import {
  apagarTurma, historico, obterTurma, registrarAula, registrarAviso, salvarTurma, ultimosAvisos,
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
const NOME_ANCORA = ['A', 'B', 'C'];
const NOME_REGIAO = {
  DENTRO_ALCANCE: 'ao alcance das âncoras',
  FORA_ALCANCE: 'fora do alcance',
  INDETERMINADA: 'medindo…',
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
    });
    return () => { clearInterval(t); parar(); };
  }, [codigo, db, recarregar]);

  const aula = turma ? aulaEmAndamento(turma, relogio) : null;
  const ativo = !!aula;

  // Tela acesa durante a aula: o Expo Go pausa o JavaScript em segundo plano.
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

  const ap = useAparelho({ eu, sala: turma?.sala ?? 'sala-204', ativo, aoAviso, aoEncerrar });

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
        <Titulo>Sinal das âncoras da sala</Titulo>
        <Texto suave tamanho={13}>
          Simulado: o Expo Go não dá acesso ao Bluetooth. Estes controles fazem o papel dos
          potenciômetros do ESP32; no app instalado, o valor viria do rádio.
        </Texto>
        <Linha>
          {POSICOES.map((p) => (
            <Chip key={p.nome} texto={p.nome}
                  ativo={p.rssi.every((v, i) => v === ap.rssiAlvo[i])}
                  onPress={() => ap.definirSinal([...p.rssi])} />
          ))}
        </Linha>
        {[0, 1, 2].map((i) => {
          const alvo = ap.rssiAlvo[i];
          const filtrado = ap.leitura.rssi[i];
          return (
            <View key={i}>
              <Text style={{ color: c.texto, fontWeight: '600' }}>
                Âncora {NOME_ANCORA[i]}: {alvo < RSSI_NAO_OUVIDA ? 'não ouvida' : `${num(alvo)} dBm`}
                <Text style={{ color: c.suave, fontWeight: '400' }}>
                  {ativo && filtrado !== null ? `  · média ${num(filtrado, 1)}` : ''}
                </Text>
              </Text>
              <Slider
                minimumValue={RSSI_MIN}
                maximumValue={RSSI_MAX}
                step={1}
                value={alvo}
                onValueChange={(v) => {
                  const novo = [...ap.rssiAlvo];
                  novo[i] = v;
                  ap.definirSinal(novo);
                }}
                minimumTrackTintColor={c.primaria}
                maximumTrackTintColor={c.borda}
                thumbTintColor={c.primaria}
                accessibilityLabel={`Sinal da âncora ${NOME_ANCORA[i]}`}
              />
            </View>
          );
        })}
        <Texto suave tamanho={13}>
          Região de rádio: {ativo ? NOME_REGIAO[ap.leitura.regiao] : '—'} (entra acima de −70 dBm, sai abaixo de −85)
        </Texto>
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
