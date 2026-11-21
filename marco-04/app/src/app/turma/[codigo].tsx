import { CameraView } from 'expo-camera';
import { activateKeepAwakeAsync, deactivateKeepAwake } from 'expo-keep-awake';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Switch, Text, Vibration, View } from 'react-native';
import { envelopar } from '@/lib/assinatura';
import { DISTANCIA_LIMITE_M, HISTERESE_DB, MQTT_USUARIO, SALA_PADRAO, topicos } from '@/lib/config';
import {
  apagarTurma, gravarAjuste, historico, lerAjuste, obterTurma, registrarAula, registrarAviso, salvarTurma,
  ultimosAvisos,
  type TurmaLocal,
} from '@/lib/db';
import { minhaIdentidade, type Eu } from '@/lib/identidade';
import { mqtt } from '@/lib/mqtt';
import { notificar, prepararNotificacoes } from '@/lib/notificacoes';
import { desligarSegundoPlano, ligarSegundoPlano, type EstadoSegundoPlano } from '@/lib/segundo-plano';
import { acompanharTurma } from '@/lib/rede-turma';
import { aulaEmAndamento, DIAS, idDaAula, limiaresDa, proximaAula } from '@/lib/turma';
import { useComandos } from '@/lib/usar-comandos';
import { useAparelho, type AvisoServidor, type EstadoServidor } from '@/lib/usar-aparelho';
import { Botao, Campo, Cartao, Chip, IndicadorConexao, Linha, Tela, Texto, Titulo, estilos } from '@/ui/componentes';
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
  'sem-permissao': 'sem permissão para usar o Bluetooth — libere em Configurações > Apps > Presença M4',
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
  // Marco 4
  const [cadastrado, setCadastrado] = useState<string | null>(null);
  const [nome, setNome] = useState('');
  const [matricula, setMatricula] = useState('');
  const [msgCadastro, setMsgCadastro] = useState('');
  const [segundoPlano, setSegundoPlano] = useState<EstadoSegundoPlano>('desligado');

  const recarregar = useCallback(async () => {
    setTurma(await obterTurma(db, codigo, 'aluno'));
    setAvisos(await ultimosAvisos(db, codigo));
    setAulas(await historico(db, codigo));
    setCadastrado(await lerAjuste(db, `cadastro.${codigo}`));
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
  const aulaId = aula ? idDaAula(aula, relogio) : null;

  // Segundo plano: o serviço só fica ligado durante a aula.
  useEffect(() => {
    if (!ativo && segundoPlano === 'ligado') {
      desligarSegundoPlano();
      setSegundoPlano('desligado');
    }
  }, [ativo, segundoPlano]);

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
  const limiares = turma ? limiaresDa(turma) : {};
  const calibrada = Object.values(limiares).some((v) => v !== null);
  const sala = turma?.sala ?? SALA_PADRAO;
  const ap = useAparelho({ eu, sala, turma: codigo, aulaId, ativo, limiares, aoAviso, aoEncerrar });
  const cmd = useComandos({ eu, sala, turma: codigo });

  if (!turma) return null;

  const prox = proximaAula(turma.periodos, relogio);

  async function enviarCadastro() {
    if (!eu) return;
    const n = nome.trim();
    if (n.length < 2) return setMsgCadastro('Escreva o seu nome como está na chamada.');
    const msg = { eventType: 'presenca.cadastro.v1', aluno: eu.aluno, turma: codigo, nome: n.slice(0, 80),
                  matricula: matricula.trim().slice(0, 20), emMs: Date.now() };
    const topico = topicos.cadastro(eu.aluno);
    if (!mqtt.publicar(topico, envelopar(eu.privada, eu.aluno, topico, msg), { qos: 1, retido: true })) {
      return setMsgCadastro('Sem conexão. Tente de novo quando a internet voltar.');
    }
    await gravarAjuste(db, `cadastro.${codigo}`, n);
    setCadastrado(n);
    setMsgCadastro('');
  }

  async function alternarSegundoPlano(v: boolean) {
    if (!v) { await desligarSegundoPlano(); return setSegundoPlano('desligado'); }
    setSegundoPlano(await ligarSegundoPlano());
  }

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

      {/* ---------------- atuador: comando do professor (Marco 4) ---------------- */}
      {cmd.naTela && (
        <Cartao estilo={{ borderColor: c.presente, borderWidth: 2 }}>
          <Titulo>{cmd.naTela.de === 'professor' ? 'O professor chamou' : 'Comando do servidor'}</Titulo>
          <Texto>{cmd.naTela.comando.texto}</Texto>
          {cmd.lanterna && <Texto suave>A lanterna está piscando…</Texto>}
          {cmd.naTela.comando.tipo === 'chamar' && !cmd.naTela.respondido && (
            <Botao titulo="Estou aqui" onPress={cmd.responder} />
          )}
          {cmd.naTela.respondido && <Text style={{ color: c.presente, fontWeight: '700' }}>Resposta enviada ao professor ✓</Text>}
          <Botao titulo="Fechar" tipo="secundario" onPress={cmd.fechar} />
        </Cartao>
      )}
      {/* A lanterna é o flash da câmera: precisa de uma câmera montada (1 px). */}
      {cmd.lanterna && <CameraView style={{ width: 1, height: 1, opacity: 0 }} enableTorch facing="back" />}

      {/* ---------------- identificação (Marco 4) ---------------- */}
      {cadastrado === null && (
        <Cartao>
          <Titulo>Identifique-se para o professor</Titulo>
          <Texto suave tamanho={13}>
            Só uma vez por turma. O nome fica numa tabela separada no servidor e pode ser apagado (LGPD);
            as medições usam só o seu pseudônimo{eu ? ` (${eu.aluno})` : ''}.
          </Texto>
          <Campo rotulo="Nome (como na chamada)" value={nome} onChangeText={setNome} />
          <Campo rotulo="Matrícula (opcional)" value={matricula} onChangeText={setMatricula} keyboardType="number-pad" />
          {msgCadastro !== '' && <Text style={{ color: c.fora }}>{msgCadastro}</Text>}
          <Botao titulo="Enviar ao professor" onPress={enviarCadastro} />
        </Cartao>
      )}

      {/* ---------------- sinal ---------------- */}
      <Cartao>
        <Titulo>{ap.leitura.ancoras.length > 1 ? 'Âncoras' : 'Âncora: o notebook'}</Titulo>
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
          {!calibrada && ap.leitura.rssi !== null ? SEM_CALIBRAR : NOME_REGIAO[ap.leitura.regiao]}
        </Text>
        {ap.leitura.ancoras.map((a) => (
          <Texto key={a.id} tamanho={13}>
            {a.id === 'anc-pc-1' ? 'notebook' : a.id === 'anc-pc-2' ? 'ESP32' : a.id} ({a.id}):{' '}
            <Text style={{ fontWeight: '700' }}>
              {a.rssi === null ? 'não ouvida' : `${num(a.rssi)} dBm`}
              {a.distancia !== null ? ` · ~${num(a.distancia, 1)} m` : ''}
            </Text>
            {a.rssi !== null && limiares[a.id] == null ? ' · sem calibração' : ''}
          </Texto>
        ))}
        <Texto suave tamanho={12}>
          âncora: {num(ap.leitura.porSegundo)} anúncios/s · todos os aparelhos: {num(ap.leitura.qualquerPorSegundo)}/s
          {ap.leitura.token ? ` · token ${ap.leitura.token}` : ''}
          {!calibrada ? ' · sem calibração' : ` · limiar de cada âncora definido pelo admin; sai ${HISTERESE_DB} dB abaixo`}
        </Texto>
      </Cartao>

      {/* ---------------- sensores do celular → broker (Marco 4) ---------------- */}
      {ativo && (
        <Cartao>
          <Titulo>Sensores do celular</Titulo>
          <Texto suave tamanho={13}>
            A cada 5 s, junto com o heartbeat, vai assinado para o broker: o quanto o celular se mexeu
            (acelerômetro) e a bateria.
          </Texto>
          {ap.sensores.disponivel === false && <Texto>Este celular não tem acelerômetro.</Texto>}
          {ap.sensores.enviado?.acelerometro && (
            <Texto>
              Movimento: <Text style={{ fontWeight: '700' }}>{num(ap.sensores.enviado.acelerometro.movimento, 3)} g</Text>
              {ap.sensores.enviado.acelerometro.parado ? ' — parado (sobre a mesa)' : ' — em movimento'}
            </Texto>
          )}
          {ap.sensores.ultimo && (
            <Texto suave tamanho={12}>
              agora: x {num(ap.sensores.ultimo.x, 2)} · y {num(ap.sensores.ultimo.y, 2)} · z {num(ap.sensores.ultimo.z, 2)} g
            </Texto>
          )}
          {ap.sensores.enviado?.bateria && (
            <Texto>
              Bateria: <Text style={{ fontWeight: '700' }}>{Math.round(ap.sensores.enviado.bateria.nivel * 100)} %</Text>
              {ap.sensores.enviado.bateria.carregando ? ' (carregando)' : ''}
            </Texto>
          )}
          <Texto suave tamanho={12}>leituras enviadas: {ap.envio.sensores}</Texto>
        </Cartao>
      )}

      {/* ---------------- segundo plano (Marco 4) ---------------- */}
      {ativo && (
        <Cartao>
          <Titulo>Tela apagada</Titulo>
          <Linha gap={espaco.m}>
            <Switch value={segundoPlano === 'ligado'} onValueChange={alternarSegundoPlano} />
            <Texto>Continuar contando com a tela apagada</Texto>
          </Linha>
          <Texto suave tamanho={12}>
            {segundoPlano === 'sem-permissao'
              ? 'Sem permissão. Em Configurações > Apps > Presença M4 > Permissões > Local, escolha "Permitir o tempo todo". O Android exige isso para o app seguir com a tela apagada; a localização não é usada nem enviada.'
              : segundoPlano === 'erro' ? 'O sistema não deixou ligar o serviço em segundo plano.'
              : 'Liga uma notificação fixa "Aula em andamento". Com ela, o Android não pausa o app e o Bluetooth segue medindo.'}
          </Texto>
        </Cartao>
      )}

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
        <Texto tamanho={14}>
          Comandos do professor executados: {cmd.executados}
          {cmd.recusados.total ? ` · recusados: ${cmd.recusados.total} (${cmd.recusados.motivo})` : ''}
        </Texto>
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
