import { useState } from 'react';
import { View, Text, StyleSheet, Platform, TouchableOpacity } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { colors, spacing, typography } from '../../src/theme';
import { OTPInput, ParticleBackground } from '../../src/components';
import { verifyOTP, sendOTP } from '../../src/lib/auth';

export default function VerifyScreen() {
  const router = useRouter();
  const { userId, email } = useLocalSearchParams<{ userId: string; email: string }>();
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleVerify(code: string) {
    if (!userId) return;
    setLoading(true);
    setError(false);

    try {
      await verifyOTP(userId, code);
      router.replace('/(tabs)');
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (!email) return;
    setError(false);
    try {
      const newUserId = await sendOTP(email);
      router.replace(`/(auth)/verify?userId=${newUserId}&email=${encodeURIComponent(email)}`);
    } catch {
      setError(true);
    }
  }

  return (
    <View style={styles.container}>
      <ParticleBackground />
      <TouchableOpacity
        style={styles.backButton}
        onPress={() => router.back()}
      >
        <Text style={styles.backText}>← Change Email</Text>
      </TouchableOpacity>

      <View style={styles.content}>
        <Text style={styles.title}>Check Your Email</Text>
        <Text style={styles.subtitle}>
          We sent a 6-digit code to{' '}
          <Text style={styles.email}>{email ?? 'your email'}</Text>
        </Text>

        <View style={styles.otpContainer}>
          <OTPInput
            onComplete={handleVerify}
            onResend={handleResend}
            error={error}
          />
        </View>

        {error && (
          <Text style={styles.error}>
            Invalid code. Try again or request a new one.
          </Text>
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
  backButton: {
    padding: spacing.lg,
    position: 'absolute',
    top: Platform.OS === 'ios' ? 60 : 20,
    left: 0,
    zIndex: 10,
  },
  backText: {
    color: colors.primary,
    fontSize: 16,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
  },
  subtitle: {
    fontSize: 16,
    color: colors.textSecondary,
    lineHeight: 24,
    marginBottom: spacing.xl,
  },
  email: {
    color: colors.primary,
    fontWeight: '600',
  },
  otpContainer: {
    marginTop: spacing.lg,
  },
  error: {
    color: colors.error,
    fontSize: 14,
    textAlign: 'center',
    marginTop: spacing.md,
  },
});
