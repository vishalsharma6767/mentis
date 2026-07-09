import { useState, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Platform, ScrollView } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import { LearningMode, api } from '../../src/lib/api';

const modes: {
  id: LearningMode;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  hint: string;
}[] = [
  { id: 'math', title: 'Math', icon: 'calculator', hint: 'Equations, graphs, word problems' },
  { id: 'science', title: 'Science', icon: 'flask', hint: 'Diagrams, lab equipment, circuits' },
  { id: 'coding', title: 'Coding', icon: 'code-slash', hint: 'Errors, snippets, algorithms' },
  { id: 'book', title: 'Book', icon: 'library', hint: 'Summaries, quizzes, flashcards' },
  { id: 'homework', title: 'Homework', icon: 'document-text', hint: 'Worksheet planning and help' },
  { id: 'language', title: 'Language', icon: 'language', hint: 'Translate, grammar, pronunciation' },
  { id: 'diagram', title: 'Diagram', icon: 'git-network', hint: 'Labels, flows, relationships' },
];

export default function ARScanScreen() {
  const router = useRouter();
  const { mode } = useLocalSearchParams<{ mode?: LearningMode }>();
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedMode, setSelectedMode] = useState<LearningMode>(mode ?? 'math');
  const cameraRef = useRef<any>(null);

  const handleCapture = async () => {
    if (!cameraRef.current || analyzing) return;
    setAnalyzing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: false, quality: 0.85 });
      if (photo?.uri) {
        const problem = await api.recognizeProblem(photo.uri, selectedMode);
        router.push(
          `/ar-tutor-realtime?type=${encodeURIComponent(problem.type)}&mode=${encodeURIComponent(selectedMode)}&content=${encodeURIComponent(problem.content)}&title=${encodeURIComponent(problem.title)}&difficulty=${encodeURIComponent(problem.difficulty)}&imageUri=${encodeURIComponent(photo.uri)}`
        );
      }
    } catch (e) {
      console.error('Capture error:', e);
    } finally {
      setAnalyzing(false);
    }
  };

  if (Platform.OS === 'web') {
    return (
      <View style={styles.container}>
        <View style={styles.center}>
          <Ionicons name="cloud-upload" size={56} color={colors.primary} />
          <Text style={styles.permissionText}>Upload a photo to start AR tutoring</Text>
          <TouchableOpacity style={styles.uploadButton}>
            <Text style={styles.uploadButtonText}>Choose Image</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  const [permission, requestPermission] = useCameraPermissions();

  if (!permission) {
    return <View style={styles.container} />;
  }

  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <View style={styles.center}>
          <Ionicons name="camera" size={64} color={colors.textTertiary} />
          <Text style={styles.permissionText}>Camera access needed for AR tutoring</Text>
          <TouchableOpacity style={styles.permissionButton} onPress={requestPermission}>
            <Text style={styles.permissionButtonText}>Grant Permission</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back" ratio="4:3">
        <View style={styles.overlay}>
          <View style={styles.topPanel}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.modeRow}>
            </ScrollView>
            <View style={styles.modeRow}>
              {modes.map((m) => {
                const active = selectedMode === m.id;
                return (
                  <TouchableOpacity
                    key={m.id}
                    style={[styles.modeChip, active && styles.modeChipActive]}
                    onPress={() => setSelectedMode(m.id)}
                  >
                    <Ionicons name={m.icon} size={18} color={active ? colors.bg : colors.textSecondary} />
                    <Text style={[styles.modeText, active && styles.modeTextActive]}>{m.title}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <GlassCard style={styles.modeSummary}>
              <View style={styles.modeSummaryRow}>
                <Ionicons name={modes.find((m) => m.id === selectedMode)?.icon} size={20} color={colors.primary} />
                <View style={styles.modeCopy}>
                  <Text style={styles.modeTitle}>{modes.find((m) => m.id === selectedMode)?.title} Tutor</Text>
                  <Text style={styles.modeHint}>{modes.find((m) => m.id === selectedMode)?.hint}</Text>
                </View>
              </View>
            </GlassCard>
          </View>

          <View style={styles.viewfinder}>
            <View style={styles.cornerTL} />
            <View style={styles.cornerTR} />
            <View style={styles.cornerBL} />
            <View style={styles.cornerBR} />
          </View>

          <Text style={styles.hint}>Point at your learning material</Text>
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
        <TouchableOpacity style={styles.captureButton} onPress={handleCapture} disabled={analyzing}>
          <View style={styles.captureInner} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md },
  permissionText: { color: colors.textSecondary, textAlign: 'center', fontSize: 16, marginBottom: spacing.md },
  permissionButton: { backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  permissionButtonText: { color: colors.bg, fontWeight: '600', fontSize: 16 },
  uploadButton: { backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  uploadButtonText: { color: colors.bg, fontWeight: '600', fontSize: 16 },
  camera: { flex: 1 },
  overlay: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.lg },
  topPanel: { position: 'absolute', top: Platform.OS === 'ios' ? 58 : 28, left: 0, right: 0 },
  modeRow: { paddingHorizontal: spacing.lg, gap: spacing.sm, marginBottom: spacing.sm },
  modeChip: {
    height: 36,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.full,
    backgroundColor: colors.glassDark,
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
  modeChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  modeText: { color: colors.textSecondary, fontSize: 13, fontWeight: '700' },
  modeTextActive: { color: colors.bg },
  modeSummary: { marginHorizontal: spacing.lg },
  modeSummaryRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  modeCopy: { flex: 1 },
  modeTitle: { color: colors.text, fontSize: 15, fontWeight: '700' },
  modeHint: { color: colors.textSecondary, fontSize: 12, marginTop: 2 },
  viewfinder: { width: 280, height: 360, position: 'relative' },
  cornerTL: { position: 'absolute', top: 0, left: 0, width: 30, height: 30, borderTopWidth: 3, borderLeftWidth: 3, borderColor: colors.primary },
  cornerTR: { position: 'absolute', top: 0, right: 0, width: 30, height: 30, borderTopWidth: 3, borderRightWidth: 3, borderColor: colors.primary },
  cornerBL: { position: 'absolute', bottom: 0, left: 0, width: 30, height: 30, borderBottomWidth: 3, borderLeftWidth: 3, borderColor: colors.primary },
  cornerBR: { position: 'absolute', bottom: 0, right: 0, width: 30, height: 30, borderBottomWidth: 3, borderRightWidth: 3, borderColor: colors.primary },
  hint: { color: colors.textSecondary, fontSize: 14, marginTop: spacing.lg },
  analyzingOverlay: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center', zIndex: 10 },
  analyzingCard: { padding: spacing.xl, alignItems: 'center', gap: spacing.md },
  analyzingText: { color: colors.textSecondary, fontSize: 16 },
  controls: { position: 'absolute', bottom: 40, left: 0, right: 0, alignItems: 'center' },
  captureButton: { width: 76, height: 76, borderRadius: 38, borderWidth: 4, borderColor: colors.text, alignItems: 'center', justifyContent: 'center' },
  captureInner: { width: 62, height: 62, borderRadius: 31, backgroundColor: colors.text },
});
