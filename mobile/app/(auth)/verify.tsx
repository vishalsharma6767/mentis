import { useState } from 'react';
import { Image, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing } from '../../src/theme';
import { OTPInput, ParticleBackground } from '../../src/components';
import { sendOTP, verifyOTP } from '../../src/lib/auth';

export default function VerifyScreen() {
  const router = useRouter();
  const { userId, email } = useLocalSearchParams<{ userId: string; email: string }>();
  const [error, setError] = useState(false);

  async function handleVerify(code: string) {
    if (!userId) return;
    setError(false);
    try {
      await verifyOTP(userId, code);
      router.replace('/(tabs)');
    } catch {
      setError(true);
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
      <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
        <Ionicons name="chevron-back" size={22} color={colors.primary} />
        <Text style={styles.backText}>Change email</Text>
      </TouchableOpacity>

      <View style={styles.content}>
        <Image source={require('../../assets/logo.png')} style={styles.logo} resizeMode="contain" />
        <Text style={styles.title}>Verify your email</Text>
        <Text style={styles.subtitle}>
          Enter the 6-digit code sent to <Text style={styles.email}>{email ?? 'your email'}</Text>.
        </Text>

        <View style={styles.otpContainer}>
          <OTPInput onComplete={handleVerify} onResend={handleResend} error={error} />
        </View>

        {error && <Text style={styles.error}>Invalid code. Try again or request a new one.</Text>}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  backButton: {
    position: 'absolute',
    top: Platform.OS === 'ios' ? 58 : 22,
    left: spacing.md,
    zIndex: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    padding: spacing.sm,
  },
  backText: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  logo: { width: 88, height: 88, marginBottom: spacing.lg },
  title: {
    fontSize: 32,
    fontWeight: '800',
    color: colors.text,
    marginBottom: spacing.sm,
  },
  subtitle: {
    fontSize: 16,
    color: colors.textSecondary,
    lineHeight: 24,
    marginBottom: spacing.xl,
  },
  email: { color: colors.primary, fontWeight: '700' },
  otpContainer: { marginTop: spacing.lg },
  error: {
    color: colors.error,
    fontSize: 14,
    textAlign: 'center',
    marginTop: spacing.md,
  },
});
