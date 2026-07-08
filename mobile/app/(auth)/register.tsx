import { useState } from 'react';
import {
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

export default function RegisterScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSendOTP() {
    const normalized = email.trim().toLowerCase();
    if (!normalized || !normalized.includes('@')) {
      setError('Enter a valid email address.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const userId = await sendOTP(normalized);
      router.replace(`/(auth)/verify?userId=${userId}&email=${encodeURIComponent(normalized)}`);
    } catch (e: any) {
      setError(e?.message ?? 'Failed to send verification code.');
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
        <Text style={styles.title}>Create account</Text>
        <Text style={styles.subtitle}>Enter your email to receive a verification code.</Text>

        <View style={[styles.inputContainer, !!error && styles.inputError]}>
          <TextInput
            style={styles.input}
            placeholder="Email address"
            placeholderTextColor={colors.textTertiary}
            value={email}
            onChangeText={(v) => { setEmail(v); setError(''); }}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            editable={!loading}
            returnKeyType="go"
            onSubmitEditing={handleSendOTP}
          />
        </View>

        {!!error && <Text style={styles.error}>{error}</Text>}

        <AnimatedButton
          title="Send Verification Code"
          onPress={handleSendOTP}
          loading={loading}
          disabled={loading}
          style={styles.button}
        />

        <TouchableOpacity style={styles.switchButton} onPress={() => router.replace('/(auth)/login')}>
          <Text style={styles.switchText}>Already have an account? <Text style={styles.switchLink}>Sign in</Text></Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  backButton: {
    position: 'absolute', top: Platform.OS === 'ios' ? 58 : 22, left: spacing.md, zIndex: 10,
    flexDirection: 'row', alignItems: 'center', gap: 2, padding: spacing.sm,
  },
  backText: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.xl },
  title: { fontSize: 32, fontWeight: '800', color: colors.text, marginBottom: spacing.sm },
  subtitle: { fontSize: 16, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
  inputContainer: {
    backgroundColor: colors.surface, borderRadius: borderRadius.md,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, height: 58, marginBottom: spacing.md,
    justifyContent: 'center',
  },
  inputError: { borderColor: colors.error },
  input: { fontSize: 16, color: colors.text },
  error: { color: colors.error, fontSize: 14, marginBottom: spacing.md },
  button: { marginTop: spacing.md },
  switchButton: { alignItems: 'center', marginTop: spacing.lg },
  switchText: { color: colors.textSecondary, fontSize: 14 },
  switchLink: { color: colors.primary, fontWeight: '700' },
});
