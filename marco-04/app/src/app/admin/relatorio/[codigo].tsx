/**
 * Relatório de presença da turma e CHAMADA (atuador) — Marco 4, tela do professor.
 *
 * - O relatório chega do servidor (presenca.relatorio.v1, retido e assinado):
 *   aula em andamento ao vivo e as anteriores, com exportação em CSV.
 * - Em cada estudante, o professor manda uma operação ao celular dele
 *   (vibrar, chamar, lanterna), assinada com a chave deste celular (a mesma
 *   que assina a turma, fixada no celular do estudante no pareamento).
 * - A confirmação de cada celular volta assinada pelo próprio estudante.
 */
import { File, Paths } from 'expo-file-system';
import { Redirect, Stack, useLocalSearchParams } from 'expo-router';
import * as Sharing from 'expo-sharing';
import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { abrirEnvelope, envelopar, identidadeDaChave } from '@/lib/assinatura';
import { montarComando, type TipoComando } from '@/lib/comandos';
import { CHAVE_PUBLICA_SERVIDOR, SALA_PADRAO, topicos } from '@/lib/config';
import { minhaIdentidade } from '@/lib/identidade';
import { mqtt } from '@/lib/mqtt';
import { abrirRelatorio, relatorioCsv, resultadoDe, type AulaNoRelatorio, type Relatorio } from '@/lib/relatorio';
import { adminLiberado } from '@/lib/sessao-admin';
import { Botao, Cartao, Chip, IndicadorConexao, Linha, Tela, Texto, Titulo } from '@/ui/componentes';
import { espaco, useCores } from '@/ui/tema';

const num = (x: number, casas = 0) => x.toFixed(casas).replace('.', ',');
const ROTULO: Record<TipoComando, string> = { vibrar: 'Vibrar', chamar: 'Chamar', lanterna: 'Lanterna' };
const TEXTO: Record<TipoComando, string> = {
  vibrar: 'O professor pediu sua atenção.',
  chamar: 'Chamada: toque em "Estou aqui".',
  lanterna: 'Mostre que está na sala: a lanterna do celular vai piscar.',
};
const SITUACAO: Record<string, string> = {
  executado: 'recebeu e executou', respondido: 'respondeu: "Estou aqui"', recusado: 'não executou',
  vencido: 'chegou vencido',
};

interface Envio { aluno: string; tipo: TipoComando; enviadoEm: number; resultado?: string; detalhe?: string; em?: number }

