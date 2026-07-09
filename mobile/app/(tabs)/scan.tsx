import { useEffect, useRef, useState, useCallback, lazy, Suspense } from 'react';
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
  ScrollView,
  Image,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
const CameraSection = lazy(() => import('../../src/components/CameraSection').then(m => ({ default: m.CameraSection })));
const ARPenCanvas = lazy(() => import('../../src/components/ARPenCanvas').then(m => ({ default: m.ARPenCanvas })));
import type { ARPenCanvasHandle } from '../../src/components/ARPenCanvas';
import { api, LearningMode, BASE_URL } from '../../src/lib/api';
import { useVoice } from '../../src/lib/voice';

interface Step {
  number: number;
  instruction: string;
  explanation: string;
  hint: string;
  answer: string;
  ar_annotation?: string;
  focus?: string;
}

interface Message {
  role: 'student' | 'teacher';
  text: string;
}

const SCAN_INTERVAL = 4000;
const STEP_DELAY = 6000;
const MODES: { id: LearningMode; title: string; icon: keyof typeof Ionicons.glyphMap; hint: string }[] = [
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
  const [selectedMode, setSelectedMode] = useState<LearningMode>(mode ?? 'math');
  const [sessionActive, setSessionActive] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [level] = useState<'beginner' | 'intermediate' | 'advanced'>('intermediate');
  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const [showPen, setShowPen] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [motion, setMotion] = useState({ x: 0, y: 0, z: 0 });
  const [problemContent, setProblemContent] = useState('');
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [phase, setPhase] = useState<'idle' | 'scanning' | 'tutoring' | 'doubts' | 'finished'>('idle');
  const speakAnim = useRef(new Animated.Value(0)).current;
  const cameraRef = useRef<any>(null);
  const scanTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stepTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const motionSub = useRef<{ remove: () => void } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const analyzingRef = useRef(false);
  const loadingRef = useRef(false);
  const canvasRef = useRef<ARPenCanvasHandle>(null);
  const streamingTextRef = useRef('');
  const stepIndexRef = useRef(0);
  const voice = useVoice();

  const step = steps[stepIndexRef.current];
  const progress = steps.length ? Math.round(((stepIndexRef.current + 1) / steps.length) * 100) : 0;

  const floatingStyle = {
    transform: [
      { translateX: motion.x * 6 },
      { translateY: motion.y * 4 },
    ],
  };

  useEffect(() => {
    let sub: { remove: () => void } | null = null;
    (async () => {
      try {
        const mod = await import('expo-sensors');
        const dm = (mod as any).DeviceMotion || mod;
        const available = await dm.isAvailableAsync();
        if (available) {
          sub = dm.addListener((data: any) => {
            const rot = data.rotation;
            setMotion({
              x: rot?.beta ?? 0,
              y: rot?.gamma ?? 0,
              z: rot?.alpha ?? 0,
            });
          });
          await dm.setUpdateIntervalAsync(100);
        }
      } catch {}
    })();
    motionSub.current = sub;
    return () => { sub?.remove(); };
  }, []);

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

  const speak = useCallback(async (text: string) => {
    setSpeaking(true);
    try {
      await voice.speakText(text);
    } catch {}
    setSpeaking(false);
  }, [voice]);

  const drawStepOnCanvas = useCallback((stepNum: number, instruction: string, explanation: string) => {
    if (!canvasRef.current) return;
    const col = colors.primary;
    const yBase = 40 + (stepNum - 1) * 90;
    canvasRef.current.drawStepBox(stepNum, instruction, explanation, 30, yBase, col);
    if (stepNum > 1) {
      canvasRef.current.drawArrow(160, yBase - 10, 160, yBase + 5, col);
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    try {
      const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/tutor/ws/tutor`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ mode: selectedMode, level, content: problemContent || '' }));
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'chunk') {
            streamingTextRef.current += data.text;
            setStreamingText(streamingTextRef.current);
          } else if (data.type === 'done') {
            const full = data.text || streamingTextRef.current;
            if (full) {
              setMessages((m) => [...m, { role: 'teacher', text: full }]);
              setStreamingText('');
              streamingTextRef.current = '';
            }
          }
        } catch {}
      };
      ws.onerror = () => {};
      ws.onclose = () => {};
    } catch {}
  }, [selectedMode, level, problemContent]);

  const sendVoiceMessage = useCallback(async (text: string) => {
    if (!text) return;
    setMessages((m) => [...m, { role: 'student', text }]);
    setStreamingText('');
    streamingTextRef.current = '';
    connectWebSocket();
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ text }));
    } else {
      try {
        const answer = await api.askDoubt({
          content: problemContent || '',
          question: text,
          current: step,
          level,
          mode: selectedMode,
        });
        setMessages((m) => [...m, { role: 'teacher', text: `${answer.reply} ${answer.follow_up}`.trim() }]);
      } catch {
        setMessages((m) => [...m, { role: 'teacher', text: 'Tell me which step feels unclear.' }]);
      }
    }
  }, [connectWebSocket, step, level, selectedMode, problemContent]);

  const finishAndExport = useCallback(async () => {
    if (phase === 'finished') return;
    setPhase('finished');
    try {
      const canvasDataUrl = await canvasRef.current?.getDataUrl();
      const currentMessages = messagesRef.current;
      const currentSteps = steps;
      const result = await api.createSessionPdf({
        title: `AR Tutor Session - ${selectedMode}`,
        problem: problemContent || 'Scanned problem',
        steps: currentSteps.map((s) => ({
          number: s.number,
          instruction: s.instruction,
          explanation: s.explanation,
          answer: s.answer,
        })),
        transcript: currentMessages.map((m) => ({ role: m.role, text: m.text })),
        penNotes: canvasDataUrl ? [{ text: 'AR Pen Drawing', x: 50, y: 10, color: colors.primary, imageData: canvasDataUrl }] : [],
      });
      if (Platform.OS === 'web') {
        const link = document.createElement('a');
        link.href = `data:application/pdf;base64,${result.base64}`;
        link.download = result.filename;
        link.click();
      } else {
        const FileSystem = await import('expo-file-system');
        const path = `${(FileSystem as any).documentDirectory}${result.filename}`;
        await FileSystem.writeAsStringAsync(path, result.base64, { encoding: FileSystem.EncodingType.Base64 });
      }
    } catch {}
    setTimeout(() => router.back(), 2000);
  }, [steps, router, problemContent, selectedMode, phase, messagesRef]);

  const autoAdvanceSteps = useCallback(async (lessonSteps: Step[]) => {
    setPhase('tutoring');
    for (let i = 0; i < lessonSteps.length; i++) {
      stepIndexRef.current = i;
      setCurrentStep(i);
      const s = lessonSteps[i];
      drawStepOnCanvas(i + 1, s.instruction, s.explanation || s.answer);
      setMessages((m) => [...m, { role: 'teacher', text: `Step ${i + 1}: ${s.instruction}` }]);
      const started = Date.now();
      await speak(s.ar_annotation || s.instruction);
      const elapsed = Date.now() - started;
      const remaining = Math.max(0, STEP_DELAY - elapsed);
      if (i < lessonSteps.length - 1) {
        await new Promise((resolve) => {
          stepTimerRef.current = setTimeout(resolve, remaining);
        });
      }
    }
    setPhase('doubts');
    const doubtMsg = 'I have finished explaining the solution. Do you have any doubts? You can ask me by tapping the mic button. If not, I will save your PDF.';
    setMessages((m) => [...m, { role: 'teacher', text: doubtMsg }]);
    await speak(doubtMsg);
    const timeout = setTimeout(async () => {
      if (phase !== 'finished') await finishAndExport();
    }, 15000);
    stepTimerRef.current = timeout;
  }, [speak, drawStepOnCanvas, phase, finishAndExport]);

  const recognizeAndTutor = useCallback(async () => {
    if (analyzingRef.current || loadingRef.current) return;
    analyzingRef.current = true;
    setAnalyzing(true);
    setPhase('scanning');
    try {
      const photo = uploadedImage ? null : await cameraRef.current?.takePictureAsync({ base64: false, quality: 0.6 });
      const imageUri = uploadedImage || photo?.uri;
      if (!imageUri) return;
      const problem = await api.recognizeProblem(imageUri, selectedMode);
      if (!problem?.content || problem.content.length < 5) return;
      setProblemContent(problem.content);
      loadingRef.current = true;
      setLoading(true);
      const lesson = await api.generateLesson(problem.type ?? 'unknown', problem.content, level, selectedMode);
      const lessonSteps = lesson.steps ?? [];
      if (!lessonSteps.length) {
        setMessages([{ role: 'teacher', text: 'I could not generate steps. Try again.' }]);
        setPhase('idle');
        return;
      }
      setSteps(lessonSteps);
      canvasRef.current?.clearAll();
      const scanMsg = `I scanned your problem. Let me explain the solution step by step.`;
      setMessages([{ role: 'teacher', text: scanMsg }]);
      await speak(scanMsg);
      autoAdvanceSteps(lessonSteps);
    } catch {
      setMessages([{ role: 'teacher', text: 'Point your camera at a problem or upload an image.' }]);
      setPhase('idle');
    } finally {
      analyzingRef.current = false;
      loadingRef.current = false;
      setAnalyzing(false);
      setLoading(false);
    }
  }, [selectedMode, level, speak, uploadedImage, autoAdvanceSteps]);

  const toggleListen = useCallback(async () => {
    if (voice.isSpeaking) {
      voice.stopSpeaking();
      setSpeaking(false);
      return;
    }
    if (voice.isRecording) {
      const uri = await voice.stopRecording();
      if (uri) {
        setListening(true);
        try {
          const text = await voice.transcribeAudio(uri);
          if (text) {
            await sendVoiceMessage(text);
            const reply = messages.findLast?.((m) => m.role === 'teacher')?.text;
            if (reply) speak(reply);
          }
        } finally {
          setListening(false);
        }
      }
    } else {
      await voice.startRecording();
    }
  }, [voice, sendVoiceMessage, messages, speak]);

  const handleImageUpload = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (e: any) => {
      const file = e.target?.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        setUploadedImage(ev.target?.result as string);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  }, []);

  useEffect(() => {
    return () => {
      if (scanTimerRef.current) clearInterval(scanTimerRef.current);
      if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const isWeb = Platform.OS === 'web';
  const showCamera = !isWeb && !uploadedImage && phase === 'idle';

  return (
    <View style={styles.container}>
      {showCamera && (
        <Suspense fallback={<View style={styles.cameraFallback} />}>
          <CameraSection ref={cameraRef} />
          <View style={styles.cameraOverlay}>
            <View style={[styles.arFrame, { borderColor: colors.primary + '60' }]} />
            {(phase as string) === 'scanning' && (
              <View style={styles.scanningOverlay}>
                <Text style={styles.scanningText}>{loading ? 'Preparing lesson...' : 'Scanning...'}</Text>
              </View>
            )}
            {!uploadedImage && phase === 'idle' && (
              <TouchableOpacity style={styles.uploadBtn} onPress={handleImageUpload}>
                <Ionicons name="cloud-upload-outline" size={20} color={colors.text} />
                <Text style={styles.uploadBtnText}>Upload Image</Text>
              </TouchableOpacity>
            )}
          </View>
        </Suspense>
      )}
      {!showCamera && (
        <View style={styles.imagePreviewContainer}>
          {uploadedImage ? (
            <View style={styles.imagePreviewWrapper}>
              {(phase === 'idle' || phase === 'scanning') && (
                <View style={[styles.arFrame, { borderColor: colors.primary + '60', position: 'absolute', zIndex: 2 }]} />
              )}
              {phase === 'scanning' && (
                <View style={styles.scanningOverlay}>
                  <Text style={styles.scanningText}>{loading ? 'Preparing lesson...' : 'Scanning...'}</Text>
                </View>
              )}
              <Image source={{ uri: uploadedImage }} style={{ width: '100%', height: '100%' }} resizeMode="contain" />
              {phase === 'idle' && (
                <TouchableOpacity style={styles.retakeBtn} onPress={() => { setUploadedImage(null); canvasRef.current?.clearAll(); }}>
                  <Ionicons name="camera-outline" size={20} color={colors.text} />
                  <Text style={styles.uploadBtnText}>Use Camera</Text>
                </TouchableOpacity>
              )}
            </View>
          ) : (
            <View style={styles.uploadPrompt}>
              <Ionicons name="cloud-upload" size={56} color={colors.primary} />
              <Text style={styles.uploadPromptTitle}>Upload a problem</Text>
              <Text style={styles.uploadPromptSub}>Choose an image of your problem to receive step-by-step tutoring</Text>
              <View style={styles.uploadActions}>
                <TouchableOpacity style={styles.uploadActionBtn} onPress={handleImageUpload}>
                  <Ionicons name="folder-open" size={22} color={colors.bg} />
                  <Text style={styles.cameraBtnText}>Choose File</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </View>
      )}

      {phase === 'tutoring' && (
        <View style={styles.annotationLayer} pointerEvents="none">
          <View style={[styles.topAnnotation, floatingStyle]}>
            <GlassCard style={styles.statusCard}>
              <View style={styles.statusRow}>
                <View style={[styles.liveDot, { backgroundColor: colors.success }]} />
                <Text style={styles.statusText}>Step {stepIndexRef.current + 1} of {steps.length}</Text>
                <Text style={styles.progressText}>{progress}%</Text>
              </View>
            </GlassCard>
          </View>

          {messages.length > 0 && (
            <View style={styles.currentMessage}>
              <GlassCard style={styles.messageCard}>
                <View style={[styles.messageInner, styles.teacherInner]}>
                  <Text style={[styles.messageRole, { color: colors.primary }]}>Mentis</Text>
                  <Text style={styles.messageText} numberOfLines={3}>{messages[messages.length - 1]?.text}</Text>
                </View>
              </GlassCard>
            </View>
          )}
        </View>
      )}

      {phase === 'doubts' && (
        <View style={styles.doubtsOverlay}>
          <GlassCard style={styles.doubtsCard}>
            <Ionicons name="help-circle" size={40} color={colors.warning} />
            <Text style={styles.doubtsTitle}>Any doubts?</Text>
            <Text style={styles.doubtsSub}>Tap the mic to ask a question, or wait for the PDF to download.</Text>
            <TouchableOpacity style={styles.doubtsFinishBtn} onPress={finishAndExport}>
              <Text style={styles.doubtsFinishText}>Download PDF Now</Text>
            </TouchableOpacity>
          </GlassCard>
        </View>
      )}

      {phase === 'finished' && (
        <View style={styles.doubtsOverlay}>
          <GlassCard style={styles.doubtsCard}>
            <Ionicons name="checkmark-circle" size={40} color={colors.success} />
            <Text style={styles.doubtsTitle}>Session Complete!</Text>
            <Text style={styles.doubtsSub}>Your PDF has been downloaded. Redirecting...</Text>
          </GlassCard>
        </View>
      )}

      {!isWeb && showPen && phase === 'tutoring' && (
        <Suspense fallback={null}>
          <ARPenCanvas ref={canvasRef} color={colors.primary} lineWidth={3} />
        </Suspense>
      )}

      <View style={styles.topBar}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => {
          if (phase === 'tutoring' || phase === 'scanning') {
            Alert.alert('End session?', 'Your progress will be lost.', [
              { text: 'Stay', style: 'cancel' },
              { text: 'End', onPress: () => router.back() },
            ]);
          } else {
            router.back();
          }
        }}>
          <Ionicons name="close" size={22} color={colors.text} />
        </TouchableOpacity>
        <View style={styles.titleBlock}>
          <Text style={styles.titleText} numberOfLines={1}>AR Tutor</Text>
          <Text style={styles.subtitleText}>{selectedMode} · {level}</Text>
        </View>
      </View>

      <View style={styles.controls}>
        <View style={styles.controlRow}>
          {phase !== 'finished' && (
            <TouchableOpacity style={[styles.ctrlBtn, listening && styles.ctrlBtnActive]} onPress={toggleListen}>
              <Ionicons name={listening ? 'mic' : 'mic-outline'} size={22} color={listening ? colors.accent : colors.text} />
              <Text style={styles.ctrlText}>{listening ? 'Listening...' : 'Ask Doubt'}</Text>
            </TouchableOpacity>
          )}
        </View>

        {phase === 'idle' && (
          <TouchableOpacity style={styles.startBtn} onPress={recognizeAndTutor} disabled={analyzing || loading}>
            {(analyzing || loading) ? (
              <ActivityIndicator size="small" color={colors.bg} />
            ) : (
              <>
                <Ionicons name="scan-outline" size={22} color={colors.bg} />
                <Text style={styles.startBtnText}>{uploadedImage ? 'Scan & Start Tutoring' : 'Start AR Tutor'}</Text>
              </>
            )}
          </TouchableOpacity>
        )}

        {phase === 'doubts' && (
          <TouchableOpacity style={styles.startBtn} onPress={finishAndExport}>
            <Ionicons name="download-outline" size={22} color={colors.bg} />
            <Text style={styles.startBtnText}>Download PDF</Text>
          </TouchableOpacity>
        )}
      </View>

      {speaking && (
        <View style={styles.speakingIndicator}>
          <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }] }]} />
          <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.7 }]} />
          <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.5 }]} />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg },
  cameraFallback: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: '#000' },
  cameraOverlay: StyleSheet.absoluteFill,
  arFrame: {
    position: 'absolute',
    top: '15%',
    left: '10%',
    right: '10%',
    height: '55%',
    borderWidth: 2,
    borderRadius: borderRadius.lg,
    borderStyle: 'dashed',
  },
  scanningOverlay: {
    position: 'absolute',
    top: '15%',
    left: '10%',
    right: '10%',
    height: '55%',
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  scanningText: { color: colors.text, fontSize: 16, fontWeight: '700' },
  uploadBtn: { position: 'absolute', bottom: 20, right: 20, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border },
  uploadBtnText: { color: colors.text, fontSize: 13, fontWeight: '700' },
  retakeBtn: { position: 'absolute', bottom: 20, left: 20, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border },
  imagePreviewContainer: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  imagePreviewWrapper: { flex: 1, position: 'relative' },
  uploadPrompt: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md, backgroundColor: colors.bg },
  uploadPromptTitle: { fontSize: 22, fontWeight: '800', color: colors.text, marginTop: spacing.sm },
  uploadPromptSub: { fontSize: 14, color: colors.textSecondary, textAlign: 'center' },
  uploadActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.md },
  uploadActionBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  cameraBtnText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
  annotationLayer: { ...StyleSheet.absoluteFill },
  topAnnotation: { position: 'absolute', top: Platform.OS === 'ios' ? 60 : 30, left: spacing.lg, right: spacing.lg },
  statusCard: { padding: spacing.sm },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  liveDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { flex: 1, color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  progressText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  currentMessage: { position: 'absolute', bottom: 120, left: spacing.lg, right: spacing.lg },
  messageCard: { padding: spacing.sm, borderRadius: borderRadius.md },
  messageInner: { borderRadius: borderRadius.md },
  teacherInner: { backgroundColor: colors.primary + '20', borderColor: colors.primary + '40', borderWidth: 1 },
  messageRole: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase', marginBottom: 2 },
  messageText: { color: colors.text, fontSize: 13, lineHeight: 18 },
  doubtsOverlay: { ...StyleSheet.absoluteFill, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.7)', zIndex: 100 },
  doubtsCard: { padding: spacing.xl, alignItems: 'center', gap: spacing.md, marginHorizontal: spacing.xl, borderRadius: borderRadius.lg },
  doubtsTitle: { color: colors.text, fontSize: 22, fontWeight: '800' },
  doubtsSub: { color: colors.textSecondary, fontSize: 14, textAlign: 'center' },
  doubtsFinishBtn: { backgroundColor: colors.primary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: borderRadius.md, marginTop: spacing.md },
  doubtsFinishText: { color: colors.bg, fontWeight: '700', fontSize: 16 },
  topBar: {
    position: 'absolute',
    top: Platform.OS === 'ios' ? 50 : 20,
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  iconBtn: { width: 42, height: 42, borderRadius: borderRadius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  titleBlock: { flex: 1, backgroundColor: colors.surface + 'D9', borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.xs },
  titleText: { color: colors.text, fontSize: 15, fontWeight: '700' },
  subtitleText: { color: colors.textTertiary, fontSize: 11 },
  controls: { position: 'absolute', bottom: Platform.OS === 'ios' ? 50 : 30, left: spacing.lg, right: spacing.lg, gap: spacing.md },
  controlRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  ctrlBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.full,
    backgroundColor: colors.surface + 'E6',
    borderWidth: 1,
    borderColor: colors.border,
  },
  ctrlBtnActive: { borderColor: colors.accent, backgroundColor: colors.accent + '18' },
  ctrlText: { color: colors.text, fontSize: 12, fontWeight: '700' },
  startBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.md,
    borderRadius: borderRadius.full,
    backgroundColor: colors.primary,
  },
  startBtnText: { color: colors.bg, fontSize: 16, fontWeight: '700' },
  speakingIndicator: { position: 'absolute', bottom: Platform.OS === 'ios' ? 120 : 100, left: 0, right: 0, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 },
  speakingBar: { width: 3, height: 16, borderRadius: 2, backgroundColor: colors.primary },
});
