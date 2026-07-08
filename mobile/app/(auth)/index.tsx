import { useState, useRef } from 'react';
import { View, Text, StyleSheet, Dimensions } from 'react-native';
import { useRouter } from 'expo-router';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withSequence,
  runOnJS,
} from 'react-native-reanimated';
import { colors, spacing, typography, borderRadius } from '../../src/theme';
import { AnimatedButton, ParticleBackground } from '../../src/components';

const { width } = Dimensions.get('window');

const slides = [
  {
    title: 'Point & Learn',
    subtitle: 'Point your camera at any problem. Mentis recognizes it instantly.',
    emoji: '📷',
  },
  {
    title: 'Step by Step',
    subtitle: 'An AI teacher guides you through every step. Never get stuck again.',
    emoji: '🧠',
  },
  {
    title: 'Your Pace',
    subtitle: 'Personalized tutoring that adapts to your level and learning style.',
    emoji: '🎯',
  },
];

export default function OnboardingScreen() {
  const router = useRouter();
  const [currentSlide, setCurrentSlide] = useState(0);
  const slideProgress = useSharedValue(0);

  function goNext() {
    if (currentSlide < slides.length - 1) {
      slideProgress.value = withSequence(
        withTiming(0, { duration: 150 }),
        withTiming(1, { duration: 400 }),
      );
      runOnJS(setCurrentSlide)(currentSlide + 1);
    } else {
      router.replace('/(auth)/login');
    }
  }

  function skip() {
    router.replace('/(auth)/login');
  }

  const slide = slides[currentSlide];

  return (
    <View style={styles.container}>
      <ParticleBackground />
      <View style={styles.content}>
        <View style={styles.emojiContainer}>
          <Text style={styles.emoji}>{slide.emoji}</Text>
        </View>
        <Text style={styles.title}>{slide.title}</Text>
        <Text style={styles.subtitle}>{slide.subtitle}</Text>

        <View style={styles.dots}>
          {slides.map((_, i) => (
            <View
              key={i}
              style={[
                styles.dot,
                i === currentSlide && styles.dotActive,
              ]}
            />
          ))}
        </View>

        <AnimatedButton
          title={currentSlide < slides.length - 1 ? 'Next' : 'Get Started'}
          onPress={goNext}
          style={styles.button}
        />
        {currentSlide < slides.length - 1 && (
          <AnimatedButton
            title="Skip"
            variant="ghost"
            onPress={skip}
            style={styles.skipButton}
          />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  emojiContainer: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emoji: {
    fontSize: 56,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.text,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  subtitle: {
    fontSize: 16,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 24,
    paddingHorizontal: spacing.lg,
  },
  dots: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.xxl,
    marginBottom: spacing.xl,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.border,
  },
  dotActive: {
    width: 24,
    backgroundColor: colors.primary,
  },
  button: {
    width: '100%',
  },
  skipButton: {
    marginTop: spacing.sm,
  },
});
