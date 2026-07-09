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
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { AnimatedButton, ParticleBackground } from '../../src/components';
import { setPassword } from '../../src/lib/auth';

export default function SetPasswordScreen() {
  const router = useRouter();
  const { userId, email } = useLocalSearchParams<{ userId: string; email: string }>();
  const [password, setPasswordState] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSetPassword() {
    if (!password || password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await setPassword(userId!, password, email!);
      router.replace(`/(auth)/profile-setup?userId=${userId}`);
    } catch (e: any) {
      setError(e?.message ?? 'Failed to set password.');
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
        <Text style={styles.title}>Set a password</Text>
        <Text style={styles.subtitle}>Create a password to sign in quickly next time.</Text>

        <View style={[styles.inputContainer, !!error && styles.inputError]}>
          <TextInput
            style={[styles.input, { flex: 1 }]}
            placeholder="Password"
            placeholderTextColor={colors.textTertiary}
            value={password}
            onChangeText={(v) => { setPasswordState(v); setError(''); }}
            secureTextEntry={!showPw}
            autoCapitalize="none"
            editable={!loading}
          />
          <TouchableOpacity onPress={() => setShowPw(!showPw)} style={styles.eyeButton}>
            <Ionicons name={showPw ? 'eye-off-outline' : 'eye-outline'} size={20} color={colors.textTertiary} />
          </TouchableOpacity>
        </View>

        <View style={[styles.inputContainer, !!error && styles.inputError]}>
          <TextInput
            style={[styles.input, { flex: 1 }]}
            placeholder="Confirm password"
            placeholderTextColor={colors.textTertiary}
            value={confirm}
            onChangeText={(v) => { setConfirm(v); setError(''); }}
            secureTextEntry={!showConfirm}
            autoCapitalize="none"
            editable={!loading}
            returnKeyType="go"
            onSubmitEditing={handleSetPassword}
          />
          <TouchableOpacity onPress={() => setShowConfirm(!showConfirm)} style={styles.eyeButton}>
            <Ionicons name={showConfirm ? 'eye-off-outline' : 'eye-outline'} size={20} color={colors.textTertiary} />
          </TouchableOpacity>
        </View>

        {!!error && <Text style={styles.error}>{error}</Text>}

        <AnimatedButton
          title="Continue"
          onPress={handleSetPassword}
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
    position: 'absolute', top: Platform.OS === 'ios' ? 58 : 22, left: spacing.md, zIndex: 10,
    flexDirection: 'row', alignItems: 'center', gap: 2, padding: spacing.sm,
  },
  backText: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  content: { flex: 1, justifyContent: 'center', paddingHorizontal: spacing.xl },
  title: { fontSize: 32, fontWeight: '800', color: colors.text, marginBottom: spacing.sm },
  subtitle: { fontSize: 16, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
  inputContainer: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: colors.surface, borderRadius: borderRadius.md,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, height: 58, marginBottom: spacing.md,
  },
  inputError: { borderColor: colors.error },
  input: { fontSize: 16, color: colors.text },
  eyeButton: { padding: spacing.sm },
  error: { color: colors.error, fontSize: 14, marginBottom: spacing.md },
  button: { marginTop: spacing.md },
});
