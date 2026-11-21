import { router, useFocusEffect } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { listarTurmas, type TurmaLocal } from '@/lib/db';
import { minhaIdentidade } from '@/lib/identidade';
import { aulaEmAndamento, DIAS, proximaAula } from '@/lib/turma';
import { Botao, Cartao, IndicadorConexao, Tela, Texto, Titulo } from '@/ui/componentes';
import { espaco, raio, useCores } from '@/ui/tema';

export default function Inicio() {
  const db = useSQLiteContext();
  const c = useCores();
  const [turmas, setTurmas] = useState<TurmaLocal[]>([]);
  const [aluno, setAluno] = useState('');

  useFocusEffect(useCallback(() => {
    listarTurmas(db, 'aluno').then(setTurmas);
  }, [db]));
  useEffect(() => { minhaIdentidade().then((e) => setAluno(e.aluno)); }, []);

  return (
    <Tela>
      <View style={{ gap: espaco.xs }}>
        <Texto suave>
          Sua frequência é registrada sozinha enquanto você está na sala. Entre na turma uma vez
          com o código ou o QR que o professor mostrar.
        </Texto>
        <IndicadorConexao />
      </View>

      <Titulo>Minhas turmas</Titulo>
      {turmas.length === 0 && (
        <Cartao>
          <Texto suave>Você ainda não entrou em nenhuma turma.</Texto>
        </Cartao>
      )}
      {turmas.map((t) => {
        const agora = new Date();
        const aula = aulaEmAndamento(t, agora);
        const prox = proximaAula(t.periodos, agora);
        return (
          <Pressable
            key={t.codigo}
            accessibilityRole="button"
            onPress={() => router.push({ pathname: '/turma/[codigo]', params: { codigo: t.codigo } })}
            style={({ pressed }) => ({
              backgroundColor: c.cartao, borderRadius: raio, borderWidth: 1, borderColor: c.borda,
              padding: espaco.l, gap: espaco.xs, opacity: pressed ? 0.7 : 1,
            })}
          >
            <Text style={{ color: c.texto, fontSize: 17, fontWeight: '700' }}>{t.nome}</Text>
            <Text style={{ color: c.suave }}>{t.sala} · código {t.codigo}</Text>
            <Text style={{ color: aula ? c.presente : c.suave, fontWeight: aula ? '700' : '400' }}>
              {aula ? 'Aula acontecendo agora'
                : prox ? `Próxima aula: ${DIAS[prox.getDay()]} ${prox.toTimeString().slice(0, 5)}`
                : 'Sem aulas na grade'}
            </Text>
          </Pressable>
        );
      })}

      <Botao titulo="Entrar numa turma" onPress={() => router.push('/entrar')} />

      <View style={{ marginTop: espaco.xl, gap: espaco.s }}>
        <Botao titulo="Área do administrador" tipo="secundario" onPress={() => router.push('/admin')} />
        {aluno !== '' && (
          <Texto suave tamanho={12}>
            Este aparelho aparece para o servidor como {aluno} — um pseudônimo, sem nome nem número do aparelho.
          </Texto>
        )}
      </View>
    </Tela>
  );
}
