import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
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
import { saveProfile } from '../../src/lib/auth';

const SUBJECTS = ['Math', 'Science', 'Coding', 'English', 'History', 'Art', 'Physics', 'Chemistry', 'Biology'];
const GOALS = ['Homework Help', 'Exam Prep', 'Practice Problems', 'Learn New Topics'];
const GRADES = ['6th', '7th', '8th', '9th', '10th', '11th', '12th', 'College', 'Adult'];

export default function ProfileSetupScreen() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [grade, setGrade] = useState('');
  const [subjects, setSubjects] = useState<string[]>([]);
  const [goal, setGoal] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  function toggleSubject(sub: string) {
    setSubjects((prev) =>
      prev.includes(sub) ? prev.filter((s) => s !== sub) : [...prev, sub]
    );
  }

  async function handleFinish() {
    if (!name.trim()) { setError('Enter your name.'); return; }
    if (!grade) { setError('Select your grade.'); return; }
    if (subjects.length === 0) { setError('Select at least one subject.'); return; }
    if (!goal) { setError('Select your goal.'); return; }

    setLoading(true);
    setError('');
    try {
      await saveProfile({ name: name.trim(), grade, subjects, goal });
      router.replace('/(tabs)');
    } catch (e: any) {
      setError(e?.message ?? 'Failed to save profile.');
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
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.content}>
          <Text style={styles.title}>Almost done!</Text>
          <Text style={styles.subtitle}>Tell us about yourself so Mentis can help you better.</Text>

          <View style={styles.progress}>
            {[0, 1, 2, 3].map((i) => (
              <View key={i} style={[styles.dot, i <= step && styles.dotActive]} />
            ))}
          </View>

          {step === 0 && (
            <>
              <Text style={styles.label}>What's your name?</Text>
              <View style={[styles.inputContainer, !!error && styles.inputError]}>
                <TextInput
                  style={styles.input}
                  placeholder="Your name"
                  placeholderTextColor={colors.textTertiary}
                  value={name}
                  onChangeText={(v) => { setName(v); setError(''); }}
                  autoCapitalize="words"
                  editable={!loading}
                  returnKeyType="next"
                  onSubmitEditing={() => setStep(1)}
                />
              </View>
              {!!error && <Text style={styles.error}>{error}</Text>}
              <AnimatedButton title="Next" onPress={() => { if (!name.trim()) setError('Enter your name.'); else { setError(''); setStep(1); } }} style={styles.button} />
            </>
          )}

          {step === 1 && (
            <>
              <Text style={styles.label}>What grade are you in?</Text>
              <View style={styles.grid}>
                {GRADES.map((g) => (
                  <TouchableOpacity
                    key={g}
                    style={[styles.chip, grade === g && styles.chipSelected]}
                    onPress={() => { setGrade(g); setError(''); }}
                    disabled={loading}
                  >
                    <Text style={[styles.chipText, grade === g && styles.chipTextSelected]}>{g}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {!!error && <Text style={styles.error}>{error}</Text>}
              <View style={styles.navRow}>
                <AnimatedButton title="Back" variant="ghost" onPress={() => setStep(0)} style={styles.navButton} />
                <AnimatedButton title="Next" onPress={() => { if (!grade) setError('Select your grade.'); else { setError(''); setStep(2); } }} style={styles.navButton} />
              </View>
            </>
          )}

          {step === 2 && (
            <>
              <Text style={styles.label}>What subjects are you learning?</Text>
              <View style={styles.grid}>
                {SUBJECTS.map((s) => (
                  <TouchableOpacity
                    key={s}
                    style={[styles.chip, subjects.includes(s) && styles.chipSelected]}
                    onPress={() => toggleSubject(s)}
                    disabled={loading}
                  >
                    <Text style={[styles.chipText, subjects.includes(s) && styles.chipTextSelected]}>{s}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {!!error && <Text style={styles.error}>{error}</Text>}
              <View style={styles.navRow}>
                <AnimatedButton title="Back" variant="ghost" onPress={() => setStep(1)} style={styles.navButton} />
                <AnimatedButton title="Next" onPress={() => { if (subjects.length === 0) setError('Select at least one subject.'); else { setError(''); setStep(3); } }} style={styles.navButton} />
              </View>
            </>
          )}

          {step === 3 && (
            <>
              <Text style={styles.label}>What's your main goal?</Text>
              <View style={styles.grid}>
                {GOALS.map((g) => (
                  <TouchableOpacity
                    key={g}
                    style={[styles.chip, goal === g && styles.chipSelected]}
                    onPress={() => { setGoal(g); setError(''); }}
                    disabled={loading}
                  >
                    <Text style={[styles.chipText, goal === g && styles.chipTextSelected]}>{g}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              {!!error && <Text style={styles.error}>{error}</Text>}
              <View style={styles.navRow}>
                <AnimatedButton title="Back" variant="ghost" onPress={() => setStep(2)} style={styles.navButton} />
                <AnimatedButton
                  title="Get Started"
                  onPress={handleFinish}
                  loading={loading}
                  disabled={loading}
                  style={styles.navButton}
                />
              </View>
            </>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { flexGrow: 1, justifyContent: 'center' },
  content: { paddingHorizontal: spacing.xl, paddingVertical: spacing.xxl },
  title: { fontSize: 32, fontWeight: '800', color: colors.text, marginBottom: spacing.sm },
  subtitle: { fontSize: 16, color: colors.textSecondary, lineHeight: 24, marginBottom: spacing.xl },
  progress: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.xl },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.border },
  dotActive: { width: 24, backgroundColor: colors.primary },
  label: { fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: spacing.md },
  inputContainer: {
    backgroundColor: colors.surface, borderRadius: borderRadius.md,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, height: 58, marginBottom: spacing.md,
    justifyContent: 'center',
  },
  inputError: { borderColor: colors.error },
  input: { fontSize: 16, color: colors.text },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.md },
  chip: {
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    borderRadius: borderRadius.full, backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border,
  },
  chipSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.textSecondary, fontSize: 14, fontWeight: '600' },
  chipTextSelected: { color: colors.bg },
  navRow: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  navButton: { flex: 1 },
  error: { color: colors.error, fontSize: 14, marginBottom: spacing.md },
  button: { marginTop: spacing.lg },
});
