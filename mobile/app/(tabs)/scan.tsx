import { useEffect, useRef, useState, useCallback } from 'react';
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
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as DeviceMotion from 'expo-sensors';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import { ARPenCanvas } from '../../src/components/ARPenCanvas';
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

interface PenNote {
  text: string;
  x: number;
  y: number;
  color: string;
}

const SCAN_INTERVAL = 4000;
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
  const [level, setLevel] = useState<'beginner' | 'intermediate' | 'advanced'>('intermediate');
  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [messages, setMessages] = useState<Message[]>([]);
  const [penNotes, setPenNotes] = useState<PenNote[]>([]);
  const [showPen, setShowPen] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [arEnabled, setArEnabled] = useState(true);
  const [streamingText, setStreamingText] = useState('');
  const [motion, setMotion] = useState({ x: 0, y: 0, z: 0 });
  const [problemContent, setProblemContent] = useState('');
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const speakAnim = useRef(new Animated.Value(0)).current;
  const scanAnim = useRef(new Animated.Value(0)).current;
  const cameraRef = useRef<CameraView>(null);
  const scanTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const motionSub = useRef<{ remove: () => void } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const analyzingRef = useRef(false);
  const loadingRef = useRef(false);
  const streamingTextRef = useRef('');
  const messagesRef = useRef<Message[]>([]);
  const voice = useVoice();

  const step = steps[currentStep];
  const progress = steps.length ? Math.round(((currentStep + 1) / steps.length) * 100) : 0;

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
      try {
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

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(scanAnim, { toValue: 1, duration: 2000, easing: Easing.linear, useNativeDriver: true }),
        Animated.timing(scanAnim, { toValue: 0, duration: 2000, easing: Easing.linear, useNativeDriver: true }),
      ]),
    ).start();
  }, []);

  const speak = useCallback(async (text: string) => {
    setSpeaking(true);
    try {
      await voice.speakText(text);
    } catch {}
    setSpeaking(false);
  }, [voice]);

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
              messagesRef.current = [...messagesRef.current, { role: 'teacher', text: full }];
              setMessages(messagesRef.current);
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
    messagesRef.current = [...messagesRef.current, { role: 'student', text }];
    setMessages(messagesRef.current);
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
        messagesRef.current = [...messagesRef.current, { role: 'teacher', text: `${answer.reply} ${answer.follow_up}`.trim() }];
        setMessages(messagesRef.current);
        setPenNotes((n) => [
          ...n,
          {
            text: answer.pen_annotation || 'Check this',
            x: 20 + Math.random() * 40,
            y: 20 + Math.random() * 40,
            color: colors.accent,
          },
        ]);
      } catch {
        messagesRef.current = [...messagesRef.current, { role: 'teacher', text: 'Tell me which step feels unclear.' }];
        setMessages(messagesRef.current);
      }
    }
  }, [connectWebSocket, step, level, selectedMode, problemContent]);

  const recognizeAndTutor = useCallback(async () => {
    if (analyzingRef.current || loadingRef.current) return;
    analyzingRef.current = true;
    setAnalyzing(true);
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
      setSteps(lessonSteps);
      setCurrentStep(0);
      const first = lessonSteps[0];
      if (first) {
        const msg = `I scanned your problem: "${problem.content.slice(0, 80)}${problem.content.length > 80 ? '...' : ''}". Let's solve it. ${first.instruction}`;
        messagesRef.current = [{ role: 'teacher', text: msg }];
        setMessages(messagesRef.current);
        speak(msg);
      }
      setSessionActive(true);
    } catch {
      messagesRef.current = [{ role: 'teacher', text: 'Point your camera at a problem or upload an image. I will guide you step by step.' }];
      setMessages(messagesRef.current);
    } finally {
      analyzingRef.current = false;
      loadingRef.current = false;
      setAnalyzing(false);
      setLoading(false);
    }
  }, [selectedMode, level, speak, uploadedImage]);

  useEffect(() => {
    if (!sessionActive) return;
    scanTimerRef.current = setInterval(() => {
      recognizeAndTutor();
    }, SCAN_INTERVAL);
    return () => {
      if (scanTimerRef.current) clearInterval(scanTimerRef.current);
    };
  }, [sessionActive, recognizeAndTutor]);

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
            const msgs = messagesRef.current;
            const reply = [...msgs].reverse().find((m) => m.role === 'teacher')?.text || 'Good question. Try the next small step.';
            speak(reply);
          }
        } finally {
          setListening(false);
        }
      }
    } else {
      await voice.startRecording();
    }
  }, [voice, sendVoiceMessage, speak]);

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
      messagesRef.current = [...messagesRef.current, { role: 'teacher', text: ns.instruction }];
      setMessages(messagesRef.current);
      speak(ns.instruction);
    }
  }, [steps, currentStep, speak]);

  const prevStep = useCallback(async () => {
    if (!steps.length || currentStep <= 0) return;
    const prev = currentStep - 1;
    setCurrentStep(prev);
    const ps = steps[prev];
    if (ps) {
      messagesRef.current = [...messagesRef.current, { role: 'teacher', text: `Going back: ${ps.instruction}` }];
      setMessages(messagesRef.current);
      speak(ps.instruction);
    }
  }, [steps, currentStep, speak]);

  const exportCanvas = useCallback(async (): Promise<string | null> => {
    if (Platform.OS === 'web') {
      const cvs = document.querySelector('canvas');
      if (cvs) return cvs.toDataURL('image/png');
      return null;
    }
    return null;
  }, []);

  const finishSession = useCallback(async () => {
    Alert.alert('Finish session?', 'Your conversation, AR pen drawings, and notes will be saved as a PDF.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Finish',
        onPress: async () => {
          try {
            const canvasDataUrl = await exportCanvas();
            const penCanvasNote = canvasDataUrl ? [{ text: 'AR Pen Drawing', x: 50, y: 10, color: colors.primary, imageData: canvasDataUrl }] : [];
            const result = await api.createSessionPdf({
              title: `AR Tutor Session - ${selectedMode}`,
              problem: problemContent || 'Scanned problem',
              steps,
              transcript: messagesRef.current,
              penNotes: [...penNotes, ...penCanvasNote],
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
  }, [steps, penNotes, router, problemContent, selectedMode, exportCanvas]);

  const handleImageUpload = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e: any) => {
      const file = e.target?.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        const dataUrl = ev.target?.result as string;
        setUploadedImage(dataUrl);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  }, []);

  useEffect(() => {
    return () => {
      if (scanTimerRef.current) clearInterval(scanTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const [permission, requestPermission] = useCameraPermissions();

  if (!permission) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const showCamera = permission.granted && Platform.OS !== 'web' && !uploadedImage;

  return (
    <View style={styles.container}>
      {showCamera ? (
        <CameraView ref={cameraRef} style={styles.camera} facing="back" enableTorch={false}>
          <View style={styles.cameraOverlay}>
            <View style={[styles.arFrame, { borderColor: colors.primary + '60' }]} />
            {(analyzing || loading) && (
              <View style={styles.scanningOverlay}>
                <Animated.View style={[styles.scanLine, { backgroundColor: colors.primary, transform: [{ translateY: scanAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 300] }) }] }]} />
                <Text style={styles.scanningText}>{loading ? 'Preparing lesson...' : 'Scanning...'}</Text>
              </View>
            )}
            {!uploadedImage && (
              <TouchableOpacity style={styles.uploadBtn} onPress={handleImageUpload}>
                <Ionicons name="cloud-upload-outline" size={20} color={colors.text} />
                <Text style={styles.uploadBtnText}>Upload Image</Text>
              </TouchableOpacity>
            )}
          </View>
        </CameraView>
      ) : (
        <View style={styles.imagePreviewContainer}>
          {uploadedImage ? (
            <View style={styles.imagePreviewWrapper}>
              <View style={[styles.arFrame, { borderColor: colors.primary + '60', position: 'absolute', zIndex: 2 }]} />
              {(analyzing || loading) && (
                <View style={styles.scanningOverlay}>
                  <Animated.View style={[styles.scanLine, { backgroundColor: colors.primary, transform: [{ translateY: scanAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 300] }) }] }]} />
                  <Text style={styles.scanningText}>{loading ? 'Preparing lesson...' : 'Scanning...'}</Text>
                </View>
              )}
              {/* eslint-disable-next-line jsx-a11y/alt-text */}
              <img src={uploadedImage} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
              <TouchableOpacity style={styles.retakeBtn} onPress={() => setUploadedImage(null)}>
                <Ionicons name="camera-outline" size={20} color={colors.text} />
                <Text style={styles.uploadBtnText}>Use Camera</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={styles.uploadPrompt}>
              <Ionicons name="cloud-upload" size={56} color={colors.primary} />
              <Text style={styles.uploadPromptTitle}>Upload a problem</Text>
              <Text style={styles.uploadPromptSub}>Take a photo or choose an image of your problem</Text>
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

      <View style={styles.annotationLayer} pointerEvents="none">
        <View style={[styles.topAnnotation, floatingStyle]}>
          <GlassCard style={styles.statusCard}>
            <View style={styles.statusRow}>
              <View style={[styles.liveDot, { backgroundColor: sessionActive ? colors.success : colors.warning }]} />
              <Text style={styles.statusText}>{sessionActive ? 'Live Session' : 'Ready'}</Text>
              <Text style={styles.progressText}>{progress}%</Text>
            </View>
            {step && arEnabled && (
              <Animated.View style={[styles.floatingStep, annotationStyle]}>
                <Text style={styles.floatingLabel}>Step {step.number} of {steps.length}</Text>
                <Text style={styles.floatingText} numberOfLines={2}>{step.ar_annotation || step.instruction}</Text>
              </Animated.View>
            )}
          </GlassCard>
        </View>

        {messagesRef.current.length > 0 && (
          <ScrollView
            style={styles.messagesScroll}
            contentContainerStyle={styles.messagesContent}
            showsVerticalScrollIndicator={false}
          >
            {messagesRef.current.slice(-4).map((msg, i) => (
              <View key={i} style={[styles.messageOverlay, { marginBottom: 8 }]}>
                <GlassCard style={styles.messageCard}>
                  <View style={[styles.messageInner, msg.role === 'student' ? styles.studentInner : styles.teacherInner]}>
                    <Text style={[styles.messageRole, { color: msg.role === 'student' ? colors.accent : colors.primary }]}>
                      {msg.role === 'student' ? 'You' : 'Mentis'}
                    </Text>
                    <Text style={styles.messageText} numberOfLines={3}>{msg.text}</Text>
                  </View>
                </GlassCard>
              </View>
            ))}
            {streamingText ? (
              <View style={styles.messageOverlay}>
                <GlassCard style={styles.messageCard}>
                  <View style={[styles.messageInner, styles.teacherInner]}>
                    <Text style={[styles.messageRole, { color: colors.primary }]}>Mentis</Text>
                    <Text style={styles.messageText}>{streamingText}</Text>
                  </View>
                </GlassCard>
              </View>
            ) : null}
          </ScrollView>
        )}
      </View>

      {!sessionActive && !uploadedImage && Platform.OS === 'web' && !permission.granted && (
        <View style={styles.modeSelector}>
          <Text style={styles.modeSelectorTitle}>Select Mode</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.modeRow}>
            {MODES.map((m) => {
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
          </ScrollView>
        </View>
      )}

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
          <Text style={styles.titleText} numberOfLines={1}>AR Tutor</Text>
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

          {steps.length > 0 && currentStep > 0 && (
            <TouchableOpacity style={styles.ctrlBtn} onPress={prevStep}>
              <Ionicons name="play-back-outline" size={22} color={colors.text} />
              <Text style={styles.ctrlText}>Back</Text>
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
          <TouchableOpacity style={styles.startBtn} onPress={recognizeAndTutor} disabled={analyzing || loading}>
            {(analyzing || loading) ? (
              <ActivityIndicator size="small" color={colors.bg} />
            ) : (
              <>
                <Ionicons name="scan-outline" size={22} color={colors.bg} />
                <Text style={styles.startBtnText}>{uploadedImage ? 'Scan Uploaded Image' : 'Start Live AR Tutor'}</Text>
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
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg },
  permissionContainer: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md, backgroundColor: colors.bg },
  permissionText: { color: colors.textSecondary, textAlign: 'center', fontSize: 16, marginBottom: spacing.md },
  permissionButton: { backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  permissionButtonText: { color: colors.bg, fontWeight: '600', fontSize: 16 },
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
    height: 3,
    opacity: 0.9,
  },
  scanningText: { color: colors.text, fontSize: 14, fontWeight: '700', marginTop: 8 },
  uploadBtn: { position: 'absolute', bottom: 20, right: 20, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border },
  uploadBtnText: { color: colors.text, fontSize: 13, fontWeight: '700' },
  retakeBtn: { position: 'absolute', bottom: 20, left: 20, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border },
  imagePreviewContainer: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  imagePreviewWrapper: { flex: 1, position: 'relative' },
  uploadPrompt: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md, backgroundColor: colors.bg },
  uploadPromptTitle: { fontSize: 22, fontWeight: '800', color: colors.text, marginTop: spacing.sm },
  uploadPromptSub: { fontSize: 14, color: colors.textSecondary, textAlign: 'center' },
  uploadActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.md },
  cameraBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  cameraBtnText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
  uploadActionBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.secondary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  annotationLayer: { ...StyleSheet.absoluteFill },
  topAnnotation: { position: 'absolute', top: Platform.OS === 'ios' ? 60 : 30, left: spacing.lg, right: spacing.lg },
  statusCard: { padding: spacing.sm, marginBottom: spacing.sm },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  liveDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { flex: 1, color: colors.text, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  progressText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  floatingStep: { marginTop: spacing.sm, padding: spacing.sm, borderRadius: borderRadius.md, backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  floatingLabel: { color: colors.primary, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', marginBottom: 2 },
  floatingText: { color: colors.text, fontSize: 14, fontWeight: '600' },
  messagesScroll: { position: 'absolute', top: Platform.OS === 'ios' ? 130 : 100, left: spacing.lg, right: spacing.lg, maxHeight: 200 },
  messagesContent: { gap: 4 },
  messageOverlay: {},
  messageCard: { padding: spacing.sm, borderRadius: borderRadius.md, maxWidth: '85%' },
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
  modeSelector: { position: 'absolute', top: Platform.OS === 'ios' ? 110 : 80, left: 0, right: 0, paddingHorizontal: spacing.lg },
  modeSelectorTitle: { color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: spacing.sm, textTransform: 'uppercase' },
  modeRow: { gap: spacing.sm },
  modeChip: { height: 36, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: spacing.md, borderRadius: borderRadius.full, backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  modeChipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  modeText: { color: colors.textSecondary, fontSize: 13, fontWeight: '700' },
  modeTextActive: { color: colors.bg },
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
