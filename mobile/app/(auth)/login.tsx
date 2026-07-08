import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { AnimatedButton, ParticleBackground } from '../../src/components';
import { sendOTP } from '../../src/lib/auth';

export default function LoginScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSendCode() {
    const normalized = email.trim().toLowerCase();
    if (!normalized || !normalized.includes('@')) {
      setError('Enter a valid email address.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const userId = await sendOTP(normalized);
      router.push(`/(auth)/verify?userId=${userId}&email=${encodeURIComponent(normalized)}`);
    } catch (e: any) {
      setError(e?.message ?? 'Could not send the code. Please try again.');
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
      <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
        <Ionicons name="chevron-back" size={22} color={colors.primary} />
        <Text style={styles.backText}>Back</Text>
      </TouchableOpacity>

      <View style={styles.content}>
        <Image source={require('../../assets/logo.png')} style={styles.logo} resizeMode="contain" />
        <Text style={styles.title}>Sign in to Mentis</Text>
        <Text style={styles.subtitle}>
          Start live AR tutoring, save progress, and download session PDFs.
        </Text>

        <View style={[styles.inputContainer, !!error && styles.inputError]}>
          <TextInput
            style={styles.input}
            placeholder="student@email.com"
            placeholderTextColor={colors.textTertiary}
            value={email}
            onChangeText={(value) => {
              setEmail(value);
              setError('');
            }}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            editable={!loading}
            returnKeyType="send"
            onSubmitEditing={handleSendCode}
          />
        </View>

        {!!error && <Text style={styles.error}>{error}</Text>}

        <AnimatedButton
          title="Send Verification Code"
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
  logo: { width: 96, height: 96, marginBottom: spacing.lg },
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
  inputContainer: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    height: 58,
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  inputError: { borderColor: colors.error },
  input: { fontSize: 16, color: colors.text },
  error: { color: colors.error, fontSize: 14, marginBottom: spacing.md },
  button: { marginTop: spacing.md },
});
