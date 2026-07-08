import { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withSequence,
} from 'react-native-reanimated';
import { colors, spacing, typography, borderRadius } from '../src/theme';
import { GlassCard, ParticleBackground } from '../src/components';
import { api } from '../src/lib/api';
import { useVoice } from '../src/lib/voice';

interface Step {
  number: number;
  instruction: string;
  explanation: string;
  hint: string;
  answer: string;
}

export default function TutorScreen() {
  const router = useRouter();
  const { type, content, title, imageUri } = useLocalSearchParams<{
    type: string;
    content: string;
    title: string;
    imageUri?: string;
  }>();

  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Step[]>([]);
  const [loading, setLoading] = useState(true);
  const [showHint, setShowHint] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);
  const [userInput, setUserInput] = useState('');
  const [helpText, setHelpText] = useState('');
  const [showHelp, setShowHelp] = useState(false);
  const [askingHelp, setAskingHelp] = useState(false);
  const [transcribingVoice, setTranscribingVoice] = useState(false);

  const voice = useVoice();
  const stepScale = useSharedValue(1);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const lesson = await api.generateLesson(type ?? 'unknown', content ?? '');
        setSteps(lesson.steps);
      } catch (e) {
        console.error('Failed to load lesson:', e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function animateStep() {
    stepScale.value = withSequence(
      withSpring(1.05),
      withSpring(1),
    );
  }

  function handleNext() {
    setShowHint(false);
    setShowAnswer(false);
    setUserInput('');
    setHelpText('');
    setShowHelp(false);
    completedSteps.push(steps[currentStep]);
    setCompletedSteps([...completedSteps]);

    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
      animateStep();
    }
  }

  async function handleVoiceInput() {
    try {
      if (voice.isRecording) {
        const uri = await voice.stopRecording();
        if (uri) {
          setTranscribingVoice(true);
          const text = await voice.transcribeAudio(uri);
          if (text) setUserInput(text);
          setTranscribingVoice(false);
        }
      } else {
        await voice.startRecording();
      }
    } catch {
      setTranscribingVoice(false);
    }
  }

  function handleReadAloud() {
    if (voice.isSpeaking) {
      voice.stopSpeaking();
    } else if (step) {
      voice.speakText(`${step.instruction}. ${step.explanation}`);
    }
  }

  async function handleAskHelp() {
    setAskingHelp(true);
    try {
      const result = await api.getStepHelp(
        type ?? 'unknown',
        content ?? '',
        completedSteps,
        steps[currentStep],
      );
      setHelpText(result.help);
      setShowHelp(true);
    } catch (e) {
      setHelpText('Try breaking the problem into smaller parts.');
      setShowHelp(true);
    } finally {
      setAskingHelp(false);
    }
  }

  const stepAnimStyle = useAnimatedStyle(() => ({
    transform: [{ scale: stepScale.value }],
  }));

  if (loading) {
    return (
      <View style={styles.container}>
        <ParticleBackground />
        <View style={styles.center}>
          <Text style={styles.loadingTitle}>Generating lesson...</Text>
          <Text style={styles.loadingSub}>Mentis is preparing your step-by-step guide</Text>
        </View>
      </View>
    );
  }

  const step = steps[currentStep];

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ParticleBackground />

      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Ionicons name="close" size={24} color={colors.text} />
        </TouchableOpacity>
        <View style={styles.progressContainer}>
          <View
            style={[
              styles.progressBar,
              { width: `${((completedSteps.length + (showAnswer ? 1 : 0)) / steps.length) * 100}%` },
            ]}
          />
        </View>
        <Text style={styles.progressText}>
          {completedSteps.length}/{steps.length}
        </Text>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <GlassCard style={styles.problemCard}>
          <Text style={styles.problemLabel}>Problem</Text>
          <Text style={styles.problemText}>{title ?? content}</Text>
        </GlassCard>

        <Animated.View style={[styles.stepCard, stepAnimStyle]}>
          <View style={styles.stepHeader}>
            <View style={styles.stepBadge}>
              <Text style={styles.stepBadgeText}>Step {step?.number}</Text>
            </View>
          </View>

          <Text style={styles.stepInstruction}>{step?.instruction}</Text>

          {step?.explanation && (
            <Text style={styles.stepExplanation}>{step?.explanation}</Text>
          )}

          <View style={styles.inputArea}>
            <View style={styles.inputRow}>
              <TextInput
                style={styles.inputField}
                placeholder="Your answer..."
                placeholderTextColor={colors.textTertiary}
                value={userInput}
                onChangeText={setUserInput}
                multiline
              />
              <TouchableOpacity
                style={[styles.voiceButton, voice.isRecording && styles.voiceButtonActive]}
                onPress={handleVoiceInput}
                disabled={transcribingVoice}
              >
                {transcribingVoice ? (
                  <ActivityIndicator size="small" color={colors.primary} />
                ) : (
                  <Ionicons
                    name={voice.isRecording ? 'mic' : 'mic-outline'}
                    size={20}
                    color={voice.isRecording ? colors.accent : colors.textSecondary}
                  />
                )}
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.actions}>
            <TouchableOpacity
              style={styles.actionButton}
              onPress={() => setShowHint(!showHint)}
            >
              <Ionicons name="bulb-outline" size={18} color={colors.warning} />
              <Text style={[styles.actionText, { color: colors.warning }]}>
                {showHint ? 'Hide Hint' : 'Hint'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionButton}
              onPress={handleAskHelp}
              disabled={askingHelp}
            >
              <Ionicons
                name="chatbubble-ellipses-outline"
                size={18}
                color={colors.primary}
              />
              <Text style={[styles.actionText, { color: colors.primary }]}>
                {askingHelp ? '...' : 'Help'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionButton}
              onPress={handleReadAloud}
            >
              <Ionicons
                name={voice.isSpeaking ? 'volume-high' : 'volume-medium-outline'}
                size={18}
                color={colors.secondary}
              />
              <Text style={[styles.actionText, { color: colors.secondary }]}>
                {voice.isSpeaking ? 'Stop' : 'Read'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.actionButton}
              onPress={() => setShowAnswer(!showAnswer)}
            >
              <Ionicons
                name="eye-outline"
                size={18}
                color={colors.accent}
              />
              <Text style={[styles.actionText, { color: colors.accent }]}>
                {showAnswer ? 'Hide Answer' : 'Answer'}
              </Text>
            </TouchableOpacity>
          </View>

          {showHint && step?.hint && (
            <GlassCard style={styles.hintCard}>
              <Text style={styles.hintText}>{step.hint}</Text>
            </GlassCard>
          )}

          {showHelp && helpText && (
            <GlassCard style={styles.helpCard}>
              <Text style={styles.helpText}>{helpText}</Text>
            </GlassCard>
          )}

          {showAnswer && step?.answer && (
            <GlassCard style={styles.answerCard}>
              <Text style={styles.answerLabel}>Answer</Text>
              <Text style={styles.answerText}>{step.answer}</Text>
            </GlassCard>
          )}
        </Animated.View>
      </ScrollView>

      <View style={styles.footer}>
        <View style={styles.footerRow}>
          <TouchableOpacity
            style={[styles.arButton]}
            onPress={() => router.push(`/ar-tutor?imageUri=${encodeURIComponent(imageUri ?? '')}&type=${encodeURIComponent(type ?? '')}&content=${encodeURIComponent(content ?? '')}&title=${encodeURIComponent(title ?? '')}`)}
          >
            <Ionicons name="scan-outline" size={18} color={colors.primary} />
            <Text style={styles.arButtonText}>AR View</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.nextButton}
            onPress={handleNext}
          >
            <Text style={styles.nextButtonText}>
              {currentStep < steps.length - 1
                ? 'Next Step'
                : 'Complete Lesson'}
            </Text>
            <Ionicons name="arrow-forward" size={20} color={colors.bg} />
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
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
  },
  loadingTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
  },
  loadingSub: {
    fontSize: 16,
    color: colors.textSecondary,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    paddingTop: Platform.OS === 'ios' ? 60 : 20,
  },
  progressContainer: {
    flex: 1,
    height: 6,
    backgroundColor: colors.surface,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressBar: {
    height: '100%',
    backgroundColor: colors.primary,
    borderRadius: 3,
  },
  progressText: {
    color: colors.textSecondary,
    fontSize: 14,
    fontWeight: '600',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: spacing.lg,
    paddingBottom: 100,
    gap: spacing.md,
  },
  problemCard: {
    padding: spacing.md,
  },
  problemLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing.xs,
  },
  problemText: {
    fontSize: 16,
    color: colors.text,
    lineHeight: 24,
  },
  stepCard: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  stepHeader: {
    marginBottom: spacing.md,
  },
  stepBadge: {
    backgroundColor: colors.primary + '20',
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: borderRadius.sm,
    alignSelf: 'flex-start',
  },
  stepBadgeText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  stepInstruction: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
    marginBottom: spacing.sm,
    lineHeight: 26,
  },
  stepExplanation: {
    fontSize: 15,
    color: colors.textSecondary,
    lineHeight: 22,
    marginBottom: spacing.md,
  },
  inputArea: {
    marginBottom: spacing.md,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
  },
  inputField: {
    flex: 1,
    backgroundColor: colors.bgSecondary,
    borderRadius: borderRadius.md,
    padding: spacing.md,
    fontSize: 16,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 50,
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.sm,
    backgroundColor: colors.bgSecondary,
  },
  actionText: {
    fontSize: 13,
    fontWeight: '600',
  },
  hintCard: {
    marginTop: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.warning + '10',
    borderColor: colors.warning + '30',
  },
  hintText: {
    color: colors.warning,
    fontSize: 14,
    lineHeight: 20,
  },
  helpCard: {
    marginTop: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.primary + '10',
    borderColor: colors.primary + '30',
  },
  helpText: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 20,
  },
  answerCard: {
    marginTop: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.accent + '10',
    borderColor: colors.accent + '30',
  },
  answerLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.accent,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: spacing.xs,
  },
  answerText: {
    color: colors.text,
    fontSize: 16,
    lineHeight: 22,
  },
  footer: {
    padding: spacing.lg,
    paddingBottom: Platform.OS === 'ios' ? 40 : spacing.lg,
    gap: spacing.sm,
  },
  footerRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  nextButton: {
    flex: 1,
    backgroundColor: colors.primary,
    borderRadius: borderRadius.md,
    paddingVertical: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  nextButtonText: {
    color: colors.bg,
    fontSize: 16,
    fontWeight: '700',
  },
  arButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 16,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.primary + '40',
  },
  arButtonText: {
    color: colors.primary,
    fontSize: 13,
    fontWeight: '600',
  },
  voiceButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.bgSecondary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  voiceButtonActive: {
    backgroundColor: colors.accent + '20',
    borderColor: colors.accent,
  },
});
