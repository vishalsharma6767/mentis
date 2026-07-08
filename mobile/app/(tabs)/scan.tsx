import { useEffect, useState, useRef } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Platform, ScrollView } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import { LearningMode, api } from '../../src/lib/api';

const isWeb = Platform.OS === 'web';

const modes: {
  id: LearningMode;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  hint: string;
}[] = [
  { id: 'math', title: 'Math', icon: 'calculator-outline', hint: 'Equations, graphs, word problems' },
  { id: 'science', title: 'Science', icon: 'flask-outline', hint: 'Diagrams, lab equipment, circuits' },
  { id: 'coding', title: 'Coding', icon: 'code-slash-outline', hint: 'Errors, snippets, algorithms' },
  { id: 'book', title: 'Book', icon: 'library-outline', hint: 'Summaries, quizzes, flashcards' },
  { id: 'homework', title: 'Homework', icon: 'document-text-outline', hint: 'Worksheet planning and help' },
  { id: 'language', title: 'Language', icon: 'language-outline', hint: 'Translate, grammar, pronunciation' },
  { id: 'diagram', title: 'Diagram', icon: 'git-network-outline', hint: 'Labels, flows, relationships' },
];

export default function ScanScreen() {
  const router = useRouter();
  const { mode } = useLocalSearchParams<{ mode?: LearningMode }>();
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedMode, setSelectedMode] = useState<LearningMode>(mode ?? 'math');

  useEffect(() => {
    if (mode) setSelectedMode(mode);
  }, [mode]);

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

  async function analyzeImage(uri: string) {
    setAnalyzing(true);
    try {
      const problem = await api.recognizeProblem(uri, selectedMode);
      router.push(
        `/ar-tutor-realtime?type=${encodeURIComponent(problem.type)}&mode=${encodeURIComponent(selectedMode)}&content=${encodeURIComponent(problem.content)}&title=${encodeURIComponent(problem.title)}&difficulty=${encodeURIComponent(problem.difficulty)}&imageUri=${encodeURIComponent(uri)}&arTargets=${encodeURIComponent(JSON.stringify(problem.arTargets ?? []))}`,
      );
    } catch (e) {
      console.error('Capture error:', e);
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleWebCapture() {
    const uri = await pickFileWeb();
    if (uri) await analyzeImage(uri);
  }

  if (isWeb) {
    return (
      <View style={styles.container}>
        <View style={styles.center}>
          <ModePicker selectedMode={selectedMode} onSelect={setSelectedMode} />
          <Ionicons name="cloud-upload-outline" size={56} color={colors.primary} />
          <Text style={styles.permissionText}>Upload a page, worksheet, diagram, code screenshot, or textbook photo.</Text>
          <TouchableOpacity style={styles.permissionButton} onPress={handleWebCapture} disabled={analyzing}>
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

  return (
    <NativeCameraView
      analyzing={analyzing}
      selectedMode={selectedMode}
      onSelectMode={setSelectedMode}
      onImageReady={analyzeImage}
    />
  );
}

function ModePicker({
  selectedMode,
  onSelect,
}: {
  selectedMode: LearningMode;
  onSelect: (mode: LearningMode) => void;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.modeRow}
    >
      {modes.map((mode) => {
        const active = selectedMode === mode.id;
        return (
          <TouchableOpacity
            key={mode.id}
            style={[styles.modeChip, active && styles.modeChipActive]}
            onPress={() => onSelect(mode.id)}
          >
            <Ionicons name={mode.icon} size={18} color={active ? colors.bg : colors.textSecondary} />
            <Text style={[styles.modeText, active && styles.modeTextActive]}>{mode.title}</Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
}

function NativeCameraView({
  analyzing,
  selectedMode,
  onSelectMode,
  onImageReady,
}: {
  analyzing: boolean;
  selectedMode: LearningMode;
  onSelectMode: (mode: LearningMode) => void;
  onImageReady: (uri: string) => void;
}) {
  const cameraRef = useRef<any>(null);
  let CameraView: any = null;
  let useCameraPermissions: any = () => [null, async () => {}];

  try {
    const mod = require('expo-camera');
    CameraView = mod.CameraView;
    useCameraPermissions = mod.useCameraPermissions;
  } catch {
    return (
      <View style={styles.container}>
        <View style={styles.center}>
          <Text style={styles.permissionText}>Camera module unavailable</Text>
        </View>
      </View>
    );
  }

  const [permission, requestPermission] = useCameraPermissions();
  const mode = modes.find((item) => item.id === selectedMode) ?? modes[0];

  async function handleCapture() {
    if (!cameraRef.current || analyzing) return;
    const photo = await cameraRef.current.takePictureAsync({ base64: false, quality: 0.85 });
    if (photo?.uri) onImageReady(photo.uri);
  }

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
      <CameraView ref={cameraRef} style={styles.camera} facing="back" ratio="4:3">
        <View style={styles.overlay}>
          <View style={styles.topPanel}>
            <ModePicker selectedMode={selectedMode} onSelect={onSelectMode} />
            <GlassCard style={styles.modeSummary}>
              <View style={styles.modeSummaryRow}>
                <Ionicons name={mode.icon} size={20} color={colors.primary} />
                <View style={styles.modeCopy}>
                  <Text style={styles.modeTitle}>{mode.title} tutor</Text>
                  <Text style={styles.modeHint}>{mode.hint}</Text>
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
          <Text style={styles.hint}>Point at the learning material and keep it inside the frame</Text>
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
  permissionText: { color: colors.textSecondary, textAlign: 'center', fontSize: 16 },
  permissionButton: { backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  permissionButtonText: { color: colors.bg, fontWeight: '600', fontSize: 16 },
  camera: { flex: 1 },
  overlay: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.lg },
  topPanel: { position: 'absolute', top: Platform.OS === 'ios' ? 58 : 28, left: 0, right: 0 },
  modeRow: { paddingHorizontal: spacing.lg, gap: spacing.sm },
  modeChip: {
    height: 38,
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
  modeSummary: { marginHorizontal: spacing.lg, marginTop: spacing.sm },
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
