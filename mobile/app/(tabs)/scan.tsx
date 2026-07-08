import { useState, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography } from '../../src/theme';
import { GlassCard } from '../../src/components';

const isWeb = Platform.OS === 'web';

export default function ScanScreen() {
  const router = useRouter();
  const [captured, setCaptured] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const cameraRef = useRef<any>(null);

  async function pickFileWeb(): Promise<string | null> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e: any) => {
      const file = e.target?.files?.[0];
      if (file) resolve(URL.createObjectURL(file));
      else resolve(null);
    };
    input.click();
  });
}

async function handleCapture() {
    setAnalyzing(true);
    try {
      let uri: string | null = null;
      if (isWeb) {
        uri = await pickFileWeb();
      } else if (cameraRef.current) {
        const photo = await cameraRef.current.takePictureAsync({ base64: false });
        uri = photo?.uri ?? null;
      }
      if (uri) {
        setCaptured(uri);
        const { api } = await import('../../src/lib/api');
        const problem = await api.recognizeProblem(uri);
        router.push(`/tutor?type=${encodeURIComponent(problem.type)}&content=${encodeURIComponent(problem.content)}&title=${encodeURIComponent(problem.title)}&imageUri=${encodeURIComponent(uri)}`);
      }
    } catch (e) {
      console.error('Capture error:', e);
    } finally {
      setAnalyzing(false);
    }
  }

  function handleRetake() {
    setCaptured(null);
  }

  if (isWeb) {
    return (
      <View style={styles.container}>
        <View style={styles.center}>
          <Ionicons name="cloud-upload-outline" size={64} color={colors.primary} />
          <Text style={styles.permissionText}>Upload a photo of your problem</Text>
          <TouchableOpacity style={styles.permissionButton} onPress={handleCapture} disabled={analyzing}>
            {analyzing ? (
              <ActivityIndicator size="small" color={colors.bg} />
            ) : (
              <Text style={styles.permissionButtonText}>Choose Image</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  const { CameraView, useCameraPermissions } = require('expo-camera');
  const [permission, requestPermission] = useCameraPermissions();

  if (!permission) {
    return <View style={styles.container} />;
  }

  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <View style={styles.center}>
          <Ionicons name="camera-outline" size={64} color={colors.textTertiary} />
          <Text style={styles.permissionText}>Camera access needed to scan problems</Text>
          <TouchableOpacity style={styles.permissionButton} onPress={requestPermission}>
            <Text style={styles.permissionButtonText}>Grant Permission</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        ref={cameraRef}
        style={styles.camera}
        facing="back"
        ratio="4:3"
      >
        <View style={styles.overlay}>
          <View style={styles.viewfinder}>
            <View style={styles.cornerTL} />
            <View style={styles.cornerTR} />
            <View style={styles.cornerBL} />
            <View style={styles.cornerBR} />
          </View>
          <Text style={styles.hint}>Point at a problem to scan</Text>
        </View>
      </CameraView>

      {analyzing && (
        <View style={styles.analyzingOverlay}>
          <GlassCard style={styles.analyzingCard}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.analyzingText}>Analyzing problem...</Text>
          </GlassCard>
        </View>
      )}

      <View style={styles.controls}>
        <TouchableOpacity
          style={styles.captureButton}
          onPress={handleCapture}
          disabled={analyzing}
        >
          <View style={styles.captureInner} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    gap: spacing.md,
  },
  permissionText: {
    color: colors.textSecondary,
    textAlign: 'center',
    fontSize: 16,
  },
  permissionButton: {
    backgroundColor: colors.primary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: 12,
  },
  permissionButtonText: {
    color: colors.bg,
    fontWeight: '600',
    fontSize: 16,
  },
  camera: {
    flex: 1,
  },
  overlay: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewfinder: {
    width: 280,
    height: 360,
    position: 'relative',
  },
  cornerTL: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: 30,
    height: 30,
    borderTopWidth: 3,
    borderLeftWidth: 3,
    borderColor: colors.primary,
  },
  cornerTR: {
    position: 'absolute',
    top: 0,
    right: 0,
    width: 30,
    height: 30,
    borderTopWidth: 3,
    borderRightWidth: 3,
    borderColor: colors.primary,
  },
  cornerBL: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    width: 30,
    height: 30,
    borderBottomWidth: 3,
    borderLeftWidth: 3,
    borderColor: colors.primary,
  },
  cornerBR: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 30,
    height: 30,
    borderBottomWidth: 3,
    borderRightWidth: 3,
    borderColor: colors.primary,
  },
  hint: {
    color: colors.textSecondary,
    fontSize: 14,
    marginTop: spacing.lg,
  },
  analyzingOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  },
  analyzingCard: {
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.md,
  },
  analyzingText: {
    color: colors.textSecondary,
    fontSize: 16,
  },
  controls: {
    position: 'absolute',
    bottom: 40,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  captureButton: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 4,
    borderColor: colors.text,
    alignItems: 'center',
    justifyContent: 'center',
  },
  captureInner: {
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: colors.text,
  },
});
