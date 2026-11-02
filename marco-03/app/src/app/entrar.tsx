import { router, useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { Text } from 'react-native';
import { TAMANHO_CODIGO } from '@/lib/config';
import { salvarTurma } from '@/lib/db';
import { buscarTurma } from '@/lib/rede-turma';
import { normalizarCodigo } from '@/lib/turma';
import { Botao, Campo, Cartao, Tela, Texto } from '@/ui/componentes';
import { useCores } from '@/ui/tema';

export default function Entrar() {
  const db = useSQLiteContext();
  const c = useCores();
  const params = useLocalSearchParams<{ codigo?: string }>();
  const [texto, setTexto] = useState(params.codigo ?? '');
  const [erro, setErro] = useState('');
  const [buscando, setBuscando] = useState(false);

  async function entrar(valor = texto) {
    const codigo = normalizarCodigo(valor);
    if (!codigo) {
      setErro(`O código tem ${TAMANHO_CODIGO} letras e números, como K7QM2P.`);
      return;
    }
    setErro('');
    setBuscando(true);
    const turma = await buscarTurma(codigo);
    setBuscando(false);
    if (!turma) {
      setErro('Nenhuma turma com esse código chegou. Confira o código e a internet, '
             + 'ou peça ao administrador para publicar a turma.');
      return;
    }
    await salvarTurma(db, turma, 'aluno', turma.publicadoEmMs);
    if (router.canDismiss()) router.dismissAll();
    router.push({ pathname: '/turma/[codigo]', params: { codigo } });
  }

  // Veio do leitor de QR já com o código: entra direto.
  useEffect(() => { if (params.codigo) entrar(params.codigo); }, [params.codigo]);

  return (
    <Tela>
      <Cartao>
        <Campo
          rotulo="Código da turma"
          value={texto}
          onChangeText={(t) => { setTexto(t); setErro(''); }}
          placeholder="K7QM2P"
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={TAMANHO_CODIGO + 2}
          returnKeyType="go"
          onSubmitEditing={() => entrar()}
          style={{ fontSize: 24, letterSpacing: 6, fontWeight: '700', textAlign: 'center' }}
        />
        {erro !== '' && <Text style={{ color: c.fora, fontSize: 14, lineHeight: 20 }}>{erro}</Text>}
        <Botao titulo={buscando ? 'Procurando a turma…' : 'Entrar'} onPress={() => entrar()} carregando={buscando} />
      </Cartao>

      <Texto suave>ou</Texto>
      <Botao titulo="Ler o QR da turma" tipo="secundario" onPress={() => router.push('/ler-qr')} />

      <Texto suave tamanho={13}>
        Você faz isso uma vez por semestre. Depois, o app sabe sozinho quando é hora de aula.
      </Texto>
    </Tela>
  );
}
