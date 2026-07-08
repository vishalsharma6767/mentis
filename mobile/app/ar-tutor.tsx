import { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Image,
  TouchableOpacity,
  Dimensions,
  Platform,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../src/theme';
import { GlassCard, ParticleBackground } from '../src/components';
import { api } from '../src/lib/api';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

interface Step {
  number: number;
  instruction: string;
  explanation: string;
  hint: string;
  answer: string;
}

export default function ARTutorScreen() {
  const router = useRouter();
  const { imageUri, type, content, title } = useLocalSearchParams<{
    imageUri: string;
    type: string;
    content: string;
    title: string;
  }>();

  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showOverlay, setShowOverlay] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const lesson = await api.generateLesson(type ?? 'unknown', content ?? '');
        setSteps(lesson.steps);
      } catch {} finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const step = steps[currentStep];

  return (
    <View style={styles.container}>
      {/* Background image */}
      {imageUri && (
        <Image source={{ uri: imageUri }} style={styles.background} resizeMode="contain" />
      )}

      {/* Annotations overlay */}
      {showOverlay && step && (
        <View style={styles.overlay}>
          <GlassCard style={styles.annotationCard}>
            <View style={styles.stepBadge}>
              <Text style={styles.stepBadgeText}>Step {step.number}/{steps.length}</Text>
            </View>
            <Text style={styles.annotationTitle}>{step.instruction}</Text>
            <Text style={styles.annotationBody}>{step.explanation}</Text>
          </GlassCard>
        </View>
      )}

      {loading && (
        <View style={styles.loadingLayer}>
          <Text style={styles.loadingText}>Analyzing with AR...</Text>
        </View>
      )}

      {/* Controls */}
      <View style={styles.controls}>
        <TouchableOpacity
          style={styles.controlButton}
          onPress={() => setShowOverlay(!showOverlay)}
        >
          <Ionicons
            name={showOverlay ? 'eye-off-outline' : 'eye-outline'}
            size={22}
            color={colors.text}
          />
          <Text style={styles.controlLabel}>{showOverlay ? 'Hide' : 'Show'} AR</Text>
        </TouchableOpacity>

        <View style={styles.stepNav}>
          <TouchableOpacity
            style={styles.navButton}
            onPress={() => setCurrentStep(Math.max(0, currentStep - 1))}
            disabled={currentStep === 0}
          >
            <Ionicons name="chevron-back" size={24} color={currentStep === 0 ? colors.textTertiary : colors.text} />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.navButton}
            onPress={() => router.replace(`/tutor?type=${encodeURIComponent(type ?? '')}&content=${encodeURIComponent(content ?? '')}&title=${encodeURIComponent(title ?? '')}&imageUri=${encodeURIComponent(imageUri ?? '')}`)}
          >
            <Ionicons name="list-outline" size={22} color={colors.primary} />
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.navButton}
            onPress={() => setCurrentStep(Math.min(steps.length - 1, currentStep + 1))}
            disabled={currentStep === steps.length - 1}
          >
            <Ionicons name="chevron-forward" size={24} color={currentStep === steps.length - 1 ? colors.textTertiary : colors.text} />
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          style={[styles.controlButton, styles.voiceButton]}
          onPress={() => router.back()}
        >
          <Ionicons name="close" size={22} color={colors.accent} />
        </TouchableOpacity>
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
  overlay: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'flex-end',
    paddingHorizontal: spacing.lg,
    paddingBottom: 120,
  },
  annotationCard: {
    padding: spacing.lg,
    borderColor: colors.primary + '60',
    borderWidth: 1,
  },
  stepBadge: {
    backgroundColor: colors.primary + '20',
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: borderRadius.sm,
    alignSelf: 'flex-start',
    marginBottom: spacing.sm,
  },
  stepBadgeText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
  },
  annotationTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
    marginBottom: spacing.xs,
  },
  annotationBody: {
    fontSize: 14,
    color: colors.textSecondary,
    lineHeight: 20,
  },
  loadingLayer: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.7)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: {
    color: colors.primary,
    fontSize: 18,
    fontWeight: '600',
  },
  controls: {
    position: 'absolute',
    bottom: Platform.OS === 'ios' ? 50 : 30,
    left: spacing.lg,
    right: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  controlButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.surface + 'CC',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  controlLabel: {
    fontSize: 13,
    color: colors.text,
    fontWeight: '600',
  },
  voiceButton: {
    borderColor: colors.accent + '40',
  },
  stepNav: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface + 'CC',
    borderRadius: borderRadius.md,
    padding: 4,
    borderWidth: 1,
    borderColor: colors.border,
  },
  navButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: borderRadius.sm,
  },
});
