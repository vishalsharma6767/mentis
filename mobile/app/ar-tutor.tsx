import { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Image,
  TouchableOpacity,
  Platform,
  ActivityIndicator,
  ViewStyle,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../src/theme';
import { GlassCard } from '../src/components';
import { api, LearningMode } from '../src/lib/api';

interface Step {
  number: number;
  instruction: string;
  explanation: string;
  hint: string;
  answer: string;
  ar_annotation?: string;
  focus?: string;
}

const targets: ViewStyle[] = [
  { left: '16%', top: '30%', width: '68%', height: 74 },
  { left: '22%', top: '44%', width: '56%', height: 68 },
  { left: '18%', top: '57%', width: '64%', height: 78 },
  { left: '24%', top: '68%', width: '52%', height: 64 },
];

export default function ARTutorScreen() {
  const router = useRouter();
  const { imageUri, type, mode, content, title, step: initialStep } = useLocalSearchParams<{
    imageUri: string;
    type: string;
    mode?: LearningMode;
    content: string;
    title: string;
    step?: string;
  }>();

  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStep, setCurrentStep] = useState(Number(initialStep ?? 0) || 0);
  const [loading, setLoading] = useState(true);
  const [showOverlay, setShowOverlay] = useState(true);
  const selectedMode = (mode ?? 'math') as LearningMode;

  useEffect(() => {
    async function load() {
      try {
        const lesson = await api.generateLesson(type ?? 'unknown', content ?? '', 'intermediate', selectedMode);
        setSteps(lesson.steps ?? []);
      } catch {
        setSteps([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const step = steps[currentStep];
  const target = targets[currentStep % targets.length];
  const canGoNext = steps.length > 0 && currentStep < steps.length - 1;

  return (
    <View style={styles.container}>
      {imageUri ? (
        <Image source={{ uri: imageUri }} style={styles.background} resizeMode="contain" />
      ) : (
        <View style={styles.emptyPage}>
          <Ionicons name="document-text-outline" size={56} color={colors.textTertiary} />
          <Text style={styles.emptyText}>{title ?? content ?? 'Scanned learning material'}</Text>
        </View>
      )}

      <View style={styles.scrim} />

      {showOverlay && step && (
        <View style={StyleSheet.absoluteFill}>
          <View style={[styles.targetBox, target]}>
            <View style={styles.targetGlow} />
          </View>

          <View style={[styles.callout, { top: target.top }]}>
            <View style={styles.pin} />
            <GlassCard style={styles.annotationCard}>
              <View style={styles.annotationTop}>
                <View style={styles.stepBadge}>
                  <Text style={styles.stepBadgeText}>Step {step.number}/{steps.length}</Text>
                </View>
                <Text style={styles.modeLabel}>{selectedMode}</Text>
              </View>
              <Text style={styles.annotationTitle}>
                {step.ar_annotation || step.instruction}
              </Text>
              <Text style={styles.annotationBody}>{step.explanation || step.hint}</Text>
              {!!step.focus && (
                <View style={styles.focusRow}>
                  <Ionicons name="locate-outline" size={15} color={colors.secondary} />
                  <Text style={styles.focusText}>{step.focus}</Text>
                </View>
              )}
            </GlassCard>
          </View>
        </View>
      )}

      {loading && (
        <View style={styles.loadingLayer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={styles.loadingText}>Anchoring tutor notes...</Text>
        </View>
      )}

      <View style={styles.topBar}>
        <TouchableOpacity style={styles.iconButton} onPress={() => router.back()}>
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <View style={styles.titleBlock}>
          <Text style={styles.titleText} numberOfLines={1}>{title ?? 'AR Tutor'}</Text>
          <Text style={styles.subtitleText}>Notebook overlay</Text>
        </View>
        <TouchableOpacity style={styles.iconButton} onPress={() => setShowOverlay(!showOverlay)}>
          <Ionicons name={showOverlay ? 'eye-outline' : 'eye-off-outline'} size={20} color={colors.primary} />
        </TouchableOpacity>
      </View>

      <View style={styles.controls}>
        <View style={styles.stepNav}>
          <TouchableOpacity
            style={styles.navButton}
            onPress={() => setCurrentStep(Math.max(0, currentStep - 1))}
            disabled={currentStep === 0}
          >
            <Ionicons name="chevron-back" size={24} color={currentStep === 0 ? colors.textTertiary : colors.text} />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.listButton}
            onPress={() => router.replace(`/tutor?type=${encodeURIComponent(type ?? '')}&mode=${encodeURIComponent(selectedMode)}&content=${encodeURIComponent(content ?? '')}&title=${encodeURIComponent(title ?? '')}&imageUri=${encodeURIComponent(imageUri ?? '')}`)}
          >
            <Ionicons name="list-outline" size={20} color={colors.bg} />
            <Text style={styles.listButtonText}>Lesson</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.navButton}
            onPress={() => setCurrentStep(Math.min(steps.length - 1, currentStep + 1))}
            disabled={!canGoNext}
          >
            <Ionicons name="chevron-forward" size={24} color={!canGoNext ? colors.textTertiary : colors.text} />
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  background: {
    ...StyleSheet.absoluteFill,
    width: '100%',
    height: '100%',
  },
  emptyPage: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
    backgroundColor: colors.bgSecondary,
  },
  emptyText: {
    color: colors.textSecondary,
    fontSize: 16,
    lineHeight: 24,
    marginTop: spacing.md,
    textAlign: 'center',
  },
  scrim: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.18)',
  },
  topBar: {
    position: 'absolute',
    top: Platform.OS === 'ios' ? 52 : 22,
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  iconButton: {
    width: 42,
    height: 42,
    borderRadius: borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface + 'E6',
    borderWidth: 1,
    borderColor: colors.border,
  },
  titleBlock: {
    flex: 1,
    minHeight: 42,
    justifyContent: 'center',
    backgroundColor: colors.surface + 'D9',
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
  },
  titleText: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  subtitleText: {
    color: colors.textTertiary,
    fontSize: 12,
    marginTop: 2,
  },
  targetBox: {
    position: 'absolute',
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: borderRadius.sm,
    backgroundColor: colors.primary + '12',
  },
  targetGlow: {
    ...StyleSheet.absoluteFill,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    borderColor: colors.text,
  },
  callout: {
    position: 'absolute',
    left: spacing.lg,
    right: spacing.lg,
    transform: [{ translateY: 92 }],
  },
  pin: {
    width: 2,
    height: 34,
    marginLeft: '50%',
    backgroundColor: colors.primary,
  },
  annotationCard: {
    padding: spacing.md,
    borderColor: colors.primary + '70',
    borderWidth: 1,
  },
  annotationTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  stepBadge: {
    backgroundColor: colors.primary + '20',
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: borderRadius.sm,
  },
  stepBadgeText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  modeLabel: {
    color: colors.textTertiary,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  annotationTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.xs,
  },
  annotationBody: {
    fontSize: 14,
    color: colors.textSecondary,
    lineHeight: 20,
  },
  focusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  focusText: {
    color: colors.secondary,
    fontSize: 13,
    fontWeight: '700',
  },
  loadingLayer: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.68)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
  },
  loadingText: {
    color: colors.primary,
    fontSize: 17,
    fontWeight: '700',
  },
  controls: {
    position: 'absolute',
    bottom: Platform.OS === 'ios' ? 46 : 26,
    left: spacing.lg,
    right: spacing.lg,
    alignItems: 'center',
  },
  stepNav: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface + 'E6',
    borderRadius: borderRadius.md,
    padding: 6,
    borderWidth: 1,
    borderColor: colors.border,
  },
  navButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: borderRadius.sm,
  },
  listButton: {
    height: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.sm,
    backgroundColor: colors.primary,
  },
  listButtonText: {
    color: colors.bg,
    fontSize: 14,
    fontWeight: '700',
  },
});
