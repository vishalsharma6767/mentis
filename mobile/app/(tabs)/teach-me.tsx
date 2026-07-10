import { useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Platform,
  Animated,
  Easing,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import { api, BASE_URL } from '../../src/lib/api';

const TOPICS = [
  { name: 'Turing Machine', icon: 'code-slash', category: 'Computer Science' },
  { name: 'Linked List', icon: 'link', category: 'Computer Science' },
  { name: 'Newton\'s Laws', icon: 'rocket', category: 'Physics' },
  { name: 'DBMS', icon: 'server', category: 'Computer Science' },
  { name: 'Machine Learning', icon: 'brain', category: 'AI' },
  { name: 'Quadratic Equations', icon: 'calculator', category: 'Math' },
  { name: 'Chemical Bonding', icon: 'flask', category: 'Chemistry' },
  { name: 'Photosynthesis', icon: 'leaf', category: 'Biology' },
  { name: 'Sorting Algorithms', icon: 'swap-vertical', category: 'Computer Science' },
  { name: 'Probability', icon: 'shuffle', category: 'Math' },
  { name: 'Electric Circuits', icon: 'flash', category: 'Physics' },
  { name: 'Calculus', icon: 'trending-up', category: 'Math' },
];

const WELCOME_MESSAGES = [
  "Namaste beta! Aaj kaun sa topic seekhna chahte ho?",
  "Kya padhna hai aaj? Batao, main sikhata hoon.",
  "Aaj ka lesson kya hai? Type karo topic ka naam.",
  "Kaun sa concept samajhna hai? Main detail mein samjhaunga.",
];

export default function TeachMeScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [lessonStarted, setLessonStarted] = useState(false);
  const [lessonContent, setLessonContent] = useState('');
  const [teacherSpeaking, setTeacherSpeaking] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const speakAnim = useRef(new Animated.Value(0)).current;
  const wsRef = useRef<WebSocket | null>(null);

  const filtered = TOPICS.filter(t =>
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.category.toLowerCase().includes(search.toLowerCase())
  );

  const startLesson = useCallback(async (topic: string) => {
    setLoading(true);
    setLessonStarted(true);
    setLessonContent('');
    setShowTranscript(true);

    try {
      const wsUrl = `${BASE_URL.replace('http', 'ws')}/api/v1/teach/stream`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'lesson', topic, level: 'intermediate' }));
      };
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'speech') {
            setLessonContent(prev => prev + data.text + '\n');
            setTeacherSpeaking(true);
            setTimeout(() => setTeacherSpeaking(false), data.text.split(' ').length * 150);
          } else if (data.type === 'thinking') {
            setLessonContent(prev => prev + '🤔 ' + (data.text || 'Thinking...') + '\n');
          } else if (data.type === 'question') {
            setLessonContent(prev => prev + '\n❓ ' + data.text + '\n');
          } else if (data.type === 'board') {
            // Board action received
          } else if (data.type === 'quiz') {
            setLessonContent(prev => prev + '\n📝 Quiz: Check your understanding!\n');
          } else if (data.type === 'homework') {
            setLessonContent(prev => prev + '\n📚 Homework assigned!\n');
          } else if (data.type === 'done') {
            setLessonContent(prev => prev + '\n✅ Lesson complete!\n');
            setLoading(false);
          } else if (data.type === 'error') {
            setLessonContent(prev => prev + '\n⚠️ ' + data.message + '\n');
            setLoading(false);
          }
        } catch {}
      };
      ws.onerror = () => setLoading(false);
    } catch {
      setLoading(false);
    }
  }, []);

  const handleSearch = useCallback(() => {
    if (search.trim().length > 2) {
      startLesson(search.trim());
    }
  }, [search, startLesson]);

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <Text style={styles.greeting}>{WELCOME_MESSAGES[Math.floor(Math.random() * WELCOME_MESSAGES.length)]}</Text>
          <Text style={styles.headline}>What do you want to learn?</Text>
        </View>

        <View style={styles.searchBox}>
          <Ionicons name="search" size={20} color={colors.textTertiary} />
          <TextInput
            style={styles.searchInput}
            placeholder="Search topic..."
            placeholderTextColor={colors.textTertiary}
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={handleSearch}
            returnKeyType="search"
          />
          <TouchableOpacity onPress={handleSearch}>
            <Ionicons name="arrow-forward" size={20} color={colors.primary} />
          </TouchableOpacity>
        </View>

        {!lessonStarted && (
          <>
            <Text style={styles.sectionTitle}>Popular Topics</Text>
            <View style={styles.topicsGrid}>
              {filtered.map((topic, i) => (
                <TouchableOpacity key={i} style={styles.topicCard} onPress={() => startLesson(topic.name)}>
                  <GlassCard style={styles.topicCardInner}>
                    <View style={styles.topicIcon}>
                      <Ionicons name={topic.icon as any} size={24} color={colors.primary} />
                    </View>
                    <Text style={styles.topicName}>{topic.name}</Text>
                    <Text style={styles.topicCategory}>{topic.category}</Text>
                  </GlassCard>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}

        {lessonStarted && (
          <View style={styles.lessonContainer}>
            {loading && (
              <View style={styles.thinkingRow}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={styles.thinkingText}>Teacher is preparing...</Text>
              </View>
            )}
            {teacherSpeaking && (
              <View style={styles.speakingRow}>
                <Animated.View style={styles.speakingDot} />
                <Text style={styles.speakingText}>Teacher is speaking...</Text>
              </View>
            )}
            {showTranscript && lessonContent && (
              <GlassCard style={styles.transcriptCard}>
                <View style={styles.transcriptHeader}>
                  <Ionicons name="chatbubbles" size={18} color={colors.primary} />
                  <Text style={styles.transcriptTitle}>Lesson</Text>
                </View>
                <Text style={styles.transcriptText}>{lessonContent}</Text>
              </GlassCard>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { flex: 1 },
  scrollContent: { padding: spacing.lg, paddingTop: 60, paddingBottom: 100, gap: spacing.lg },
  header: { gap: spacing.xs, marginBottom: spacing.sm },
  greeting: { fontSize: 15, color: colors.primary, fontWeight: '600', lineHeight: 22 },
  headline: { fontSize: 28, fontWeight: '700', color: colors.text, lineHeight: 34 },
  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    backgroundColor: colors.surface, borderRadius: borderRadius.md,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  searchInput: { flex: 1, fontSize: 16, color: colors.text, paddingVertical: 4 },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: colors.text, marginTop: spacing.sm },
  topicsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  topicCard: { width: '47%' },
  topicCardInner: { padding: spacing.md, gap: spacing.xs, alignItems: 'center' },
  topicIcon: { width: 48, height: 48, borderRadius: 14, backgroundColor: colors.primary + '20', alignItems: 'center', justifyContent: 'center' },
  topicName: { fontSize: 14, fontWeight: '700', color: colors.text, textAlign: 'center' },
  topicCategory: { fontSize: 11, color: colors.textTertiary, fontWeight: '600' },
  lessonContainer: { gap: spacing.md },
  thinkingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.sm },
  thinkingText: { color: colors.textSecondary, fontSize: 14 },
  speakingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.sm },
  speakingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },
  speakingText: { color: colors.success, fontSize: 14, fontWeight: '600' },
  transcriptCard: { padding: spacing.md, gap: spacing.sm },
  transcriptHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  transcriptTitle: { fontSize: 14, fontWeight: '700', color: colors.text },
  transcriptText: { fontSize: 13, color: colors.textSecondary, lineHeight: 20 },
});
