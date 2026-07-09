import { forwardRef, useImperativeHandle, useRef } from 'react';
import { View, StyleSheet } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';

export interface CameraSectionHandle {
  takePictureAsync: (options?: { base64?: boolean; quality?: number }) => Promise<{ uri: string } | undefined>;
}

export const CameraSection = forwardRef<CameraSectionHandle>((_, ref) => {
  const [permission] = useCameraPermissions();
  const cameraRef = useRef<any>(null);

  useImperativeHandle(ref, () => ({
    async takePictureAsync(options) {
      return cameraRef.current?.takePictureAsync(options);
    },
  }));

  if (!permission?.granted) {
    return <View style={styles.placeholder} />;
  }

  return <CameraView ref={cameraRef} style={styles.camera} facing="back" enableTorch={false} />;
});

const styles = StyleSheet.create({
  camera: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  placeholder: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: '#000' },
});
