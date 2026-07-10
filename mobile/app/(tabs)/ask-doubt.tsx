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
  Modal,
  TextInput,
  ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import type { ARPenCanvasHandle } from '../../src/components/ARPenCanvas';
import { api, BASE_URL } from '../../src/lib/api';
import { useVoice } from '../../src/lib/voice';
import { restoreSession } from '../../src/lib/auth';

const CameraSection = lazy(() => import('../../src/components/CameraSection').then(m => ({ default: m.CameraSection })));
const ARPenCanvas = lazy(() => import('../../src/components/ARPenCanvas').then(m => ({ default: m.ARPenCanvas })));
const isWeb = Platform.OS === 'web';

type SessionPhase =
  | 'idle' | 'capturing' | 'analyzing' | 'building_scene'
  | 'planning' | 'teaching' | 'question' | 'interacting'
  | 'homework' | 'quiz' | 'complete' | 'error';

interface HomeworkItem {
  title: string;
  description: string;
  difficulty?: string;
}

interface QuizItem {
  question: string;
  options: string[];
  correct_answer: string;
  explanation: string;
}

class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: string | null }> {
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

const PHASE_MESSAGES: Record<string, string> = {
  analyzing_image: 'Image pakad raha hoon... 📸',
  building_scene: 'Problem samajh raha hoon... 🤔',
  planning_lesson: 'Sabak taiyar kar raha hoon... 📚',
  default: 'Processing... ⏳',
};

const PHASE_ANIMATION_DURATION = 800;

export default function AskDoubtScreen() {
  const router = useRouter();
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [problemContent, setProblemContent] = useState('');
  const [speaking, setSpeaking] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [sessionActive, setSessionActive] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [phase, setPhase] = useState<SessionPhase>('idle');
  const [processingPhase, setProcessingPhase] = useState('');
  const [responseText, setResponseText] = useState('');
  const [showResponse, setShowResponse] = useState(false);
  const [showTypeModal, setShowTypeModal] = useState(false);
  const [typeInput, setTypeInput] = useState('');
  const [awaitingDoubts, setAwaitingDoubts] = useState(false);
  const [homework, setHomework] = useState<HomeworkItem[]>([]);
  const [quiz, setQuiz] = useState<QuizItem | null>(null);
  const [quizSelected, setQuizSelected] = useState<number | null>(null);
  const [quizResult, setQuizResult] = useState<boolean | null>(null);
  const [keyPoints, setKeyPoints] = useState<string[]>([]);
  const [concepts, setConcepts] = useState<string[]>([]);
  const [errorMessage, setErrorMessage] = useState('');
  const [userId, setUserId] = useState('anonymous');

  const speakAnim = useRef(new Animated.Value(0)).current;
  const phaseAnim = useRef(new Animated.Value(0)).current;
  const cameraRef = useRef<any>(null);
  const canvasRef = useRef<ARPenCanvasHandle>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const voice = useVoice();
  const actionsQueueRef = useRef<any[]>([]);
  const processingRef = useRef(false);

  const setSessionPhase = useCallback((p: SessionPhase) => {
    setPhase(p);
    Animated.sequence([
      Animated.timing(phaseAnim, { toValue: 0, duration: 100, useNativeDriver: true }),
      Animated.timing(phaseAnim, { toValue: 1, duration: 300, useNativeDriver: true }),
    ]).start();
  }, []);

  useEffect(() => {
    restoreSession().then(s => { if (s?.userId) setUserId(s.userId); });
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

  const saveSession = useCallback(async () => {
    try {
      await api.saveSessionV1({
        userId,
        sessionId,
        problemTitle: problemContent.slice(0, 80),
        problemType: 'doubt',
        extractedText: problemContent,
        explanation: responseText,
        keyPoints,
        concepts,
        homework,
        quiz: quiz || {},
        memoryUpdate: {},
      });
    } catch {}
  }, [userId, sessionId, problemContent, responseText, keyPoints, concepts, homework, quiz]);

  const finishSession = useCallback(async () => {
    try {
      await saveSession();
      await new Promise(r => setTimeout(r, 300));
      const dataUrl = await canvasRef.current?.getDataUrl();
      setSessionActive(false);
      setShowResponse(false);
      setSessionPhase('complete');
      if (!dataUrl) {
        setTimeout(() => router.back(), 2000);
        return;
      }
      if (isWeb) {
        const link = document.createElement('a');
        link.href = dataUrl;
        link.download = `solution-${Date.now()}.png`;
        link.click();
      } else {
        try {
          const FileSystem = await import('expo-file-system');
          const path = `${(FileSystem as any).documentDirectory}solution-${Date.now()}.png`;
          const base64 = dataUrl.split(',')[1];
          await FileSystem.writeAsStringAsync(path, base64, { encoding: FileSystem.EncodingType.Base64 });
        } catch {}
      }
    } catch {}
    setTimeout(() => router.back(), 2000);
  }, [saveSession, router]);

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
        await new Promise(r => setTimeout(r, 100));
      } else if (action.writeln) {
        canvasRef.current?.writeln(action.writeln, action.color);
        await new Promise(r => setTimeout(r, 100));
      } else if (action.clear) {
        canvasRef.current?.clearAll();
      } else if (action.line) {
        canvasRef.current?.drawLine(action.line.x1, action.line.y1, action.line.x2, action.line.y2, action.line.color);
      } else if (action.arrow) {
        canvasRef.current?.drawArrow(action.arrow.x1, action.arrow.y1, action.arrow.x2, action.arrow.y2, action.arrow.color);
      } else if (action.circle) {
        canvasRef.current?.drawCircle(action.circle.x, action.circle.y, action.circle.radius, action.circle.color);
      } else if (action.underline) {
        canvasRef.current?.drawUnderline(action.underline.y, action.underline.width, action.underline.color);
      } else if (action.askDoubts) {
        setAwaitingDoubts(true);
        setSessionPhase('question');
      } else if (action.sessionComplete) {
        setAwaitingDoubts(false);
        await finishSession();
        return;
      }
    }
    processingRef.current = false;
  }, [speak, finishSession]);

  const handleWsMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'processing':
          setProcessingPhase(data.phase || '');
          if (data.phase === 'analyzing_image') setSessionPhase('analyzing');
          else if (data.phase === 'building_scene') setSessionPhase('building_scene');
          else if (data.phase === 'planning_lesson') setSessionPhase('planning');
          break;

        case 'speech':
          setResponseText(prev => prev + data.text + '\n');
          setShowResponse(true);
          setSessionPhase('teaching');
          processActions([{ say: data.text }]);
          break;

        case 'board':
          processActions([{ write: data.text, color: data.color }]);
          break;

        case 'pointer':
          processActions([{ circle: data, color: data.color }]);
          break;

        case 'thinking':
          setResponseText(prev => prev + '🤔 ' + (data.text || 'Thinking...') + '\n');
          break;

        case 'question':
          setResponseText(prev => prev + '\n❓ ' + data.text + '\n');
          setAwaitingDoubts(true);
          setSessionPhase('question');
          break;

        case 'lesson_plan':
          if (data.homework?.length) setHomework(data.homework);
          if (data.key_concepts?.length) setConcepts(data.key_concepts);
          break;

        case 'key_points':
          setKeyPoints(data.points || []);
          break;

        case 'concepts':
          setConcepts(data.topics || []);
          break;

        case 'homework':
          setHomework(data.problems || []);
          break;

        case 'quiz':
          setQuiz(data.questions || null);
          setQuizSelected(null);
          setQuizResult(null);
          setSessionPhase('quiz');
          break;

        case 'memory':
          break;

        case 'done':
          setSessionId(data.session_id || sessionId);
          setSessionPhase('homework');
          break;

        case 'session_complete':
          setSessionPhase('complete');
          saveSession();
          break;

        case 'error':
          setErrorMessage(data.message || 'Something went wrong');
          setSessionPhase('error');
          break;

        case 'cancelled':
          wsRef.current?.close();
          setSessionActive(false);
          router.back();
          break;
      }
    } catch {}
  }, [processActions, sessionId, saveSession, router]);

  const connectWebSocket = useCallback(async (content: string, mode = 'math', level = 'intermediate') => {
    if (wsRef.current) wsRef.current.close();
    setResponseText('');
    setHomework([]);
    setQuiz(null);
    setKeyPoints([]);
    setConcepts([]);
    setErrorMessage('');
    setQuizSelected(null);
    setQuizResult(null);
    setAwaitingDoubts(false);

    try {
      const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/v1/teach/stream`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'doubt', content, mode, level }));
        setWsConnected(true);
      };
      ws.onmessage = handleWsMessage;
      ws.onclose = () => setWsConnected(false);
      ws.onerror = () => {
        setWsConnected(false);
        setErrorMessage('Connection lost. Check your network.');
        setSessionPhase('error');
      };
    } catch {
      setWsConnected(false);
      setErrorMessage('Failed to connect. Please try again.');
      setSessionPhase('error');
    }
  }, [handleWsMessage]);

  const submitTypedDoubt = useCallback(() => {
    const text = typeInput.trim();
    if (text.length < 3) return;
    setShowTypeModal(false);
    setTypeInput('');
    setProblemContent(text);
    canvasRef.current?.clearAll();
    setSessionActive(true);
    setSessionPhase('planning');
    connectWebSocket(text);
  }, [typeInput, connectWebSocket]);

  const startSessionWithImage = useCallback(async (imageUri: string) => {
    setUploadedImage(imageUri);
    setSessionActive(true);
    setSessionPhase('analyzing');

    try {
      const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/v1/teach/stream`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => {
        const imageBase64 = imageUri.startsWith('data:') ? imageUri.split(',')[1] : imageUri;
        ws.send(JSON.stringify({ type: 'doubt_image', image_base64: imageBase64, mode: 'math', level: 'intermediate' }));
        setWsConnected(true);
      };
      ws.onmessage = handleWsMessage;
      ws.onclose = () => setWsConnected(false);
      ws.onerror = () => {
        setWsConnected(false);
        setErrorMessage('Vision processing failed. Please try again.');
        setSessionPhase('error');
      };
    } catch {
      setWsConnected(false);
      setErrorMessage('Failed to connect. Check your network.');
      setSessionPhase('error');
    }
  }, [handleWsMessage]);

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
        startSessionWithImage(uri);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  }, [startSessionWithImage]);

  const takePhoto = useCallback(async () => {
    try {
      const photo = await cameraRef.current?.takePictureAsync({ base64: false, quality: 0.6 });
      if (photo?.uri) startSessionWithImage(photo.uri);
    } catch {
      setErrorMessage('Camera capture failed. Try uploading instead.');
      setSessionPhase('error');
    }
  }, [startSessionWithImage]);

  const sendToWs = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'student_response', text }));
      setSessionPhase('teaching');
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

  const handleRetry = useCallback(() => {
    setSessionPhase('idle');
    setErrorMessage('');
    setUploadedImage(null);
    setProblemContent('');
    setResponseText('');
    setSessionActive(false);
    setWsConnected(false);
    setShowResponse(false);
    canvasRef.current?.clearAll();
  }, []);

  const handleQuizAnswer = useCallback((idx: number) => {
    if (!quiz || quizResult !== null) return;
    setQuizSelected(idx);
    const correct = quiz.options[idx] === quiz.correct_answer;
    setQuizResult(correct);
  }, [quiz, quizResult]);

  const handleFinishHomework = useCallback(async () => {
    await finishSession();
  }, [finishSession]);

  const handleAskAnotherDoubt = useCallback(() => {
    setHomework([]);
    setQuiz(null);
    setKeyPoints([]);
    setConcepts([]);
    setResponseText('');
    setShowResponse(false);
    setAwaitingDoubts(false);
    setQuizSelected(null);
    setQuizResult(null);
    setErrorMessage('');
    setSessionActive(true);
    setSessionPhase('idle');
    setShowTypeModal(true);
  }, []);

  const showCamera = !isWeb && !uploadedImage && phase === 'idle';

  const processingMsg = PHASE_MESSAGES[processingPhase] || PHASE_MESSAGES.default;

  return (
    <ErrorBoundary>
      <View style={styles.container}>
        {/* Processing overlay */}
        {['analyzing', 'building_scene', 'planning'].includes(phase) && (
          <View style={styles.processingOverlay}>
            <Animated.View style={[styles.processingCard, { opacity: phaseAnim, transform: [{ scale: phaseAnim.interpolate({ inputRange: [0, 1], outputRange: [0.8, 1] }) }] }]}>
              <View style={styles.processingAnimation}>
                <View style={styles.processingRing}>
                  <ActivityIndicator size="large" color={colors.primary} />
                </View>
              </View>
              <Text style={styles.processingTitle}>Mentis samajh raha hai...</Text>
              <Text style={styles.processingText}>{processingMsg}</Text>
              <Text style={styles.processingHint}>
                {phase === 'analyzing' ? 'Image ko process kar raha hoon' :
                 phase === 'building_scene' ? 'Problem structure bana raha hoon' :
                 'Teacher ko taiyar kar raha hoon'}
              </Text>
              {wsConnected && (
                <View style={styles.processingLive}>
                  <View style={styles.liveDot} />
                  <Text style={styles.processingLiveText}>Live</Text>
                </View>
              )}
            </Animated.View>
          </View>
        )}

        {/* Camera view */}
        {showCamera && (
          <Suspense fallback={<View style={styles.cameraFallback} />}>
            <CameraSection ref={cameraRef} />
            <View style={styles.cameraOverlay}>
              <View style={styles.cameraHint}>
                <Ionicons name="camera" size={32} color={colors.primary} />
                <Text style={styles.cameraHintText}>Capture your doubt</Text>
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

        {/* Upload prompt (web) */}
        {phase === 'idle' && !showCamera && !sessionActive && (
          <View style={styles.uploadPrompt}>
            <Ionicons name="camera" size={56} color={colors.primary} />
            <Text style={styles.uploadPromptTitle}>Ask a Doubt</Text>
            <Text style={styles.uploadPromptSub}>Capture or upload a problem, or type below</Text>
            <TouchableOpacity style={styles.uploadActionBtn} onPress={handleImageUpload}>
              <Ionicons name="folder-open" size={22} color={colors.bg} />
              <Text style={styles.cameraBtnText}>Upload Image</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.typeBtn} onPress={() => setShowTypeModal(true)}>
              <Ionicons name="create" size={22} color={colors.primary} />
              <Text style={styles.typeBtnText}>Type Doubt</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Teacher canvas */}
        {sessionActive && ['teaching', 'question', 'interacting', 'homework', 'quiz', 'complete'].includes(phase) && (
          <Suspense fallback={null}>
            <ARPenCanvas ref={canvasRef} color={colors.primary} lineWidth={3} />
          </Suspense>
        )}

        {/* Response panel */}
        {showResponse && responseText && phase !== 'complete' && (
          <View style={styles.responsePanel}>
            <ScrollView style={styles.responseScroll}>
              <Text style={styles.responseText}>{responseText}</Text>
            </ScrollView>
          </View>
        )}

        {/* Homework panel */}
        {phase === 'homework' && homework.length > 0 && (
          <View style={styles.panelOverlay}>
            <Animated.View style={[styles.panelCard, { opacity: phaseAnim }]}>
              <View style={styles.panelHeader}>
                <Ionicons name="book" size={28} color={colors.warning} />
                <Text style={styles.panelTitle}>Practice Time! 📝</Text>
              </View>
              <ScrollView style={styles.homeworkList}>
                {homework.map((item, i) => (
                  <View key={i} style={styles.homeworkItem}>
                    <View style={styles.homeworkBullet}>
                      <Text style={styles.homeworkNum}>{i + 1}</Text>
                    </View>
                    <View style={styles.homeworkContent}>
                      <Text style={styles.homeworkTitle}>{item.title}</Text>
                      <Text style={styles.homeworkDesc}>{item.description}</Text>
                      {item.difficulty && (
                        <View style={styles.difficultyBadge}>
                          <Text style={styles.difficultyText}>{item.difficulty}</Text>
                        </View>
                      )}
                    </View>
                  </View>
                ))}
              </ScrollView>
              {concepts.length > 0 && (
                <View style={styles.conceptsRow}>
                  {concepts.map((c, i) => (
                    <View key={i} style={styles.conceptChip}>
                      <Text style={styles.conceptChipText}>{c}</Text>
                    </View>
                  ))}
                </View>
              )}
              <View style={styles.panelActions}>
                <TouchableOpacity style={styles.panelAskBtn} onPress={handleAskAnotherDoubt}>
                  <Ionicons name="add-circle" size={18} color={colors.primary} />
                  <Text style={styles.panelAskText}>Another doubt</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.panelFinishBtn} onPress={handleFinishHomework}>
                  <Ionicons name="checkmark-circle" size={18} color={colors.bg} />
                  <Text style={styles.panelFinishText}>Complete</Text>
                </TouchableOpacity>
              </View>
            </Animated.View>
          </View>
        )}

        {/* Quiz panel */}
        {phase === 'quiz' && quiz && (
          <View style={styles.panelOverlay}>
            <Animated.View style={[styles.panelCard, { opacity: phaseAnim }]}>
              <View style={styles.panelHeader}>
                <Ionicons name="bulb" size={28} color={colors.accent} />
                <Text style={styles.panelTitle}>Quick Quiz! 🧠</Text>
              </View>
              <Text style={styles.quizQuestion}>{quiz.question}</Text>
              <View style={styles.quizOptions}>
                {quiz.options.map((opt, i) => {
                  const isSelected = quizSelected === i;
                  const isCorrect = quizResult !== null && opt === quiz.correct_answer;
                  const isWrong = quizResult !== null && isSelected && opt !== quiz.correct_answer;
                  return (
                    <TouchableOpacity
                      key={i}
                      style={[
                        styles.quizOption,
                        isSelected && styles.quizOptionSelected,
                        isCorrect && styles.quizOptionCorrect,
                        isWrong && styles.quizOptionWrong,
                      ]}
                      onPress={() => handleQuizAnswer(i)}
                      disabled={quizResult !== null}
                    >
                      <Text style={styles.quizOptionLetter}>{String.fromCharCode(65 + i)}</Text>
                      <Text style={[
                        styles.quizOptionText,
                        isSelected && styles.quizOptionTextSelected,
                      ]}>{opt}</Text>
                      {isCorrect && <Ionicons name="checkmark-circle" size={20} color={colors.success} />}
                      {isWrong && <Ionicons name="close-circle" size={20} color="#FF3D8A" />}
                    </TouchableOpacity>
                  );
                })}
              </View>
              {quizResult !== null && (
                <View style={styles.quizResultBox}>
                  <Text style={[
                    styles.quizResultText,
                    { color: quizResult ? colors.success : '#FF3D8A' },
                  ]}>
                    {quizResult ? 'Sahi jawab! 🎉' : 'Galat jawab. Sahi jawab: ' + quiz.correct_answer}
                  </Text>
                  <Text style={styles.quizExplanation}>{quiz.explanation}</Text>
                  <TouchableOpacity
                    style={styles.quizContinueBtn}
                    onPress={() => { setSessionPhase('homework'); }}
                  >
                    <Text style={styles.quizContinueText}>Continue</Text>
                    <Ionicons name="arrow-forward" size={18} color={colors.bg} />
                  </TouchableOpacity>
                </View>
              )}
            </Animated.View>
          </View>
        )}

        {/* Complete screen */}
        {phase === 'complete' && (
          <View style={styles.completeOverlay}>
            <Animated.View style={[styles.completeCard, { opacity: phaseAnim, transform: [{ scale: phaseAnim }] }]}>
              <View style={styles.completeIcon}>
                <Ionicons name="checkmark-circle" size={64} color={colors.success} />
              </View>
              <Text style={styles.completeTitle}>Session Complete! 🎉</Text>
              <Text style={styles.completeSub}>Great job today, beta!</Text>
              {keyPoints.length > 0 && (
                <View style={styles.completeSection}>
                  <Text style={styles.completeSectionTitle}>Key Points</Text>
                  {keyPoints.map((pt, i) => (
                    <View key={i} style={styles.completePointRow}>
                      <Ionicons name="bulb" size={14} color={colors.warning} />
                      <Text style={styles.completePointText}>{pt}</Text>
                    </View>
                  ))}
                </View>
              )}
              {concepts.length > 0 && (
                <View style={styles.completeConcepts}>
                  {concepts.map((c, i) => (
                    <View key={i} style={styles.conceptChip}>
                      <Text style={styles.conceptChipText}>{c}</Text>
                    </View>
                  ))}
                </View>
              )}
              <TouchableOpacity style={styles.completeBtn} onPress={() => router.back()}>
                <Text style={styles.completeBtnText}>Back to Dashboard</Text>
              </TouchableOpacity>
            </Animated.View>
          </View>
        )}

        {/* Error screen */}
        {phase === 'error' && (
          <View style={styles.completeOverlay}>
            <View style={styles.completeCard}>
              <Ionicons name="alert-circle" size={56} color={colors.warning} />
              <Text style={styles.completeTitle}>Oops! 😅</Text>
              <Text style={styles.errorDetail}>{errorMessage}</Text>
              <View style={styles.errorActions}>
                <TouchableOpacity style={styles.errorRetryBtn} onPress={handleRetry}>
                  <Ionicons name="refresh" size={20} color={colors.bg} />
                  <Text style={styles.errorRetryText}>Try Again</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.errorBackBtn} onPress={() => router.back()}>
                  <Text style={styles.errorBackText}>Go Back</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {/* Doubts overlay */}
        {awaitingDoubts && phase === 'question' && (
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
                  setSessionPhase('homework');
                  await saveSession();
                }}>
                  <Text style={styles.doubtsFinishText}>All clear</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        )}

        {/* Speaking indicator */}
        {speaking && (
          <View style={styles.speakingIndicator}>
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }] }]} />
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.7 }]} />
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.5 }]} />
          </View>
        )}

        {/* WS connection badge */}
        {wsConnected && ['teaching', 'question', 'interacting'].includes(phase) && (
          <View style={styles.connectionBadge}>
            <View style={[styles.liveDot, { backgroundColor: colors.success }]} />
            <Text style={styles.connectionText}>Teaching</Text>
          </View>
        )}

        {/* Top bar */}
        <View style={styles.topBar}>
          <TouchableOpacity style={styles.iconBtn} onPress={() => {
            if (sessionActive) {
              Alert.alert('End session?', 'Your progress will be saved.', [
                { text: 'Stay', style: 'cancel' },
                { text: 'End', onPress: () => { wsRef.current?.close(); setSessionActive(false); saveSession(); router.back(); } },
              ]);
            } else {
              router.back();
            }
          }}>
            <Ionicons name="close" size={22} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.titleBlock}>
            <Text style={styles.titleText} numberOfLines={1}>
              {phase === 'analyzing' ? 'Analyzing...' :
               phase === 'teaching' ? 'Teaching' :
               phase === 'question' ? 'Your Turn' :
               phase === 'quiz' ? 'Quiz' :
               phase === 'homework' ? 'Practice' :
               phase === 'complete' ? 'Done!' : 'Ask Doubt'}
            </Text>
          </View>
        </View>

        {/* Controls */}
        <View style={styles.controls}>
          {['teaching', 'question', 'interacting'].includes(phase) && (
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

          {sessionActive && !wsConnected && !['analyzing', 'building_scene', 'planning'].includes(phase) && phase !== 'error' && (
            <TouchableOpacity style={styles.startBtn} onPress={() => connectWebSocket(problemContent)}>
              <Text style={styles.startBtnText}>Reconnect</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Type doubt modal */}
        <Modal visible={showTypeModal} transparent animationType="fade">
          <View style={styles.modalOverlay}>
            <View style={styles.modalCard}>
              <Ionicons name="create" size={36} color={colors.primary} />
              <Text style={styles.modalTitle}>Type Your Doubt</Text>
              <TextInput
                style={styles.modalInput}
                placeholder="e.g. Solve x^2 + 5x + 6 = 0"
                placeholderTextColor={colors.textTertiary}
                value={typeInput}
                onChangeText={setTypeInput}
                multiline
                autoFocus
              />
              <View style={styles.modalActions}>
                <TouchableOpacity style={styles.modalCancelBtn} onPress={() => { setShowTypeModal(false); setTypeInput(''); }}>
                  <Text style={styles.modalCancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.modalSubmitBtn} onPress={submitTypedDoubt}>
                  <Ionicons name="arrow-forward" size={18} color={colors.bg} />
                  <Text style={styles.modalSubmitText}>Teach Me</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      </View>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  cameraFallback: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: '#000' },
  cameraOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  cameraHint: { position: 'absolute', top: '40%', left: 0, right: 0, alignItems: 'center', gap: 12 },
  cameraHintText: { color: colors.text, fontSize: 16, fontWeight: '600', opacity: 0.7 },
  captureBtn: { position: 'absolute', bottom: 100, alignSelf: 'center', width: 72, height: 72, borderRadius: 36, borderWidth: 4, borderColor: colors.text, alignItems: 'center', justifyContent: 'center' },
  captureInner: { width: 60, height: 60, borderRadius: 30, backgroundColor: colors.text },
  uploadBtn: { position: 'absolute', bottom: 108, right: 40, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.border },
  uploadBtnText: { color: colors.text, fontSize: 13, fontWeight: '700' },

  // Processing
  processingOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 100 },
  processingCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.xl, marginHorizontal: spacing.xl, alignItems: 'center', gap: spacing.md, borderWidth: 1, borderColor: colors.border, maxWidth: 340, width: '100%' },
  processingAnimation: { width: 80, height: 80, alignItems: 'center', justifyContent: 'center' },
  processingRing: { width: 64, height: 64, borderRadius: 32, borderWidth: 3, borderColor: colors.primary + '40', alignItems: 'center', justifyContent: 'center' },
  processingTitle: { fontSize: 18, fontWeight: '800', color: colors.text, marginTop: spacing.sm },
  processingText: { fontSize: 15, color: colors.primary, fontWeight: '600' },
  processingHint: { fontSize: 12, color: colors.textTertiary },
  processingLive: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.success + '20', paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: 6 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success },
  processingLiveText: { fontSize: 10, color: colors.success, fontWeight: '700' },

  // Upload prompt
  uploadPrompt: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.md, backgroundColor: colors.bg },
  uploadPromptTitle: { fontSize: 22, fontWeight: '800', color: colors.text, marginTop: spacing.sm },
  uploadPromptSub: { fontSize: 14, color: colors.textSecondary, textAlign: 'center' },
  uploadActionBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md, marginTop: spacing.md },
  typeBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.primary },
  typeBtnText: { color: colors.primary, fontWeight: '700', fontSize: 15 },
  cameraBtnText: { color: colors.bg, fontWeight: '700', fontSize: 15 },

  // Response panel
  responsePanel: { position: 'absolute', top: 100, left: spacing.md, right: spacing.md, maxHeight: 180, backgroundColor: colors.surface + 'E6', borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, zIndex: 50 },
  responseScroll: { maxHeight: 140 },
  responseText: { color: colors.text, fontSize: 13, lineHeight: 18 },

  // Panel (homework/quiz)
  panelOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.75)', zIndex: 200 },
  panelCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.lg, marginHorizontal: spacing.lg, width: '90%', maxWidth: 400, maxHeight: '80%', borderWidth: 1, borderColor: colors.border, gap: spacing.md },
  panelHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.xs },
  panelTitle: { fontSize: 20, fontWeight: '800', color: colors.text },
  panelActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
  panelAskBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.primary },
  panelAskText: { color: colors.primary, fontWeight: '600', fontSize: 13 },
  panelFinishBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, backgroundColor: colors.primary, paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderRadius: borderRadius.md, flex: 1 },
  panelFinishText: { color: colors.bg, fontWeight: '700', fontSize: 14 },

  // Homework
  homeworkList: { maxHeight: 250 },
  homeworkItem: { flexDirection: 'row', gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border + '60' },
  homeworkBullet: { width: 24, height: 24, borderRadius: 12, backgroundColor: colors.primary + '30', alignItems: 'center', justifyContent: 'center' },
  homeworkNum: { color: colors.primary, fontSize: 12, fontWeight: '700' },
  homeworkContent: { flex: 1, gap: 2 },
  homeworkTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  homeworkDesc: { color: colors.textSecondary, fontSize: 12, lineHeight: 16 },
  difficultyBadge: { alignSelf: 'flex-start', backgroundColor: colors.warning + '25', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, marginTop: 4 },
  difficultyText: { fontSize: 10, color: colors.warning, fontWeight: '600' },
  conceptsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  conceptChip: { backgroundColor: colors.primary + '20', paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: colors.primary + '30' },
  conceptChipText: { fontSize: 11, color: colors.primary, fontWeight: '600' },

  // Quiz
  quizQuestion: { fontSize: 16, fontWeight: '600', color: colors.text, lineHeight: 22, marginBottom: spacing.md },
  quizOptions: { gap: spacing.sm },
  quizOption: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, padding: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg },
  quizOptionSelected: { borderColor: colors.primary, backgroundColor: colors.primary + '15' },
  quizOptionCorrect: { borderColor: colors.success, backgroundColor: colors.success + '20' },
  quizOptionWrong: { borderColor: '#FF3D8A', backgroundColor: '#FF3D8A20' },
  quizOptionLetter: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', fontWeight: '700', fontSize: 13, color: colors.text, borderWidth: 1, borderColor: colors.border, textAlign: 'center', lineHeight: 26 },
  quizOptionText: { flex: 1, fontSize: 14, color: colors.text },
  quizOptionTextSelected: { fontWeight: '600' },
  quizResultBox: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.bg, borderRadius: borderRadius.md, gap: spacing.sm },
  quizResultText: { fontSize: 16, fontWeight: '700' },
  quizExplanation: { fontSize: 13, color: colors.textSecondary, lineHeight: 18 },
  quizContinueBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, backgroundColor: colors.primary, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: borderRadius.md, marginTop: spacing.sm },
  quizContinueText: { color: colors.bg, fontWeight: '700', fontSize: 14 },

  // Complete
  completeOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 200 },
  completeCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.xl, marginHorizontal: spacing.xl, alignItems: 'center', gap: spacing.md, borderWidth: 1, borderColor: colors.border, maxWidth: 360, width: '90%' },
  completeIcon: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.success + '20', alignItems: 'center', justifyContent: 'center', marginBottom: spacing.sm },
  completeTitle: { fontSize: 22, fontWeight: '800', color: colors.text },
  completeSub: { fontSize: 14, color: colors.textSecondary },
  completeSection: { width: '100%', gap: spacing.xs, marginTop: spacing.sm },
  completeSectionTitle: { fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 4 },
  completePointRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  completePointText: { fontSize: 13, color: colors.textSecondary, flex: 1 },
  completeConcepts: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.sm },
  completeBtn: { backgroundColor: colors.primary, paddingVertical: spacing.md, paddingHorizontal: spacing.xl, borderRadius: borderRadius.md, marginTop: spacing.md, width: '100%', alignItems: 'center' },
  completeBtnText: { color: colors.bg, fontWeight: '700', fontSize: 16 },

  // Error
  errorDetail: { fontSize: 14, color: colors.textSecondary, textAlign: 'center', lineHeight: 20 },
  errorActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.md },
  errorRetryBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  errorRetryText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
  errorBackBtn: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border },
  errorBackText: { color: colors.textSecondary, fontWeight: '600', fontSize: 15 },

  // Connection badge
  connectionBadge: { position: 'absolute', top: Platform.OS === 'ios' ? 54 : 24, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.surface + 'E6', paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: borderRadius.full, borderWidth: 1, borderColor: colors.success + '40' },
  connectionText: { color: colors.text, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },

  // Top bar
  topBar: { position: 'absolute', top: Platform.OS === 'ios' ? 50 : 20, left: spacing.lg, right: spacing.lg, flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  iconBtn: { width: 42, height: 42, borderRadius: borderRadius.md, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  titleBlock: { flex: 1, backgroundColor: colors.surface + 'D9', borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.xs },
  titleText: { color: colors.text, fontSize: 15, fontWeight: '700' },

  // Controls
  controls: { position: 'absolute', bottom: Platform.OS === 'ios' ? 50 : 30, left: spacing.lg, right: spacing.lg, gap: spacing.md },
  micBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.md, paddingHorizontal: spacing.lg, borderRadius: borderRadius.full, backgroundColor: colors.surface + 'E6', borderWidth: 1, borderColor: colors.border },
  micBtnActive: { borderColor: colors.accent, backgroundColor: colors.accent + '18' },
  micText: { color: colors.text, fontSize: 14, fontWeight: '600', flex: 1 },
  startBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, paddingVertical: spacing.md, borderRadius: borderRadius.full, backgroundColor: colors.primary },
  startBtnText: { color: colors.bg, fontSize: 16, fontWeight: '700' },

  // Speaking indicator
  speakingIndicator: { position: 'absolute', bottom: Platform.OS === 'ios' ? 120 : 100, left: 0, right: 0, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 },
  speakingBar: { width: 3, height: 16, borderRadius: 2, backgroundColor: colors.primary },

  // Doubts overlay
  doubtsOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.75)', zIndex: 200 },
  doubtsCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.xl, marginHorizontal: spacing.xl, alignItems: 'center', gap: spacing.md, borderWidth: 1, borderColor: colors.border, maxWidth: 340 },
  doubtsTitle: { color: colors.text, fontSize: 22, fontWeight: '800' },
  doubtsSub: { color: colors.textSecondary, fontSize: 14, textAlign: 'center' },
  doubtsActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.md, flexWrap: 'wrap', justifyContent: 'center' },
  doubtsMicBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  doubtsFinishBtn: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border },
  doubtsBtnText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
  doubtsFinishText: { color: colors.textSecondary, fontWeight: '600', fontSize: 15 },

  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.xl, width: '100%', maxWidth: 400, gap: spacing.lg, borderWidth: 1, borderColor: colors.border },
  modalTitle: { fontSize: 20, fontWeight: '700', color: colors.text, textAlign: 'center' },
  modalInput: { backgroundColor: colors.bg, borderRadius: borderRadius.md, padding: spacing.md, color: colors.text, fontSize: 16, minHeight: 100, textAlignVertical: 'top', borderWidth: 1, borderColor: colors.border },
  modalActions: { flexDirection: 'row', gap: spacing.md },
  modalCancelBtn: { flex: 1, alignItems: 'center', paddingVertical: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border },
  modalCancelText: { color: colors.textSecondary, fontWeight: '600', fontSize: 15 },
  modalSubmitBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, backgroundColor: colors.primary, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  modalSubmitText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
});
