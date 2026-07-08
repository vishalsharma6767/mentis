import { useState } from 'react';
import { View, Text, StyleSheet, Image } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, spacing, borderRadius } from '../../src/theme';
import { AnimatedButton, ParticleBackground } from '../../src/components';

const slides = [
  {
    title: 'Point & Learn',
    subtitle: 'Scan a notebook, worksheet, diagram, textbook, or code error.',
  },
  {
    title: 'Live AR Teacher',
    subtitle: 'Mentis talks with you, writes on the page, and waits for your doubts.',
  },
  {
    title: 'Session PDF',
    subtitle: 'Download solved steps, AR pen notes, and the doubt transcript after class.',
  },
];

export default function OnboardingScreen() {
  const router = useRouter();
  const [currentSlide, setCurrentSlide] = useState(0);
  const slide = slides[currentSlide];

  function goNext() {
    if (currentSlide < slides.length - 1) {
      setCurrentSlide(currentSlide + 1);
    } else {
      setCurrentSlide(2);
    }
  }

  return (
    <View style={styles.container}>
      <ParticleBackground />
      <View style={styles.content}>
        <View style={styles.logoPanel}>
          <Image source={require('../../assets/logo.png')} style={styles.logo} resizeMode="contain" />
        </View>
        <Text style={styles.brand}>Mentis</Text>
        <Text style={styles.title}>{slide.title}</Text>
        <Text style={styles.subtitle}>{slide.subtitle}</Text>

        <View style={styles.dots}>
          {slides.map((_, i) => (
            <View key={i} style={[styles.dot, i === currentSlide && styles.dotActive]} />
          ))}
        </View>

        {currentSlide < slides.length - 1 ? (
          <AnimatedButton title="Next" onPress={goNext} style={styles.button} />
        ) : (
          <>
            <AnimatedButton title="Create Account" onPress={() => router.replace('/(auth)/register')} style={styles.button} />
            <AnimatedButton title="I already have an account" variant="ghost" onPress={() => router.replace('/(auth)/login')} style={styles.skipButton} />
          </>
        )}
        {currentSlide < slides.length - 1 && (
          <AnimatedButton title="Skip" variant="ghost" onPress={() => setCurrentSlide(2)} style={styles.skipButton} />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  logoPanel: {
    width: 136,
    height: 136,
    borderRadius: borderRadius.xl,
    backgroundColor: colors.bgSecondary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.lg,
  },
  logo: { width: 108, height: 108 },
  brand: {
    color: colors.primary,
    fontSize: 15,
    fontWeight: '900',
    letterSpacing: 0,
    textTransform: 'uppercase',
    marginBottom: spacing.sm,
  },
  title: {
    fontSize: 32,
    fontWeight: '800',
    color: colors.text,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  subtitle: {
    fontSize: 16,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 24,
    paddingHorizontal: spacing.md,
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
  button: { width: '100%' },
  skipButton: { marginTop: spacing.sm },
});
