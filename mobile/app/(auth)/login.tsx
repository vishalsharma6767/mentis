import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { colors, spacing, typography, borderRadius } from '../../src/theme';
import { AnimatedButton, ParticleBackground } from '../../src/components';
import { sendOTP } from '../../src/lib/auth';

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSendCode() {
    if (!email.trim()) {
      setError('Enter your email address');
      return;
    }
    if (!email.includes('@')) {
      setError('Enter a valid email');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const userId = await sendOTP(email.trim().toLowerCase());
      router.push(`/(auth)/verify?userId=${userId}&email=${encodeURIComponent(email.trim())}`);
    } catch (e: any) {
      setError(e?.message ?? 'Failed to send code. Try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ParticleBackground />
      <TouchableOpacity
        style={styles.backButton}
        onPress={() => router.back()}
      >
        <Text style={styles.backText}>← Back</Text>
      </TouchableOpacity>

      <View style={styles.content}>
        <Text style={styles.title}>Welcome to Mentis</Text>
        <Text style={styles.subtitle}>
          Enter your email to receive a verification code
        </Text>

        <View style={styles.inputContainer}>
          <TextInput
            style={styles.input}
            placeholder="you@email.com"
            placeholderTextColor={colors.textTertiary}
            value={email}
            onChangeText={(t) => { setEmail(t); setError(''); }}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            editable={!loading}
          />
        </View>

        {!!error && <Text style={styles.error}>{error}</Text>}

        <AnimatedButton
          title="Send Code"
          onPress={handleSendCode}
          loading={loading}
          disabled={loading}
          style={styles.button}
        />
      </View>
    </KeyboardAvoidingView>
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
  inputContainer: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    height: 56,
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  input: {
    fontSize: 16,
    color: colors.text,
  },
  error: {
    color: colors.error,
    fontSize: 14,
    marginBottom: spacing.md,
  },
  button: {
    marginTop: spacing.sm,
  },
});
