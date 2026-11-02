import { Stack } from 'expo-router';
import { SQLiteProvider } from 'expo-sqlite';
import { StatusBar } from 'expo-status-bar';
import { migrar } from '@/lib/db';
import { useCores } from '@/ui/tema';

export default function Layout() {
  const c = useCores();
  return (
    <SQLiteProvider databaseName="presenca.db" onInit={migrar}>
      <StatusBar style="auto" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: c.fundo },
          headerTintColor: c.texto,
          headerShadowVisible: false,
          contentStyle: { backgroundColor: c.fundo },
          headerBackTitle: 'Voltar',
        }}
      >
        <Stack.Screen name="index" options={{ title: 'Presença' }} />
        <Stack.Screen name="entrar" options={{ title: 'Entrar numa turma' }} />
        <Stack.Screen name="ler-qr" options={{ title: 'Ler QR da turma' }} />
        <Stack.Screen name="turma/[codigo]" options={{ title: 'Aula' }} />
        <Stack.Screen name="admin/index" options={{ title: 'Administração' }} />
        <Stack.Screen name="admin/[codigo]" options={{ title: 'Turma' }} />
      </Stack>
    </SQLiteProvider>
  );
}
