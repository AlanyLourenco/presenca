import { Redirect, router, Stack, useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { Alert, Pressable, Text, View } from 'react-native';
import QRCode from 'react-native-qrcode-svg';
import { CALIBRACAO_MS, DISTANCIA_LIMITE_M, DURACAO_AULA_DEMO_S, SALAS, topicos } from '@/lib/config';
import { apagarTurma, obterTurma, salvarTurma, type TurmaLocal } from '@/lib/db';
import { mqtt } from '@/lib/mqtt';
import { publicarTurma } from '@/lib/rede-turma';
import { adminLiberado } from '@/lib/sessao-admin';
import { useAncora } from '@/lib/usar-ancora';
import {
  aulaEmAndamento, conteudoQr, DIAS, horaValida, novaAulaAgora, periodoValido, type Periodo,
} from '@/lib/turma';
import { Botao, Campo, Cartao, Chip, estilos, IndicadorConexao, Linha, Tela, Texto, Titulo } from '@/ui/componentes';
import { espaco, useCores } from '@/ui/tema';

/** "1930" → "19:30" enquanto digita. */
function mascaraHora(t: string) {
  const d = t.replace(/\D/g, '').slice(0, 4);
  return d.length > 2 ? `${d.slice(0, 2)}:${d.slice(2)}` : d;
}

const ordenar = (ps: Periodo[]) =>
  [...ps].sort((a, b) => a.dia - b.dia || a.inicio.localeCompare(b.inicio));

export default function EditarTurma() {
  const { codigo } = useLocalSearchParams<{ codigo: string }>();
  const db = useSQLiteContext();
  const c = useCores();
  const [t, setT] = useState<TurmaLocal | null>(null);
  const [dia, setDia] = useState(new Date().getDay());
  const [inicio, setInicio] = useState('');
  const [fim, setFim] = useState('');
  const [erro, setErro] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [agora, setAgora] = useState(Date.now());
  const [msgCalibracao, setMsgCalibracao] = useState('');
  // O admin também escuta a âncora: é ele quem define o que é 1 m.
  const ancora = useAncora(t?.limiar1mDbm ?? null);

  useEffect(() => {
    obterTurma(db, codigo, 'admin').then(setT);
    const r = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(r);
  }, [db, codigo]);

  if (!adminLiberado()) return <Redirect href="/admin" />;
  if (!t) return null;

  /** Toda alteração fica salva no celular e marcada como não publicada. */
  async function alterar(mudanca: Partial<TurmaLocal>) {
    const nova = { ...t!, ...mudanca, publicada: false };
    setT(nova);
    setMensagem('');
    await salvarTurma(db, nova, 'admin', null);
  }

  async function publicar(turma = t!) {
    const quando = await publicarTurma(turma);
    if (quando === null) {
      setMensagem('Sem conexão com o servidor. A turma ficou salva neste celular; publique quando a internet voltar.');
      return false;
    }
    await salvarTurma(db, turma, 'admin', quando);
    setT({ ...turma, publicada: true, publicadoEmMs: quando });
    setMensagem('Publicada. Os estudantes já recebem esta versão.');
    return true;
  }

  function adicionarPeriodo() {
    const p = { dia, inicio, fim };
    if (!horaValida(inicio) || !horaValida(fim)) return setErro('Use horas no formato 19:00.');
    if (!periodoValido(p)) return setErro('O fim tem de ser depois do início.');
    setErro('');
    setInicio('');
    setFim('');
    alterar({ periodos: ordenar([...t!.periodos, p]) });
  }

  const demo = t.aulaAgora && aulaEmAndamento({ periodos: [], aulaAgora: t.aulaAgora }, new Date(agora));
  const restante = demo ? Math.ceil((demo.fimMs - agora) / 1000) : 0;

  async function iniciarDemo() {
    const nova = { ...t!, aulaAgora: novaAulaAgora(Date.now()) };
    await salvarTurma(db, nova, 'admin', null);
    await publicar(nova);
  }

  async function encerrarDemo() {
    const nova = { ...t!, aulaAgora: null };
    await salvarTurma(db, nova, 'admin', null);
    await publicar(nova);
  }

  async function calibrar() {
    setMsgCalibracao('');
    const novo = await ancora.calibrar();
    if (novo === null) {
      setMsgCalibracao('Quase nenhum sinal da âncora chegou. Confira se o ancora.py mostra TRANSMITINDO.');
      return;
    }
    const nova = { ...t!, limiar1mDbm: novo };
    await salvarTurma(db, nova, 'admin', null);
    const ok = await publicar(nova);
    setMsgCalibracao(`A ${DISTANCIA_LIMITE_M} m o sinal é ${novo} dBm. `
      + (ok ? 'Publicado: os estudantes já usam este valor.' : 'Salvo; publique quando a internet voltar.'));
  }

  function apagar() {
    Alert.alert('Apagar a turma?', 'Os estudantes deixam de receber a grade. O código não poderá ser usado de novo.', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Apagar', style: 'destructive', onPress: async () => {
        // Mensagem retida vazia apaga a turma do broker.
        mqtt.publicar(topicos.turma(codigo), '', { retido: true, qos: 1 });
        await apagarTurma(db, codigo, 'admin');
        router.back();
      } },
    ]);
  }

  return (
    <Tela>
      <Stack.Screen options={{ title: t.nome }} />
      <IndicadorConexao />

      {/* ---------------- código e QR ---------------- */}
      <Cartao estilo={{ alignItems: 'center' }}>
        <Texto suave>Código da turma</Texto>
        <Text selectable style={{ color: c.texto, fontSize: 36, fontWeight: '800', letterSpacing: 8 }}>{t.codigo}</Text>
        <View style={{ padding: espaco.m, backgroundColor: '#FFFFFF', borderRadius: 8 }}>
          <QRCode value={conteudoQr(t.codigo)} size={200} />
        </View>
        <Texto suave tamanho={13}>Mostre este QR na primeira aula. O estudante lê uma vez só.</Texto>
      </Cartao>

      {/* ---------------- dados ---------------- */}
      <Cartao>
        <Campo rotulo="Nome da turma" value={t.nome} onChangeText={(nome) => alterar({ nome })} />
        <Texto suave tamanho={13}>Sala (o servidor conhece a planta e as âncoras destas salas)</Texto>
        <Linha>
          {Object.keys(SALAS).map((s) => (
            <Chip key={s} texto={s} ativo={t.sala === s} onPress={() => alterar({ sala: s })} />
          ))}
        </Linha>
      </Cartao>

      {/* ---------------- grade ---------------- */}
      <Cartao>
        <Titulo>Horários das aulas</Titulo>
        {t.periodos.length === 0 && <Texto suave>Nenhum horário ainda.</Texto>}
        {t.periodos.map((p, i) => (
          <View key={`${p.dia}-${p.inicio}-${i}`}
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                         borderBottomWidth: 1, borderBottomColor: c.borda, paddingVertical: espaco.s }}>
            <Text style={{ color: c.texto, fontSize: 16 }}>
              <Text style={{ fontWeight: '700' }}>{DIAS[p.dia]}</Text>  {p.inicio} – {p.fim}
            </Text>
            <Pressable accessibilityRole="button" hitSlop={12}
                       onPress={() => alterar({ periodos: t.periodos.filter((_, j) => j !== i) })}>
              <Text style={{ color: c.fora, fontWeight: '600' }}>Remover</Text>
            </Pressable>
          </View>
        ))}

        <Texto suave tamanho={13}>Novo horário</Texto>
        <Linha gap={6}>
          {DIAS.map((d, i) => <Chip key={d} texto={d} ativo={dia === i} onPress={() => setDia(i)} />)}
        </Linha>
        <View style={{ flexDirection: 'row', gap: espaco.m }}>
          <View style={{ flex: 1 }}>
            <Campo rotulo="Início" value={inicio} placeholder="19:00" keyboardType="number-pad"
                   onChangeText={(v) => { setInicio(mascaraHora(v)); setErro(''); }} maxLength={5} />
          </View>
          <View style={{ flex: 1 }}>
            <Campo rotulo="Fim" value={fim} placeholder="20:40" keyboardType="number-pad"
                   onChangeText={(v) => { setFim(mascaraHora(v)); setErro(''); }} maxLength={5} />
          </View>
        </View>
        {erro !== '' && <Text style={{ color: c.fora }}>{erro}</Text>}
        <Botao titulo="Adicionar horário" tipo="secundario" onPress={adicionarPeriodo} />
      </Cartao>

      <Botao titulo={t.publicada ? 'Publicada ✓' : 'Publicar para os estudantes'} onPress={() => publicar()}
             desativado={t.publicada} />
      {mensagem !== '' && <Texto suave>{mensagem}</Texto>}

      {/* ---------------- calibração da âncora ---------------- */}
      <Cartao>
        <Titulo>Âncora: calibrar a {DISTANCIA_LIMITE_M} m</Titulo>
        <Texto suave tamanho={13}>
          Só o administrador calibra. Fique a {DISTANCIA_LIMITE_M} m do notebook, parado, segurando o celular
          como o estudante segura, e toque em calibrar ({CALIBRACAO_MS / 1000} s). O valor vai junto com a
          turma; o celular do estudante não tem como mudar.
        </Texto>
        <Text style={[estilos.numeroGrande, { color: c.texto, fontSize: 32 }]}>
          {ancora.leitura.rssi === null ? 'âncora não ouvida' : `${Math.round(ancora.leitura.rssi)} dBm`}
        </Text>
        <Texto suave tamanho={13}>
          {t.limiar1mDbm === null ? 'Ainda não calibrada: os estudantes não são contados como perto nem longe.'
            : `Calibrada: ${t.limiar1mDbm} dBm a ${DISTANCIA_LIMITE_M} m.`}
        </Texto>
        <Botao titulo={ancora.calibrando ? 'Medindo…' : t.limiar1mDbm === null ? 'Calibrar' : 'Calibrar de novo'}
               onPress={calibrar} carregando={ancora.calibrando} desativado={ancora.estadoBle !== 'escutando'} />
        {msgCalibracao !== '' && <Texto tamanho={14}>{msgCalibracao}</Texto>}
      </Cartao>

      {/* ---------------- demonstração ---------------- */}
      <Cartao>
        <Titulo>Aula de demonstração</Titulo>
        <Texto suave tamanho={13}>
          Começa uma aula agora, fora da grade, com {DURACAO_AULA_DEMO_S} s — a aula de 50 min no tempo
          comprimido do servidor (1 s = 30 s). Serve para mostrar o sistema funcionando em sala.
        </Texto>
        {demo ? (
          <>
            <Text style={{ color: c.presente, fontWeight: '700', fontSize: 16 }}>
              Em andamento · termina em {restante} s
            </Text>
            <Botao titulo="Encerrar agora" tipo="perigo" onPress={encerrarDemo} />
          </>
        ) : (
          <Botao titulo="Iniciar aula agora" onPress={iniciarDemo} />
        )}
      </Cartao>

      <Botao titulo="Apagar turma" tipo="perigo" onPress={apagar} />
    </Tela>
  );
}
