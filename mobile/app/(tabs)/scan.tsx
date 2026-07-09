import { useEffect, useRef, useState, useCallback, lazy, Suspense, Component } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Platform,
  ActivityIndicator,
  Alert,
  Animated,
  Easing,
  Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import type { ARPenCanvasHandle } from '../../src/components/ARPenCanvas';
import { api, LearningMode, BASE_URL } from '../../src/lib/api';
import { useVoice } from '../../src/lib/voice';

const CameraSection = lazy(() => import('../../src/components/CameraSection').then(m => ({ default: m.CameraSection })));
const ARPenCanvas = lazy(() => import('../../src/components/ARPenCanvas').then(m => ({ default: m.ARPenCanvas })));
const isWeb = Platform.OS === 'web';
const LINE_HEIGHT = 42;

class ScanErrorBoundary extends Component<{ children: React.ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: any) { return { error: e?.message || String(e) }; }
  render() {
    if (this.state.error) {
      return (
        <View style={{ flex: 1, backgroundColor: '#0A0A0F', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
          <Text style={{ color: '#FF3D8A', fontSize: 16, fontWeight: '700', marginBottom: 8 }}>Error</Text>
          <Text style={{ color: '#888', fontSize: 13, textAlign: 'center' }}>{this.state.error}</Text>
        </View>
      );
    }
    return this.props.children;
  }
}

export default function ARScanScreen() {
  const router = useRouter();
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [problemContent, setProblemContent] = useState('');
  const [selectedMode] = useState<LearningMode>('math');
  const [speaking, setSpeaking] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [sessionActive, setSessionActive] = useState(false);
  const [awaitingDoubts, setAwaitingDoubts] = useState(false);
  const speakAnim = useRef(new Animated.Value(0)).current;
  const cameraRef = useRef<any>(null);
  const canvasRef = useRef<ARPenCanvasHandle>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const voice = useVoice();
  const actionsQueueRef = useRef<any[]>([]);
  const processingRef = useRef(false);

  useEffect(() => {
    if (speaking) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(speakAnim, { toValue: 1, duration: 200, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
          Animated.timing(speakAnim, { toValue: 0, duration: 200, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        ]),
      ).start();
    } else {
      speakAnim.setValue(0);
    }
  }, [speaking]);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      voice.stopListening();
    };
  }, []);

  const speak = useCallback(async (text: string) => {
    setSpeaking(true);
    try { await voice.speakText(text); } catch {}
    setSpeaking(false);
  }, [voice]);

  const processActions = useCallback(async (actions: any[]) => {
    if (processingRef.current) {
      actionsQueueRef.current.push(...actions);
      return;
    }
    processingRef.current = true;
    let queue = [...actions];

    while (queue.length > 0 || actionsQueueRef.current.length > 0) {
      if (queue.length === 0) {
        queue = [...actionsQueueRef.current];
        actionsQueueRef.current = [];
      }
      const action = queue.shift();
      if (!action) continue;

      if (action.say) {
        await speak(action.say);
      } else if (action.write) {
        canvasRef.current?.write(action.write, action.color);
        await new Promise(r => setTimeout(r, 300));
      } else if (action.writeln) {
        canvasRef.current?.writeln(action.writeln, action.color);
        await new Promise(r => setTimeout(r, 300));
      } else if (action.clear) {
        canvasRef.current?.clearAll();
      } else if (action.askDoubts) {
        setAwaitingDoubts(true);
      } else if (action.sessionComplete) {
        setSessionActive(false);
        setAwaitingDoubts(false);
        await finishSession();
        return;
      }
    }
    processingRef.current = false;
  }, [speak]);

  const connectWebSocket = useCallback(async (content: string) => {
    if (wsRef.current) wsRef.current.close();
    try {
      const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/tutor/ws/tutor`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ mode: selectedMode, level: 'intermediate', content }));
        setWsConnected(true);
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'chunk') return;
          if (data.type === 'actions') {
            processActions(data.actions);
          } else if (data.type === 'done' && data.text) {
            processActions([{ say: data.text }]);
          }
        } catch {}
      };
      ws.onclose = () => setWsConnected(false);
      ws.onerror = () => setWsConnected(false);
    } catch {
      setWsConnected(false);
    }
  }, [selectedMode, processActions]);

  const sendToWs = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ text }));
    }
  }, []);

  const toggleMic = useCallback(async () => {
    if (voice.isRecording) {
      if (isWeb) {
        voice.stopListening();
      } else {
        const uri = await voice.stopRecording();
        if (uri) {
          const text = await voice.transcribeAudio(uri);
          if (text) sendToWs(text);
        }
      }
    } else {
      if (isWeb) {
        voice.startListening((text) => {
          sendToWs(text);
          voice.stopListening();
        });
      } else {
        await voice.startRecording();
      }
    }
  }, [voice, sendToWs]);

  const startSession = useCallback(async (imageUri: string) => {
    setIsScanning(true);
    try {
      const problem = await api.recognizeProblem(imageUri, selectedMode);
      if (!problem?.content || problem.content.length < 5) {
        setIsScanning(false);
        return;
      }
      setProblemContent(problem.content);
      setIsScanning(false);
      canvasRef.current?.clearAll();
      setSessionActive(true);
      await connectWebSocket(problem.content);
    } catch {
      setIsScanning(false);
    }
  }, [selectedMode, connectWebSocket]);

  const handleImageUpload = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e: any) => {
      const file = e.target?.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const uri = ev.target?.result as string;
        setUploadedImage(uri);
        startSession(uri);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  }, [startSession]);

  const takePhoto = useCallback(async () => {
    try {
      const photo = await cameraRef.current?.takePictureAsync({ base64: false, quality: 0.6 });
      if (photo?.uri) {
        setUploadedImage(photo.uri);
        startSession(photo.uri);
      }
    } catch {}
  }, [startSession]);

  const finishSession = useCallback(async () => {
    setSessionActive(false);
    try {
      const dataUrl = await canvasRef.current?.getDataUrl();
      if (!dataUrl) {
        setTimeout(() => router.back(), 1000);
        return;
      }
      if (isWeb) {
        const link = document.createElement('a');
        link.href = dataUrl;
        link.download = `solution-${Date.now()}.png`;
        link.click();
      } else {
        const FileSystem = await import('expo-file-system');
        const path = `${(FileSystem as any).documentDirectory}solution-${Date.now()}.png`;
        const base64 = dataUrl.split(',')[1];
        await FileSystem.writeAsStringAsync(path, base64, { encoding: FileSystem.EncodingType.Base64 });
        Alert.alert('Session Complete', `Solution saved to: ${path}`);
      }
    } catch {}
    setTimeout(() => router.back(), 1500);
  }, [router]);

  const showCamera = !isWeb && !uploadedImage;

  return (
    <ScanErrorBoundary>
      <View style={styles.container}>
        {showCamera && (
          <Suspense fallback={<View style={styles.cameraFallback} />}>
            <CameraSection ref={cameraRef} />
            <View style={styles.cameraOverlay}>
              <View style={styles.cameraHint}>
                <Ionicons name="scan" size={32} color={colors.primary} />
                <Text style={styles.cameraHintText}>Point at problem</Text>
              </View>
              <TouchableOpacity style={styles.captureBtn} onPress={takePhoto}>
                <View style={styles.captureInner} />
              </TouchableOpacity>
              <TouchableOpacity style={styles.uploadBtn} onPress={handleImageUpload}>
                <Ionicons name="folder-open" size={20} color={colors.text} />
                <Text style={styles.uploadBtnText}>Upload</Text>
              </TouchableOpacity>
            </View>
          </Suspense>
        )}

        {!showCamera && !sessionActive && !isScanning && (
          <View style={styles.uploadPrompt}>
            <Ionicons name="cloud-upload" size={56} color={colors.primary} />
            <Text style={styles.uploadPromptTitle}>Upload a problem</Text>
            <Text style={styles.uploadPromptSub}>Choose an image to start tutoring</Text>
            <TouchableOpacity style={styles.uploadActionBtn} onPress={handleImageUpload}>
              <Ionicons name="folder-open" size={22} color={colors.bg} />
              <Text style={styles.cameraBtnText}>Choose File</Text>
            </TouchableOpacity>
          </View>
        )}

        {isScanning && (
          <View style={styles.scanningOverlay}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.scanningText}>Reading problem...</Text>
          </View>
        )}

        {sessionActive && (
          <Suspense fallback={null}>
            <ARPenCanvas ref={canvasRef} color={colors.primary} lineWidth={3} />
          </Suspense>
        )}

        {wsConnected && (
          <View style={styles.connectionBadge}>
            <View style={[styles.liveDot, { backgroundColor: colors.success }]} />
            <Text style={styles.connectionText}>Tutoring</Text>
          </View>
        )}

        <View style={styles.topBar}>
          <TouchableOpacity style={styles.iconBtn} onPress={() => {
            if (sessionActive) {
              Alert.alert('End session?', 'Your progress will be lost.', [
                { text: 'Stay', style: 'cancel' },
                { text: 'End', onPress: () => { wsRef.current?.close(); setSessionActive(false); router.back(); } },
              ]);
            } else {
              router.back();
            }
          }}>
            <Ionicons name="close" size={22} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.titleBlock}>
            <Text style={styles.titleText} numberOfLines={1}>AR Tutor</Text>
          </View>
        </View>

        <View style={styles.controls}>
          {sessionActive && (
            <TouchableOpacity
              style={[styles.micBtn, voice.isRecording && styles.micBtnActive]}
              onPress={toggleMic}
            >
              <Ionicons
                name={voice.isRecording ? 'mic' : 'mic-outline'}
                size={28}
                color={voice.isRecording ? colors.accent : colors.text}
              />
              <Text style={styles.micText}>
                {voice.isRecording ? (voice.transcript || 'Listening...') : 'Tap to speak'}
              </Text>
            </TouchableOpacity>
          )}

          {sessionActive && !wsConnected && !isScanning && (
            <TouchableOpacity style={styles.startBtn} onPress={() => connectWebSocket(problemContent)}>
              <Text style={styles.startBtnText}>Connect</Text>
            </TouchableOpacity>
          )}

          {!sessionActive && !showCamera && !isScanning && (
            <TouchableOpacity style={styles.startBtn} onPress={() => {
              if (uploadedImage) startSession(uploadedImage);
            }}>
              <Text style={styles.startBtnText}>Start Tutoring</Text>
            </TouchableOpacity>
          )}
        </View>

        {awaitingDoubts && (
          <View style={styles.doubtsOverlay}>
            <View style={styles.doubtsCard}>
              <Ionicons name="help-circle" size={40} color={colors.warning} />
              <Text style={styles.doubtsTitle}>Any doubts?</Text>
              <Text style={styles.doubtsSub}>Tap the mic to ask, or tap below if all clear.</Text>
              <View style={styles.doubtsActions}>
                <TouchableOpacity style={styles.doubtsMicBtn} onPress={toggleMic}>
                  <Ionicons name="mic" size={22} color={colors.bg} />
                  <Text style={styles.doubtsBtnText}>Ask Doubt</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.doubtsFinishBtn} onPress={async () => {
                  setAwaitingDoubts(false);
                  setSessionActive(false);
                  await finishSession();
                }}>
                  <Text style={styles.doubtsFinishText}>No, download PNG</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {speaking && (
          <View style={styles.speakingIndicator}>
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }] }]} />
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.7 }]} />
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.5 }]} />
          </View>
        )}
      </View>
    </ScanErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  cameraFallback: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: '#000' },
  cameraOverlay: StyleSheet.absoluteFill,
  cameraHint: { position: 'absolute', top: '40%', left: 0, right: 0, alignItems: 'center', gap: 12 },
  cameraHintText: { color: colors.text, fontSize: 16, fontWeight: '600', opacity: 0.7 },
  captureBtn: { position: 'absolute', bottom: 100, alignSelf: 'center', width: 72, height: 72, borderRadius: 36, borderWidth: 4, borderColor: colors.text, alignItems: 'center', justifyContent: 'center' },
  captureInner: { width: 60, height: 60, borderRadius: 30, backgroundColor: colors.text },
  uploadBtn: { position: 'absolute', bottom: 108, right: 40, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border },
  uploadBtnText: { color: colors.text, fontSize: 13, fontWeight: '700' },
  scanningOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.7)', zIndex: 100 },
  scanningText: { color: colors.text, fontSize: 16, fontWeight: '700', marginTop: spacing.md },
  uploadPrompt: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md, backgroundColor: colors.bg },
  uploadPromptTitle: { fontSize: 22, fontWeight: '800', color: colors.text, marginTop: spacing.sm },
  uploadPromptSub: { fontSize: 14, color: colors.textSecondary, textAlign: 'center' },
  uploadActionBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md, marginTop: spacing.md },
  cameraBtnText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
  connectionBadge: { position: 'absolute', top: Platform.OS === 'ios' ? 54 : 24, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.success + '40' },
  liveDot: { width: 6, height: 6, borderRadius: 3 },
  connectionText: { color: colors.text, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  topBar: { position: 'absolute', top: Platform.OS === 'ios' ? 50 : 20, left: spacing.lg, right: spacing.lg, flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  iconBtn: { width: 42, height: 42, borderRadius: borderRadius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  titleBlock: { flex: 1, backgroundColor: colors.surface + 'D9', borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.xs },
  titleText: { color: colors.text, fontSize: 15, fontWeight: '700' },
  controls: { position: 'absolute', bottom: Platform.OS === 'ios' ? 50 : 30, left: spacing.lg, right: spacing.lg, gap: spacing.md },
  micBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: borderRadius.full, backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  micBtnActive: { borderColor: colors.accent, backgroundColor: colors.accent + '18' },
  micText: { color: colors.text, fontSize: 14, fontWeight: '600', flex: 1 },
  startBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, paddingVertical: spacing.md, borderRadius: borderRadius.full, backgroundColor: colors.primary },
  startBtnText: { color: colors.bg, fontSize: 16, fontWeight: '700' },
  speakingIndicator: { position: 'absolute', bottom: Platform.OS === 'ios' ? 120 : 100, left: 0, right: 0, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 },
  speakingBar: { width: 3, height: 16, borderRadius: 2, backgroundColor: colors.primary },
  doubtsOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.75)', zIndex: 200 },
  doubtsCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.xl, marginHorizontal: spacing.xl, alignItems: 'center', gap: spacing.md, borderWidth: 1, borderColor: colors.border, maxWidth: 340 },
  doubtsTitle: { color: colors.text, fontSize: 22, fontWeight: '800' },
  doubtsSub: { color: colors.textSecondary, fontSize: 14, textAlign: 'center' },
  doubtsActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.md, flexWrap: 'wrap', justifyContent: 'center' },
  doubtsMicBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  doubtsFinishBtn: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border },
  doubtsBtnText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
  doubtsFinishText: { color: colors.textSecondary, fontWeight: '600', fontSize: 15 },
});
