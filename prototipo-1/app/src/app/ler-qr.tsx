import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { View } from 'react-native';
import { normalizarCodigo } from '@/lib/turma';
import { Botao, Cartao, Tela, Texto } from '@/ui/componentes';
import { espaco, raio } from '@/ui/tema';

export default function LerQr() {
  const [permissao, pedirPermissao] = useCameraPermissions();
  const [aviso, setAviso] = useState('');
  const lido = useRef(false);

  if (!permissao) return null;

  if (!permissao.granted) {
    return (
      <Tela>
        <Cartao>
          <Texto>A câmera é usada só para ler o QR da turma, uma vez. Nenhuma imagem é guardada.</Texto>
          <Botao titulo="Permitir a câmera" onPress={pedirPermissao} />
          {!permissao.canAskAgain && (
            <Texto suave>A permissão foi negada. Libere a câmera nas configurações do celular, ou digite o código.</Texto>
          )}
        </Cartao>
        <Botao titulo="Digitar o código" tipo="secundario" onPress={() => router.back()} />
      </Tela>
    );
  }

  return (
    <View style={{ flex: 1, padding: espaco.l, gap: espaco.l }}>
      <CameraView
        style={{ flex: 1, borderRadius: raio, overflow: 'hidden' }}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={({ data }) => {
          if (lido.current) return;
          const codigo = normalizarCodigo(data);
          if (!codigo) {
            setAviso('Esse QR não é de uma turma do Presença.');
            return;
          }
          lido.current = true;
          router.replace({ pathname: '/entrar', params: { codigo } });
        }}
      />
      <Texto suave>{aviso || 'Aponte para o QR que o professor mostrar.'}</Texto>
    </View>
  );
}
