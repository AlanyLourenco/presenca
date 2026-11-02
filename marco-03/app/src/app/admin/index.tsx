import { router, useFocusEffect } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, Text } from 'react-native';
import { SALA_PADRAO } from '@/lib/config';
import { listarTurmas, salvarTurma, type TurmaLocal } from '@/lib/db';
import { conferirPinAdmin, definirPinAdmin, temPinAdmin } from '@/lib/identidade';
import { adminLiberado, liberarAdmin } from '@/lib/sessao-admin';
import { gerarCodigo } from '@/lib/turma';
import { Botao, Campo, Cartao, Tela, Texto, Titulo } from '@/ui/componentes';
import { espaco, raio, useCores } from '@/ui/tema';

const PIN_MINIMO = 4;

export default function Admin() {
  const [ok, setOk] = useState(adminLiberado());
  return ok ? <ListaTurmas /> : <Portao aoLiberar={() => { liberarAdmin(); setOk(true); }} />;
}

function Portao({ aoLiberar }: { aoLiberar: () => void }) {
  const c = useCores();
  const [existe, setExiste] = useState<boolean | null>(null);
  const [pin, setPin] = useState('');
  const [confirma, setConfirma] = useState('');
  const [erro, setErro] = useState('');

  useEffect(() => { temPinAdmin().then(setExiste); }, []);
  if (existe === null) return null;

  async function continuar() {
    if (pin.length < PIN_MINIMO) return setErro(`O PIN tem pelo menos ${PIN_MINIMO} números.`);
    if (!existe) {
      if (pin !== confirma) return setErro('Os dois PINs não são iguais.');
      await definirPinAdmin(pin);
      return aoLiberar();
    }
    if (await conferirPinAdmin(pin)) aoLiberar();
    else { setErro('PIN errado.'); setPin(''); }
  }

  return (
    <Tela>
      <Cartao>
        <Titulo>{existe ? 'Entre com o PIN do administrador' : 'Crie o PIN do administrador'}</Titulo>
        <Texto suave>
          {existe ? 'Só quem tem o PIN cria turmas e define os horários das aulas.'
                  : 'Este PIN protege, neste celular, a criação de turmas e a grade de aulas.'}
        </Texto>
        <Campo rotulo="PIN" value={pin} onChangeText={(t) => { setPin(t.replace(/\D/g, '')); setErro(''); }}
               keyboardType="number-pad" secureTextEntry maxLength={8} autoFocus
               onSubmitEditing={existe ? continuar : undefined} />
        {!existe && (
          <Campo rotulo="Repita o PIN" value={confirma} onChangeText={(t) => setConfirma(t.replace(/\D/g, ''))}
                 keyboardType="number-pad" secureTextEntry maxLength={8} onSubmitEditing={continuar} />
        )}
        {erro !== '' && <Text style={{ color: c.fora }}>{erro}</Text>}
        <Botao titulo={existe ? 'Entrar' : 'Criar PIN e entrar'} onPress={continuar} />
      </Cartao>
    </Tela>
  );
}

function ListaTurmas() {
  const db = useSQLiteContext();
  const c = useCores();
  const [turmas, setTurmas] = useState<TurmaLocal[]>([]);

  useFocusEffect(useCallback(() => { listarTurmas(db, 'admin').then(setTurmas); }, [db]));

  async function nova() {
    const codigo = gerarCodigo();
    await salvarTurma(db, { codigo, nome: 'Nova turma', sala: SALA_PADRAO, periodos: [], aulaAgora: null, limiar1mDbm: null },
                      'admin', null);
    router.push({ pathname: '/admin/[codigo]', params: { codigo } });
  }

  return (
    <Tela>
      <Texto suave>
        Cada turma tem um código. O estudante entra digitando o código ou lendo o QR, e o app dele
        passa a seguir a grade de aulas que você publicar aqui.
      </Texto>
      {turmas.length === 0 && <Cartao><Texto suave>Nenhuma turma criada neste celular.</Texto></Cartao>}
      {turmas.map((t) => (
        <Pressable
          key={t.codigo}
          accessibilityRole="button"
          onPress={() => router.push({ pathname: '/admin/[codigo]', params: { codigo: t.codigo } })}
          style={({ pressed }) => ({
            backgroundColor: c.cartao, borderRadius: raio, borderWidth: 1, borderColor: c.borda,
            padding: espaco.l, gap: espaco.xs, opacity: pressed ? 0.7 : 1,
          })}
        >
          <Text style={{ color: c.texto, fontSize: 17, fontWeight: '700' }}>{t.nome}</Text>
          <Text style={{ color: c.suave }}>
            {t.codigo} · {t.sala} · {t.periodos.length} horário(s)
          </Text>
          <Text style={{ color: t.publicada ? c.presente : c.tolerancia, fontWeight: '600' }}>
            {t.publicada ? 'Publicada' : 'Alterações não publicadas'}
          </Text>
        </Pressable>
      ))}
      <Botao titulo="Nova turma" onPress={nova} />
    </Tela>
  );
}
