import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../src/theme';
import { GlassCard, ParticleBackground } from '../src/components';
import { api, LearnerLevel, LearningMode } from '../src/lib/api';
import { useVoice } from '../src/lib/voice';
import { restoreSession } from '../src/lib/auth';

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

const penPositions = [
  { x: 14, y: 25 },
  { x: 22, y: 38 },
  { x: 16, y: 52 },
  { x: 28, y: 64 },
  { x: 18, y: 73 },
];

function downloadBase64Pdf(filename: string, base64: string) {
  if (Platform.OS === 'web') {
    const link = document.createElement('a');
    link.href = `data:application/pdf;base64,${base64}`;
    link.download = filename;
    link.click();
  }
}

export default function LiveSessionScreen() {
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
  const [level, setLevel] = useState<LearnerLevel>('intermediate');
  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [speaking, setSpeaking] = useState(false);
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [penNotes, setPenNotes] = useState<PenNote[]>([]);
  const voice = useVoice();

  const step = steps[currentStep];
  const progress = steps.length ? Math.round(((currentStep + 1) / steps.length) * 100) : 0;

  useEffect(() => {
    async function loadLesson() {
      setLoading(true);
      try {
        const lesson = await api.generateLesson(type ?? selectedMode, content ?? '', level, selectedMode);
        const lessonSteps = lesson.steps ?? [];
        setSteps(lessonSteps);
        setCurrentStep(0);
        const first = lessonSteps[0];
        if (first) {
          setMessages([
            {
              role: 'teacher',
              text: `Let's solve this together. ${first.instruction}`,
            },
          ]);
          setPenNotes([
            {
              text: first.ar_annotation || first.instruction,
              ...penPositions[0],
              color: colors.primary,
            },
          ]);
        }
      } catch {
        setMessages([{ role: 'teacher', text: 'I am ready. Ask your doubt and we will solve it step by step.' }]);
      } finally {
        setLoading(false);
      }
    }
    loadLesson();
  }, [level]);

  const teacherScript = useMemo(() => {
    if (!step) return 'Ask me your doubt and I will guide you.';
    return `${step.instruction}. ${step.explanation || step.hint}`;
  }, [step]);

  async function speakCurrentStep() {
    if (voice.isSpeaking || speaking) {
      voice.stopSpeaking();
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    await voice.speakText(teacherScript);
    setSpeaking(false);
  }

  function writeCurrentStep() {
    if (!step) return;
    const pos = penPositions[currentStep % penPositions.length];
    setPenNotes((notes) => [
      ...notes,
      {
        text: step.ar_annotation || step.instruction,
        x: pos.x,
        y: pos.y,
        color: currentStep % 2 === 0 ? colors.primary : colors.warning,
      },
    ]);
  }

  function goNextStep() {
    if (!steps.length) return;
    const next = Math.min(steps.length - 1, currentStep + 1);
    setCurrentStep(next);
    const nextStep = steps[next];
    if (nextStep) {
      setMessages((items) => [...items, { role: 'teacher', text: nextStep.instruction }]);
      const pos = penPositions[next % penPositions.length];
      setPenNotes((notes) => [
        ...notes,
        {
          text: nextStep.ar_annotation || nextStep.instruction,
          x: pos.x,
          y: pos.y,
          color: colors.primary,
        },
      ]);
    }
  }

  async function askDoubt() {
    const trimmed = question.trim();
    if (!trimmed || asking) return;
    setAsking(true);
    setQuestion('');
    setMessages((items) => [...items, { role: 'student', text: trimmed }]);
    try {
      const answer = await api.askDoubt({
        content: content ?? '',
        question: trimmed,
        current: step,
        level,
        mode: selectedMode,
      });
      setMessages((items) => [
        ...items,
        { role: 'teacher', text: `${answer.reply} ${answer.follow_up}`.trim() },
      ]);
      const pos = penPositions[(penNotes.length + 1) % penPositions.length];
      setPenNotes((notes) => [
        ...notes,
        {
          text: answer.pen_annotation || 'Check this idea',
          x: pos.x,
          y: pos.y,
          color: colors.accent,
        },
      ]);
      voice.speakText(answer.reply);
    } catch {
      setMessages((items) => [...items, { role: 'teacher', text: 'You are close. Tell me which exact line feels confusing.' }]);
    } finally {
      setAsking(false);
    }
  }

  async function recordDoubt() {
    try {
      if (voice.isRecording) {
        const uri = await voice.stopRecording();
        if (uri) {
          const text = await voice.transcribeAudio(uri);
          if (text) setQuestion(text);
        }
      } else {
        await voice.startRecording();
      }
    } catch {}
  }

  async function downloadPdf() {
    setDownloading(true);
    try {
      const result = await api.createSessionPdf({
        title: title ?? 'Mentis live tutor session',
        problem: content ?? '',
        steps,
        transcript: messages,
        penNotes,
      });
      if (Platform.OS === 'web') {
        downloadBase64Pdf(result.filename, result.base64);
      } else {
        const FileSystem: any = await import('expo-file-system');
        const path = `${FileSystem.documentDirectory}${result.filename}`;
        await FileSystem.writeAsStringAsync(path, result.base64, {
          encoding: FileSystem.EncodingType.Base64,
        });
        Alert.alert('PDF saved', path);
      }
    } finally {
      setDownloading(false);
    }
  }

  async function finishSession() {
    try {
      const session = await restoreSession();
      if (session) {
        await api.saveSession({
          userId: session.userId,
          problemTitle: title ?? 'Live tutor session',
          problemType: selectedMode,
          extractedText: content ?? '',
          status: 'completed',
          steps: JSON.stringify(steps),
        });
      }
    } catch {}
    await downloadPdf();
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ParticleBackground />

      <View style={styles.header}>
        <TouchableOpacity style={styles.iconButton} onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <View style={styles.headerText}>
          <Text style={styles.title} numberOfLines={1}>{title ?? 'Live AR Tutor'}</Text>
          <Text style={styles.subtitle}>{selectedMode} session{difficulty ? ` - ${difficulty}` : ''}</Text>
        </View>
        <TouchableOpacity style={styles.pdfButton} onPress={downloadPdf} disabled={downloading}>
          {downloading ? (
            <ActivityIndicator size="small" color={colors.bg} />
          ) : (
            <Ionicons name="download-outline" size={18} color={colors.bg} />
          )}
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.levelRow}>
          {(['beginner', 'intermediate', 'advanced'] as LearnerLevel[]).map((item) => (
            <TouchableOpacity
              key={item}
              style={[styles.levelButton, level === item && styles.levelButtonActive]}
              onPress={() => setLevel(item)}
            >
              <Text style={[styles.levelText, level === item && styles.levelTextActive]}>{item}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.stage}>
          {imageUri ? (
            <Image source={{ uri: imageUri }} resizeMode="contain" style={styles.stageImage} />
          ) : (
            <View style={styles.blankPage}>
              <Text style={styles.problemText}>{content}</Text>
            </View>
          )}

          <View style={styles.scanFrame} pointerEvents="none" />
          {penNotes.map((note, index) => (
            <View
              key={`${note.text}-${index}`}
              style={[
                styles.penNote,
                {
                  left: `${note.x}%`,
                  top: `${note.y}%`,
                  borderColor: note.color,
                  backgroundColor: note.color + '18',
                },
              ]}
            >
              <View style={[styles.penDot, { backgroundColor: note.color }]} />
              <Text style={[styles.penText, { color: note.color }]}>{note.text}</Text>
            </View>
          ))}
        </View>

        <GlassCard style={styles.teacherCard}>
          {loading ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={colors.primary} />
              <Text style={styles.teacherText}>Preparing a real-time teaching plan...</Text>
            </View>
          ) : (
            <>
              <View style={styles.teacherTop}>
                <View style={styles.liveBadge}>
                  <View style={styles.liveDot} />
                  <Text style={styles.liveText}>Live teacher</Text>
                </View>
                <Text style={styles.progressText}>{progress}%</Text>
              </View>
              <Text style={styles.stepTitle}>{step?.instruction ?? 'Ask your doubt'}</Text>
              <Text style={styles.teacherText}>{step?.explanation || step?.hint || 'I will guide you without just revealing the answer.'}</Text>
              {!!step?.hint && <Text style={styles.hintText}>Hint: {step.hint}</Text>}
            </>
          )}
        </GlassCard>

        <View style={styles.controlGrid}>
          <TouchableOpacity style={styles.controlButton} onPress={speakCurrentStep}>
            <Ionicons name={voice.isSpeaking ? 'volume-high' : 'volume-medium-outline'} size={18} color={colors.secondary} />
            <Text style={styles.controlText}>{voice.isSpeaking ? 'Stop' : 'Talk'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.controlButton} onPress={writeCurrentStep}>
            <Ionicons name="create-outline" size={18} color={colors.warning} />
            <Text style={styles.controlText}>AR Pen</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.controlButton} onPress={goNextStep} disabled={currentStep >= steps.length - 1}>
            <Ionicons name="play-forward-outline" size={18} color={colors.primary} />
            <Text style={styles.controlText}>Next</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.controlButton} onPress={finishSession}>
            <Ionicons name="checkmark-circle-outline" size={18} color={colors.success} />
            <Text style={styles.controlText}>Finish</Text>
          </TouchableOpacity>
        </View>

        <GlassCard style={styles.chatCard}>
          <Text style={styles.chatTitle}>Doubt conversation</Text>
          <View style={styles.messages}>
            {messages.slice(-6).map((message, index) => (
              <View
                key={`${message.role}-${index}`}
                style={[
                  styles.messageBubble,
                  message.role === 'student' ? styles.studentBubble : styles.teacherBubble,
                ]}
              >
                <Text style={styles.messageRole}>{message.role === 'student' ? 'You' : 'Mentis'}</Text>
                <Text style={styles.messageText}>{message.text}</Text>
              </View>
            ))}
          </View>
          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              placeholder="Ask: why did we do this step?"
              placeholderTextColor={colors.textTertiary}
              value={question}
              onChangeText={setQuestion}
              multiline
            />
            <TouchableOpacity style={[styles.micButton, voice.isRecording && styles.micActive]} onPress={recordDoubt}>
              <Ionicons name={voice.isRecording ? 'mic' : 'mic-outline'} size={19} color={voice.isRecording ? colors.accent : colors.text} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.sendButton} onPress={askDoubt} disabled={asking}>
              {asking ? (
                <ActivityIndicator size="small" color={colors.bg} />
              ) : (
                <Ionicons name="send" size={18} color={colors.bg} />
              )}
            </TouchableOpacity>
          </View>
        </GlassCard>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: Platform.OS === 'ios' ? 58 : 24,
    paddingBottom: spacing.md,
  },
  iconButton: {
    width: 42,
    height: 42,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  headerText: { flex: 1 },
  title: { color: colors.text, fontSize: 18, fontWeight: '800' },
  subtitle: { color: colors.textSecondary, fontSize: 12, marginTop: 2, textTransform: 'capitalize' },
  pdfButton: {
    width: 42,
    height: 42,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
  },
  content: { padding: spacing.lg, paddingBottom: 120, gap: spacing.md },
  levelRow: { flexDirection: 'row', gap: spacing.sm },
  levelButton: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgSecondary,
  },
  levelButtonActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  levelText: { color: colors.textSecondary, fontSize: 12, fontWeight: '800', textTransform: 'capitalize' },
  levelTextActive: { color: colors.bg },
  stage: {
    height: 430,
    borderRadius: borderRadius.lg,
    overflow: 'hidden',
    backgroundColor: '#F4F1EA',
    borderWidth: 1,
    borderColor: colors.border,
  },
  stageImage: { width: '100%', height: '100%' },
  blankPage: { flex: 1, justifyContent: 'center', padding: spacing.xl },
  problemText: { color: '#111827', fontSize: 19, lineHeight: 28, fontWeight: '700' },
  scanFrame: {
    ...StyleSheet.absoluteFill,
    borderWidth: 2,
    borderColor: colors.primary + '80',
    margin: spacing.md,
    borderRadius: borderRadius.md,
  },
  penNote: {
    position: 'absolute',
    maxWidth: '62%',
    borderWidth: 1.5,
    borderRadius: borderRadius.sm,
    paddingVertical: 6,
    paddingHorizontal: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  penDot: { width: 8, height: 8, borderRadius: 4 },
  penText: { fontSize: 13, fontWeight: '900' },
  teacherCard: { padding: spacing.md },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  teacherTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm },
  liveBadge: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },
  liveText: { color: colors.success, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' },
  progressText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  stepTitle: { color: colors.text, fontSize: 20, fontWeight: '800', marginBottom: spacing.xs },
  teacherText: { color: colors.textSecondary, fontSize: 15, lineHeight: 22 },
  hintText: { color: colors.warning, fontSize: 14, lineHeight: 20, marginTop: spacing.sm, fontWeight: '700' },
  controlGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  controlButton: {
    width: '48%',
    minHeight: 46,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    borderRadius: borderRadius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  controlText: { color: colors.text, fontSize: 14, fontWeight: '800' },
  chatCard: { padding: spacing.md },
  chatTitle: { color: colors.text, fontSize: 16, fontWeight: '800', marginBottom: spacing.sm },
  messages: { gap: spacing.sm, marginBottom: spacing.md },
  messageBubble: { padding: spacing.sm, borderRadius: borderRadius.sm, borderWidth: 1 },
  teacherBubble: { backgroundColor: colors.primary + '10', borderColor: colors.primary + '25' },
  studentBubble: { backgroundColor: colors.accent + '10', borderColor: colors.accent + '25' },
  messageRole: { color: colors.textTertiary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 2 },
  messageText: { color: colors.text, fontSize: 14, lineHeight: 20 },
  inputRow: { flexDirection: 'row', alignItems: 'flex-end', gap: spacing.sm },
  input: {
    flex: 1,
    minHeight: 48,
    maxHeight: 96,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgSecondary,
    color: colors.text,
    padding: spacing.md,
    fontSize: 15,
  },
  micButton: {
    width: 46,
    height: 46,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  micActive: { borderColor: colors.accent, backgroundColor: colors.accent + '18' },
  sendButton: {
    width: 46,
    height: 46,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
  },
});
