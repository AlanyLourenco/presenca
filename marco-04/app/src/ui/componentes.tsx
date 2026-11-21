import { type ReactNode, useEffect, useState } from 'react';
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, type TextInputProps, View,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { mqtt } from '@/lib/mqtt';
import { espaco, raio, useCores } from './tema';

export function Tela({ children }: { children: ReactNode }) {
  const c = useCores();
  const { bottom } = useSafeAreaInsets();
  return (
    <ScrollView
      style={{ backgroundColor: c.fundo }}
      contentContainerStyle={{ padding: espaco.l, paddingBottom: bottom + espaco.xl, gap: espaco.l }}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  );
}

export function Cartao({ children, estilo }: { children: ReactNode; estilo?: ViewStyle }) {
  const c = useCores();
  return (
    <View style={[{ backgroundColor: c.cartao, borderColor: c.borda, borderWidth: 1, borderRadius: raio,
                    padding: espaco.l, gap: espaco.m }, estilo]}>
      {children}
    </View>
  );
}

export function Titulo({ children }: { children: ReactNode }) {
  const c = useCores();
  return <Text style={{ color: c.texto, fontSize: 17, fontWeight: '700' }}>{children}</Text>;
}

export function Texto({ children, suave, tamanho = 15 }: { children: ReactNode; suave?: boolean; tamanho?: number }) {
  const c = useCores();
  return <Text style={{ color: suave ? c.suave : c.texto, fontSize: tamanho, lineHeight: tamanho * 1.4 }}>{children}</Text>;
}

type TipoBotao = 'primario' | 'secundario' | 'perigo';

export function Botao({ titulo, onPress, tipo = 'primario', desativado, carregando }: {
  titulo: string; onPress: () => void; tipo?: TipoBotao; desativado?: boolean; carregando?: boolean;
}) {
  const c = useCores();
  const fundo = tipo === 'primario' ? c.primaria : 'transparent';
  const cor = tipo === 'primario' ? c.primariaTexto : tipo === 'perigo' ? c.fora : c.primaria;
  return (
    <Pressable
      onPress={onPress}
      disabled={desativado || carregando}
      accessibilityRole="button"
      style={({ pressed }) => ({
        backgroundColor: fundo, borderRadius: raio, minHeight: 48, paddingHorizontal: espaco.l,
        alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: espaco.s,
        borderWidth: tipo === 'primario' ? 0 : 1.5, borderColor: cor,
        opacity: desativado ? 0.4 : pressed ? 0.75 : 1,
      })}
    >
      {carregando && <ActivityIndicator color={cor} />}
      <Text style={{ color: cor, fontSize: 16, fontWeight: '600' }}>{titulo}</Text>
    </Pressable>
  );
}

export function Campo(props: TextInputProps & { rotulo: string }) {
  const c = useCores();
  const { rotulo, style, ...resto } = props;
  return (
    <View style={{ gap: espaco.xs }}>
      <Text style={{ color: c.suave, fontSize: 13, fontWeight: '600' }}>{rotulo}</Text>
      <TextInput
        placeholderTextColor={c.neutro}
        {...resto}
        style={[{ backgroundColor: c.campo, color: c.texto, borderColor: c.borda, borderWidth: 1,
                  borderRadius: 10, paddingHorizontal: espaco.m, minHeight: 48, fontSize: 16 }, style]}
      />
    </View>
  );
}

export function Chip({ texto, ativo, onPress }: { texto: string; ativo?: boolean; onPress: () => void }) {
  const c = useCores();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!ativo }}
      style={{ paddingHorizontal: espaco.m, minHeight: 40, justifyContent: 'center', borderRadius: 999,
               borderWidth: 1.5, borderColor: ativo ? c.primaria : c.borda,
               backgroundColor: ativo ? c.primaria : 'transparent' }}
    >
      <Text style={{ color: ativo ? c.primariaTexto : c.texto, fontWeight: '600' }}>{texto}</Text>
    </Pressable>
  );
}

export function Linha({ children, gap = espaco.s }: { children: ReactNode; gap?: number }) {
  return <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap }}>{children}</View>;
}

/** Bolinha + texto com o estado da conexão com o broker. */
export function IndicadorConexao() {
  const c = useCores();
  const [on, setOn] = useState(mqtt.conectado);
  useEffect(() => mqtt.aoMudarConexao(setOn), []);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: on ? c.presente : c.fora }} />
      <Text style={{ color: c.suave, fontSize: 13 }}>{on ? 'conectado ao servidor' : 'sem conexão'}</Text>
    </View>
  );
}

export const estilos = StyleSheet.create({
  numeroGrande: { fontSize: 40, fontWeight: '800', fontVariant: ['tabular-nums'] },
});