export default function RelatorioDaTurma() {
  const { codigo } = useLocalSearchParams<{ codigo: string }>();
  const c = useCores();
  const [rel, setRel] = useState<Relatorio | null>(null);
  const [recusado, setRecusado] = useState('');
  const [aulaVista, setAulaVista] = useState(0);
  const [envios, setEnvios] = useState<Record<string, Envio>>({});
  const [msg, setMsg] = useState('');
  const sala = SALA_PADRAO;

  useEffect(() => {
    const pararRel = mqtt.assinar(topicos.relatorio(codigo), (topico, texto) => {
      if (!texto) return;
      const r = abrirRelatorio(topico, texto, CHAVE_PUBLICA_SERVIDOR, codigo);
      if (r.ok) setRel(r.relatorio);
      else setRecusado(r.motivo);
    });
    // Confirmações dos celulares: cada uma assinada pelo estudante que diz ser.
    const pararAck = mqtt.assinar(topicos.comandoAckTodos(sala), (topico, texto) => {
      const a = abrirEnvelope(topico, texto);
      if (!a.ok) return;
      const ack = a.carga as { comandoId: string; aluno: string; resultado: string; detalhe?: string; emMs: number };
      if (identidadeDaChave(a.chavePublica).aluno !== ack.aluno || !topico.endsWith(`/${ack.aluno}`)) return;
      setEnvios((e) => (e[ack.comandoId]
        ? { ...e, [ack.comandoId]: { ...e[ack.comandoId], resultado: ack.resultado, detalhe: ack.detalhe, em: Date.now() } }
        : e));
    });
    return () => { pararRel(); pararAck(); };
  }, [codigo, sala]);

  if (!adminLiberado()) return <Redirect href="/admin" />;

  async function mandar(aluno: string, tipo: TipoComando) {
    const eu = await minhaIdentidade();
    const cmd = montarComando({ aluno, turma: codigo, tipo, texto: TEXTO[tipo] }, Date.now());
    const topico = topicos.comando(sala, aluno);
    if (!mqtt.publicar(topico, envelopar(eu.privada, 'admin', topico, cmd), { qos: 1 })) {
      setMsg('Sem conexão com o broker: o comando não saiu.');
      return;
    }
    setMsg('');
    setEnvios((e) => ({ ...e, [cmd.comandoId]: { aluno, tipo, enviadoEm: Date.now() } }));
  }

  async function exportar() {
    if (!rel) return;
    try {
      const arquivo = new File(Paths.cache, `presenca-${codigo}-${Date.now()}.csv`);
      arquivo.create({ overwrite: true });
      arquivo.write('﻿' + relatorioCsv(rel));        // BOM: o Excel reconhece os acentos
      await Sharing.shareAsync(arquivo.uri, { mimeType: 'text/csv', dialogTitle: `Presença ${codigo}`, UTI: 'public.comma-separated-values-text' });
    } catch (e) {
      setMsg(`Não foi possível exportar: ${String(e)}`);
    }
  }

  const aula: AulaNoRelatorio | undefined = rel?.aulas[aulaVista];
  const ultimoEnvio = (aluno: string) => Object.entries(envios)
    .filter(([, e]) => e.aluno === aluno).sort((a, b) => b[1].enviadoEm - a[1].enviadoEm)[0]?.[1];

  return (
    <Tela>
      <Stack.Screen options={{ title: `Relatório · ${codigo}` }} />
      <IndicadorConexao />
      {!rel && (
        <Cartao>
          <Titulo>Esperando o relatório do servidor…</Titulo>
          <Texto suave>
            O servidor publica o relatório desta turma assim que algum estudante manda o primeiro heartbeat.
            {recusado ? ` Recusei uma versão: ${recusado}.` : ''}
          </Texto>
        </Cartao>
      )}
      {rel && (
        <>
          <Texto suave tamanho={13}>
            Atualizado às {new Date(rel.geradoEmMs).toTimeString().slice(0, 8)} · assinado pelo servidor ✓
          </Texto>
          <Linha gap={6}>
            {rel.aulas.slice(0, 6).map((a, i) => (
              <Chip key={a.aulaId} ativo={aulaVista === i} onPress={() => setAulaVista(i)}
                    texto={`${new Date(a.inicioMs).toLocaleDateString('pt-BR').slice(0, 5)} ${new Date(a.inicioMs).toTimeString().slice(0, 5)}${a.emAndamento ? ' •' : ''}`} />
            ))}
          </Linha>
          <Botao titulo="Exportar lista da turma (CSV)" tipo="secundario" onPress={exportar} />
        </>
      )}
      {msg !== '' && <Text style={{ color: c.fora }}>{msg}</Text>}

      {aula && (
        <Cartao>
          <Titulo>{aula.emAndamento ? 'Aula em andamento' : 'Aula encerrada'}</Titulo>
          <Texto suave tamanho={13}>
            {aula.alunos.length} estudante(s) · {aula.alunos.filter((x) => x.aprovado).length} com presença
            {aula.emAndamento ? ' até agora' : ''}
          </Texto>
          {aula.alunos.map((x) => {
            const envio = ultimoEnvio(x.aluno);
            const cor = x.estado === 'PRESENTE' ? c.presente : x.estado === 'AUSENCIA_TOLERADA' ? c.tolerancia : c.fora;
            return (
              <View key={x.aluno} style={{ borderTopWidth: 1, borderTopColor: c.borda, paddingTop: espaco.s, gap: 4 }}>
                <Text style={{ color: c.texto, fontSize: 16, fontWeight: '700' }}>
                  {x.nome ?? x.aluno}{x.matricula ? ` · ${x.matricula}` : ''}
                </Text>
                <Text style={{ color: cor, fontWeight: '700' }}>
                  {num(x.percentual)} % · {resultadoDe(x)}
                  {aula.emAndamento ? ` · agora: ${x.estado === 'PRESENTE' ? 'na sala' : x.estado === 'AUSENCIA_TOLERADA' ? 'fora (tolerância)' : 'fora'}` : ''}
                </Text>
                <Texto suave tamanho={12}>
                  {x.nome ? `${x.aluno} · ` : ''}dentro {num(x.dentroS)} s · perdoado {num(x.perdoadoS)} s · {x.mensagens} mensagens
                  {x.bateria !== null ? ` · bateria ${Math.round(x.bateria * 100)} %` : ''}
                </Texto>
                {x.celularParado && (
                  <Text style={{ color: c.tolerancia, fontSize: 13 }}>
                    Celular parado a aula toda (acelerômetro): confira se o estudante está com ele.
                  </Text>
                )}
                {aula.emAndamento && (
                  <Linha gap={6}>
                    {(['vibrar', 'chamar', 'lanterna'] as TipoComando[]).map((tipo) => (
                      <Chip key={tipo} texto={ROTULO[tipo]} ativo={false} onPress={() => mandar(x.aluno, tipo)} />
                    ))}
                  </Linha>
                )}
                {envio && (
                  <Texto tamanho={13}>
                    {ROTULO[envio.tipo]}: {envio.resultado
                      ? `${SITUACAO[envio.resultado] ?? envio.resultado} em ${num(((envio.em ?? 0) - envio.enviadoEm) / 1000, 1)} s`
                      : 'enviado, esperando o celular…'}
                  </Texto>
                )}
              </View>
            );
          })}
        </Cartao>
      )}
    </Tela>
  );
}
