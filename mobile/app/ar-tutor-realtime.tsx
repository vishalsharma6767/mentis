import { useEffect, useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Platform,
  ActivityIndicator,
  Dimensions,
  Alert,
  Animated,
  Easing,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CameraView } from 'expo-camera';
import * as DeviceMotion from 'expo-sensors';
import { colors, spacing, borderRadius } from '../src/theme';
import { GlassCard } from '../src/components';
import { ARPenCanvas } from '../src/components/ARPenCanvas';
import { api, LearningMode } from '../src/lib/api';
import { useVoice } from '../src/lib/voice';

interface Step {
  number: number;
  instruction: string;
  explanation: string;
  hint: string;
  answer: string;
  ar_annotation?: string;
  focus?: string;
}

interface PenNote {
  text: string;
  x: number;
  y: number;
  color: string;
}

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');
const FRAME_INTERVAL = 4000;

export default function ARTutorRealtimeScreen() {
  const router = useRouter();
  const { type, mode, content, title, imageUri, difficulty } = useLocalSearchParams<{
    type: string;
    mode?: LearningMode;
    content: string;
    title: string;
    imageUri?: string;
    difficulty?: string;
  }>();
  const selectedMode = (mode ?? 'math') as LearningMode;
  const [level, setLevel] = useState<'beginner' | 'intermediate' | 'advanced'>('intermediate');
  const [loading, setLoading] = useState(true);
  const [sessionActive, setSessionActive] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [messages, setMessages] = useState<{ role: 'student' | 'teacher'; text: string }[]>([]);
  const [penNotes, setPenNotes] = useState<PenNote[]>([]);
  const [showPen, setShowPen] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [arEnabled, setArEnabled] = useState(true);
  const speakAnim = useRef(new Animated.Value(0)).current;
  const cameraRef = useRef<CameraView>(null);
  const frameTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const motionSub = useRef<{ remove: () => void } | null>(null);
  const voice = useVoice();

  const [motion, setMotion] = useState({ x: 0, y: 0, z: 0 });
  const step = steps[currentStep];
  const progress = steps.length ? Math.round(((currentStep + 1) / steps.length) * 100) : 0;

  const rotateStyle = {
    transform: [
      { perspective: 800 },
      { rotateY: motion.x * 0.08 },
      { rotateX: -motion.y * 0.06 },
    ],
  };

  const floatingStyle = {
    transform: [
      { translateX: motion.x * 6 },
      { translateY: motion.y * 4 },
    ],
  };

  const annotationStyle = {
    transform: [
      { translateX: motion.x * 10 },
      { translateY: motion.y * 8 + 40 },
    ],
  };

  useEffect(() => {
    let sub: { remove: () => void } | null = null;
    (async () => {
      const available = await DeviceMotion.isAvailableAsync();
      if (available) {
        sub = DeviceMotion.addListener((data: any) => {
          const rot = data.rotation;
          setMotion({
            x: rot?.beta ?? 0,
            y: rot?.gamma ?? 0,
            z: rot?.alpha ?? 0,
          });
        });
        await DeviceMotion.setUpdateIntervalAsync(100);
      }
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

  useEffect(() => {
    if (!sessionActive || !content) return;
    (async () => {
      setLoading(true);
      try {
        const lesson = await api.generateLesson(type ?? 'unknown', content ?? '', level, selectedMode);
        setSteps(lesson.steps ?? []);
        setCurrentStep(0);
        const first = lesson.steps?.[0];
        if (first) {
          setMessages([{ role: 'teacher', text: `Let's solve this together. ${first.instruction}` }]);
        }
      } catch {
        setMessages([{ role: 'teacher', text: 'Point your camera at a problem. I will guide you step by step.' }]);
      } finally {
        setLoading(false);
      }
    })();
  }, [sessionActive, level]);

  const startRealtimeScan = useCallback(() => {
    if (frameTimerRef.current) clearInterval(frameTimerRef.current);
    frameTimerRef.current = setInterval(async () => {
      if (!cameraRef.current || !sessionActive) return;
      try {
        const photo = await cameraRef.current.takePictureAsync({ base64: false, quality: 0.6 });
        if (!photo?.uri) return;
        const problem = await api.recognizeProblem(photo.uri, selectedMode);
        if (problem?.content && problem.content.length > 10) {
          setSessionActive(true);
        }
      } catch {}
    }, FRAME_INTERVAL);
    return () => {
      if (frameTimerRef.current) clearInterval(frameTimerRef.current);
    };
  }, [sessionActive, selectedMode]);

  useEffect(() => {
    if (!sessionActive) return;
    const stop = startRealtimeScan();
    return stop;
  }, [sessionActive, startRealtimeScan]);

  const speak = useCallback(async (text: string) => {
    setSpeaking(true);
    await voice.speakText(text);
    setSpeaking(false);
  }, [voice]);

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
            setMessages((m) => [...m, { role: 'student', text }]);
            const answer = await api.askDoubt({
              content: content ?? '',
              question: text,
              current: step,
              level,
              mode: selectedMode,
            });
            setMessages((m) => [...m, { role: 'teacher', text: `${answer.reply} ${answer.follow_up}`.trim() }]);
            setPenNotes((n) => [
              ...n,
              {
                text: answer.pen_annotation || 'Check this',
                x: 20 + Math.random() * 40,
                y: 20 + Math.random() * 40,
                color: colors.accent,
              },
            ]);
            speak(answer.reply);
          }
        } finally {
          setListening(false);
        }
      }
    } else {
      await voice.startRecording();
    }
  }, [voice, step, content, level, selectedMode, speak]);

  const writeStep = useCallback(() => {
    if (!step) return;
    const pos = { x: 15 + Math.random() * 30, y: 20 + Math.random() * 30 };
    setPenNotes((n) => [
      ...n,
      {
        text: step.ar_annotation || step.instruction,
        x: pos.x,
        y: pos.y,
        color: colors.primary,
      },
    ]);
  }, [step]);

  const nextStep = useCallback(async () => {
    if (!steps.length) return;
    const next = Math.min(steps.length - 1, currentStep + 1);
    setCurrentStep(next);
    const ns = steps[next];
    if (ns) {
      setMessages((m) => [...m, { role: 'teacher', text: ns.instruction }]);
    }
  }, [steps, currentStep]);

  const finishSession = useCallback(async () => {
    Alert.alert('Finish session?', 'Your conversation and notes will be saved as PDF.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Finish',
        onPress: async () => {
          try {
            const result = await api.createSessionPdf({
              title: title ?? 'AR Tutor Session',
              problem: content ?? '',
              steps,
              transcript: messages,
              penNotes,
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
              Alert.alert('PDF saved', path);
            }
          } catch {
            Alert.alert('Error', 'Failed to generate PDF');
          }
          router.back();
        },
      },
    ]);
  }, [steps, messages, penNotes, title, content, router]);

  const startSession = useCallback(async () => {
    setLoading(true);
    setSessionActive(true);
    setAnalyzing(true);
    try {
      const photo = cameraRef.current ? await cameraRef.current.takePictureAsync({ base64: false, quality: 0.85 }) : null;
      if (photo?.uri) {
        const problem = await api.recognizeProblem(photo.uri, selectedMode);
        if (problem?.content) {
          const lesson = await api.generateLesson(problem.type ?? 'unknown', problem.content, level, selectedMode);
          setSteps(lesson.steps ?? []);
          setCurrentStep(0);
          const first = lesson.steps?.[0];
          if (first) {
            setMessages([{ role: 'teacher', text: `Let's solve this together. ${first.instruction}` }]);
            speak(first.instruction);
          }
        }
      }
    } catch {
      setMessages([{ role: 'teacher', text: 'Point your camera at a problem and tap Start.' }]);
    } finally {
      setLoading(false);
      setAnalyzing(false);
    }
  }, [selectedMode, level, speak]);

  if (loading && !sessionActive) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingText}>Initializing AR Tutor...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back" enableTorch={false}>
        <View style={styles.cameraOverlay}>
          <View style={[styles.arFrame, { borderColor: colors.primary + '60' }]} />
          {analyzing && (
            <View style={styles.scanningOverlay}>
              <View style={[styles.scanLine, { backgroundColor: colors.primary }]} />
              <Text style={styles.scanningText}>Analyzing problem...</Text>
            </View>
          )}
        </View>
      </CameraView>

      <View style={styles.annotationLayer} pointerEvents="none">
        <View style={[styles.topAnnotation, floatingStyle]}>
          <GlassCard style={styles.statusCard}>
            <View style={styles.statusRow}>
              <View style={[styles.liveDot, { backgroundColor: sessionActive ? colors.success : colors.warning }]} />
              <Text style={styles.statusText}>{sessionActive ? 'Live Session' : 'Scanning'}</Text>
              <Text style={styles.progressText}>{progress}%</Text>
            </View>
            {step && arEnabled && (
              <Animated.View style={[styles.floatingStep, annotationStyle]}>
                <Text style={styles.floatingLabel}>Step {step.number}</Text>
                <Text style={styles.floatingText} numberOfLines={2}>{step.ar_annotation || step.instruction}</Text>
              </Animated.View>
            )}
          </GlassCard>
        </View>

        {messages.slice(-2).map((msg, i) => (
          <Animated.View key={i} style={[styles.messageOverlay, floatingStyle, { top: 120 + i * 80 }]}>
            <GlassCard style={styles.messageCard}>
              <View style={[styles.messageInner, msg.role === 'student' ? styles.studentInner : styles.teacherInner]}>
                <Text style={[styles.messageRole, { color: msg.role === 'student' ? colors.accent : colors.primary }]}>
                  {msg.role === 'student' ? 'You' : 'Mentis'}
                </Text>
                <Text style={styles.messageText} numberOfLines={2}>{msg.text}</Text>
              </View>
            </GlassCard>
          </Animated.View>
        ))}
      </View>

      <ARPenCanvas color={colors.primary} lineWidth={3} visible={showPen} />

      {penNotes.map((note, i) => (
        <View key={i} style={[styles.penNoteOverlay, { left: `${note.x}%`, top: `${note.y}%` }]}>
          <View style={[styles.penDot, { backgroundColor: note.color }]} />
          <Text style={[styles.penText, { color: note.color }]}>{note.text}</Text>
        </View>
      ))}

      <View style={styles.topBar}>
        <TouchableOpacity style={styles.iconBtn} onPress={() => router.back()}>
          <Ionicons name="close" size={22} color={colors.text} />
        </TouchableOpacity>
        <View style={styles.titleBlock}>
          <Text style={styles.titleText} numberOfLines={1}>{title ?? 'AR Tutor'}</Text>
          <Text style={styles.subtitleText}>{selectedMode} · {level}</Text>
        </View>
        <TouchableOpacity style={styles.iconBtn} onPress={() => setArEnabled(!arEnabled)}>
          <Ionicons name={arEnabled ? 'eye' : 'eye-off'} size={20} color={colors.primary} />
        </TouchableOpacity>
      </View>

      <View style={styles.controls}>
        <View style={styles.controlRow}>
          <TouchableOpacity style={[styles.ctrlBtn, listening && styles.ctrlBtnActive]} onPress={toggleListen}>
            <Ionicons name={listening ? 'mic' : 'mic-outline'} size={22} color={listening ? colors.accent : colors.text} />
            <Text style={styles.ctrlText}>{listening ? 'Listening...' : 'Talk'}</Text>
          </TouchableOpacity>

          <TouchableOpacity style={[styles.ctrlBtn, showPen && styles.ctrlBtnActive]} onPress={() => setShowPen(!showPen)}>
            <Ionicons name="create-outline" size={22} color={showPen ? colors.warning : colors.text} />
            <Text style={styles.ctrlText}>AR Pen</Text>
          </TouchableOpacity>

          {step && (
            <TouchableOpacity style={styles.ctrlBtn} onPress={writeStep}>
              <Ionicons name="pencil-outline" size={22} color={colors.secondary} />
              <Text style={styles.ctrlText}>Write Step</Text>
            </TouchableOpacity>
          )}

          {steps.length > 0 && currentStep < steps.length - 1 && (
            <TouchableOpacity style={styles.ctrlBtn} onPress={nextStep}>
              <Ionicons name="play-forward-outline" size={22} color={colors.text} />
              <Text style={styles.ctrlText}>Next</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity style={[styles.ctrlBtn, styles.finishBtn]} onPress={finishSession}>
            <Ionicons name="checkmark-circle-outline" size={22} color={colors.bg} />
            <Text style={[styles.ctrlText, { color: colors.bg }]}>Finish</Text>
          </TouchableOpacity>
        </View>

        {!sessionActive && (
          <TouchableOpacity style={styles.startBtn} onPress={startSession} disabled={analyzing}>
            {analyzing ? (
              <ActivityIndicator size="small" color={colors.bg} />
            ) : (
              <>
                <Ionicons name="scan-outline" size={22} color={colors.bg} />
                <Text style={styles.startBtnText}>Start AR Session</Text>
              </>
            )}
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
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, backgroundColor: colors.bg },
  loadingText: { color: colors.text, fontSize: 16, fontWeight: '600' },
  camera: StyleSheet.absoluteFill,
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
  },
  scanLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 2,
    opacity: 0.8,
  },
  scanningText: { color: colors.text, fontSize: 14, fontWeight: '700', marginTop: 8 },
  annotationLayer: { ...StyleSheet.absoluteFill, pointerEvents: 'none' },
  topAnnotation: { position: 'absolute', top: Platform.OS === 'ios' ? 60 : 30, left: spacing.lg, right: spacing.lg },
  statusCard: { padding: spacing.sm, marginBottom: spacing.sm },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  liveDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { flex: 1, color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  progressText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  floatingStep: { marginTop: spacing.sm, padding: spacing.sm, borderRadius: borderRadius.md, backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  floatingLabel: { color: colors.primary, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', marginBottom: 2 },
  floatingText: { color: colors.text, fontSize: 14, fontWeight: '600' },
  messageOverlay: { position: 'absolute', left: spacing.lg, right: spacing.lg },
  messageCard: { padding: spacing.sm, borderRadius: borderRadius.md, maxWidth: '80%' },
  messageInner: { borderRadius: borderRadius.md },
  studentInner: { backgroundColor: colors.accent + '20', borderColor: colors.accent + '40', alignSelf: 'flex-end', borderWidth: 1 },
  teacherInner: { backgroundColor: colors.primary + '20', borderColor: colors.primary + '40', alignSelf: 'flex-start', borderWidth: 1 },
  messageRole: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase', marginBottom: 2 },
  messageText: { color: colors.text, fontSize: 13, lineHeight: 18 },
  penNoteOverlay: { position: 'absolute', flexDirection: 'row', alignItems: 'center', gap: 6, maxWidth: '60%' },
  penDot: { width: 8, height: 8, borderRadius: 4 },
  penText: { fontSize: 13, fontWeight: '900' },
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
  finishBtn: { backgroundColor: colors.success, borderColor: colors.success },
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
