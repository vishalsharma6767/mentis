import { useState, useCallback, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Animated,
  Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import { api, BASE_URL } from '../../src/lib/api';
import { restoreSession } from '../../src/lib/auth';

interface HomeworkItem {
  title: string;
  description: string;
  difficulty?: string;
}

interface QuizItem {
  question: string;
  options: string[];
  correct_answer: string;
  explanation: string;
}

interface LessonPlan {
  topic: string;
  subject: string;
  difficulty: string;
  prerequisites: string[];
  key_concepts: string[];
  total_steps: number;
  estimated_duration: number;
  homework: HomeworkItem[];
}

type LessonPhase = 'search' | 'loading' | 'planning' | 'teaching' | 'checkpoint' | 'quiz' | 'homework' | 'summary' | 'error';

const TOPICS = [
  { name: 'Turing Machine', icon: 'code-slash', category: 'Computer Science', difficulty: 'Advanced' },
  { name: 'Linked List', icon: 'link', category: 'Computer Science', difficulty: 'Intermediate' },
  { name: "Newton's Laws", icon: 'rocket', category: 'Physics', difficulty: 'Intermediate' },
  { name: 'DBMS', icon: 'server', category: 'Computer Science', difficulty: 'Advanced' },
  { name: 'Machine Learning', icon: 'brain', category: 'AI', difficulty: 'Advanced' },
  { name: 'Quadratic Equations', icon: 'calculator', category: 'Math', difficulty: 'Intermediate' },
  { name: 'Chemical Bonding', icon: 'flask', category: 'Chemistry', difficulty: 'Intermediate' },
  { name: 'Photosynthesis', icon: 'leaf', category: 'Biology', difficulty: 'Beginner' },
  { name: 'Sorting Algorithms', icon: 'swap-vertical', category: 'Computer Science', difficulty: 'Intermediate' },
  { name: 'Probability', icon: 'shuffle', category: 'Math', difficulty: 'Intermediate' },
  { name: 'Electric Circuits', icon: 'flash', category: 'Physics', difficulty: 'Advanced' },
  { name: 'Calculus', icon: 'trending-up', category: 'Math', difficulty: 'Advanced' },
  { name: 'Operating Systems', icon: 'server', category: 'Computer Science', difficulty: 'Advanced' },
  { name: 'Computer Networks', icon: 'globe', category: 'Computer Science', difficulty: 'Advanced' },
  { name: 'Organic Chemistry', icon: 'flask', category: 'Chemistry', difficulty: 'Advanced' },
  { name: 'Thermodynamics', icon: 'flame', category: 'Physics', difficulty: 'Advanced' },
];

const WELCOME_MESSAGES = [
  "Namaste beta! Aaj kaun sa topic seekhna chahte ho?",
  "Kya padhna hai aaj? Batao, main sikhata hoon.",
  "Aaj ka lesson kya hai? Type karo topic ka naam.",
  "Kaun sa concept samajhna hai? Main detail mein samjhaunga.",
  "Namaste! Aaj hum kya seekhenge?",
];

const PHASE_TITLES: Record<string, string> = {
  loading: "Teacher taiyar ho raha hai... 📚",
  planning: "Sabak plan kar raha hoon... 📋",
  teaching: "Pdh raha hoon... 🎓",
};

const DIFFICULTY_COLORS: Record<string, string> = {
  Beginner: '#44FF88',
  Intermediate: colors.warning,
  Advanced: '#FF3D8A',
};

export default function TeachMeScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [phase, setPhase] = useState<LessonPhase>('search');
  const [lessonContent, setLessonContent] = useState('');
  const [lessonPlan, setLessonPlan] = useState<LessonPlan | null>(null);
  const [keyPoints, setKeyPoints] = useState<string[]>([]);
  const [examples, setExamples] = useState<string[]>([]);
  const [analogy, setAnalogy] = useState('');
  const [checkpoints, setCheckpoints] = useState<string[]>([]);
  const [concepts, setConcepts] = useState<string[]>([]);
  const [recommendations, setRecommendations] = useState<string[]>([]);
  const [homework, setHomework] = useState<HomeworkItem[]>([]);
  const [quiz, setQuiz] = useState<QuizItem | null>(null);
  const [quizSelected, setQuizSelected] = useState<number | null>(null);
  const [quizResult, setQuizResult] = useState<boolean | null>(null);
  const [teacherSpeaking, setTeacherSpeaking] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [showTranscript, setShowTranscript] = useState(false);
  const [currentTopic, setCurrentTopic] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [userId, setUserId] = useState('anonymous');

  const speakAnim = useRef(new Animated.Value(0)).current;
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    restoreSession().then(s => { if (s?.userId) setUserId(s.userId); });
  }, []);

  useEffect(() => {
    if (teacherSpeaking) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(speakAnim, { toValue: 1, duration: 250, useNativeDriver: true }),
          Animated.timing(speakAnim, { toValue: 0, duration: 250, useNativeDriver: true }),
        ]),
      ).start();
    } else {
      speakAnim.setValue(0);
    }
  }, [teacherSpeaking]);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const filtered = TOPICS.filter(t =>
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.category.toLowerCase().includes(search.toLowerCase())
  );

  const resetLesson = useCallback(() => {
    setLessonContent('');
    setLessonPlan(null);
    setKeyPoints([]);
    setExamples([]);
    setAnalogy('');
    setCheckpoints([]);
    setConcepts([]);
    setRecommendations([]);
    setHomework([]);
    setQuiz(null);
    setQuizSelected(null);
    setQuizResult(null);
    setErrorMessage('');
  }, []);

  const startLesson = useCallback((topic: string) => {
    resetLesson();
    setCurrentTopic(topic);
    setPhase('loading');
    setLessonContent(`📖 **${topic}** — Teacher taiyar ho raha hai...\n\n`);
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

          switch (data.type) {
            case 'processing':
              if (data.phase === 'planning_lesson') setPhase('planning');
              break;

            case 'lesson_plan':
              setLessonPlan({
                topic: data.topic || topic,
                subject: data.subject || '',
                difficulty: data.difficulty || 'Intermediate',
                prerequisites: data.prerequisites || [],
                key_concepts: data.key_concepts || [],
                total_steps: data.total_steps || 0,
                estimated_duration: data.estimated_duration || 0,
                homework: data.homework || [],
              });
              if (data.prerequisites?.length) {
                setLessonContent(prev => prev + `📋 **Prerequisites**: ${data.prerequisites.join(', ')}\n\n`);
              }
              if (data.key_concepts?.length) {
                setConcepts(data.key_concepts);
                setLessonContent(prev => prev + `🎯 **Key Concepts**: ${data.key_concepts.join(', ')}\n\n`);
              }
              setPhase('teaching');
              break;

            case 'speech':
              setLessonContent(prev => prev + data.text + '\n\n');
              setTeacherSpeaking(true);
              setPhase(prev => prev === 'loading' || prev === 'planning' ? 'teaching' : prev);
              setTimeout(() => setTeacherSpeaking(false), Math.max(1500, data.text.length * 60));
              break;

            case 'board':
              break;

            case 'pointer':
              break;

            case 'thinking':
              setLessonContent(prev => prev + '🤔 ' + (data.text || 'Teacher soch raha hai...') + '\n\n');
              break;

            case 'question':
              setLessonContent(prev => prev + '\n❓ ' + data.text + '\n\n');
              setPhase('checkpoint');
              break;

            case 'analogy':
              setAnalogy(data.text);
              setLessonContent(prev => prev + `💡 **Real Life Example**: ${data.text}\n\n`);
              break;

            case 'examples':
              setExamples(data.examples || []);
              if (data.examples?.length) {
                setLessonContent(prev => prev + '📝 **Examples**:\n' + data.examples.map((e: string, i: number) => `${i + 1}. ${e}`).join('\n') + '\n\n');
              }
              break;

            case 'checkpoints':
              setCheckpoints(data.points || []);
              break;

            case 'key_points':
              setKeyPoints(data.points || []);
              if (data.points?.length) {
                setLessonContent(prev => prev + '📌 **Key Points**:\n' + data.points.map((p: string) => `• ${p}`).join('\n') + '\n\n');
              }
              break;

            case 'concepts':
              setConcepts(data.topics || []);
              break;

            case 'quiz':
              setQuiz(data.questions || null);
              setQuizSelected(null);
              setQuizResult(null);
              setPhase('quiz');
              setLessonContent(prev => prev + '\n📝 **Quick Quiz!**\n\n');
              break;

            case 'homework':
              setHomework(data.problems || []);
              break;

            case 'memory':
              if (data.revision_suggestions?.length) {
                setRecommendations(data.revision_suggestions);
              }
              break;

            case 'done':
              setSessionId(data.session_id || '');
              if (data.recommendations?.length) {
                setRecommendations(data.recommendations);
              }
              if (homework.length > 0 || lessonPlan?.homework?.length) {
                setPhase('homework');
              } else {
                setPhase('summary');
              }
              setLessonContent(prev => prev + '\n✅ **Lesson Complete!**\n\n');
              setTeacherSpeaking(false);
              break;

            case 'session_complete':
              setPhase('summary');
              break;

            case 'error':
              setErrorMessage(data.message || 'Something went wrong');
              setPhase('error');
              setTeacherSpeaking(false);
              break;
          }
        } catch {}
      };

      ws.onerror = () => {
        setErrorMessage('Connection failed. Check your network.');
        setPhase('error');
      };
    } catch {
      setErrorMessage('Failed to start lesson. Please try again.');
      setPhase('error');
    }
  }, [resetLesson]);

  const handleSearch = useCallback(() => {
    if (search.trim().length > 2) {
      startLesson(search.trim());
    }
  }, [search, startLesson]);

  const handleQuizAnswer = useCallback((idx: number) => {
    if (!quiz || quizResult !== null) return;
    setQuizSelected(idx);
    const correct = quiz.options[idx] === quiz.correct_answer;
    setQuizResult(correct);
  }, [quiz, quizResult]);

  const handleQuizContinue = useCallback(() => {
    if (homework.length > 0 || (lessonPlan?.homework?.length ?? 0) > 0) {
      setPhase('homework');
    } else {
      setPhase('summary');
    }
  }, [homework, lessonPlan]);

  const handleFinish = useCallback(async () => {
    try {
      await api.saveSessionV1({
        userId,
        sessionId: sessionId || `lesson_${Date.now()}`,
        problemTitle: currentTopic,
        problemType: 'lesson',
        extractedText: currentTopic,
        explanation: lessonContent,
        keyPoints,
        concepts,
        homework: homework.length ? homework : (lessonPlan?.homework || []),
        quiz: quiz || {},
        memoryUpdate: {},
      });
    } catch {}
    router.back();
  }, [userId, sessionId, currentTopic, lessonContent, keyPoints, concepts, homework, lessonPlan, quiz, router]);

  const handleRetry = useCallback(() => {
    resetLesson();
    setPhase('search');
    wsRef.current?.close();
  }, [resetLesson]);

  const allHomework = homework.length ? homework : (lessonPlan?.homework || []);

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.greeting}>
            {phase === 'search' ? WELCOME_MESSAGES[Math.floor(Math.random() * WELCOME_MESSAGES.length)] : ''}
          </Text>
          <Text style={styles.headline}>
            {phase === 'search' ? 'What do you want to learn?' :
             phase === 'summary' ? 'Lesson Complete! 🎉' :
             PHASE_TITLES[phase] || `Learning: ${currentTopic}`}
          </Text>
        </View>

        {/* Search */}
        {phase === 'search' && (
          <>
            <View style={styles.searchBox}>
              <Ionicons name="search" size={20} color={colors.textTertiary} />
              <TextInput
                style={styles.searchInput}
                placeholder="Search any topic..."
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
                    <View style={[styles.difficultyBadge, { backgroundColor: (DIFFICULTY_COLORS[topic.difficulty] || colors.primary) + '25' }]}>
                      <Text style={[styles.difficultyText, { color: DIFFICULTY_COLORS[topic.difficulty] || colors.primary }]}>{topic.difficulty}</Text>
                    </View>
                  </GlassCard>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}

        {/* Loading / Planning */}
        {(phase === 'loading' || phase === 'planning') && (
          <View style={styles.loadingContainer}>
            <View style={styles.loadingCard}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={styles.loadingTitle}>
                {phase === 'loading' ? PHASE_TITLES.loading : PHASE_TITLES.planning}
              </Text>
              <Text style={styles.loadingSub}>Kripya pratiksha karein...</Text>
            </View>
          </View>
        )}

        {/* Lesson Plan Info */}
        {lessonPlan && ['teaching', 'checkpoint', 'quiz', 'homework', 'summary'].includes(phase) && (
          <GlassCard style={styles.planCard}>
            <View style={styles.planRow}>
              <Ionicons name="school" size={20} color={colors.primary} />
              <Text style={styles.planTopic}>{lessonPlan.topic}</Text>
              <View style={[styles.diffBadge, { backgroundColor: (DIFFICULTY_COLORS[lessonPlan.difficulty] || colors.primary) + '25' }]}>
                <Text style={[styles.diffBadgeText, { color: DIFFICULTY_COLORS[lessonPlan.difficulty] || colors.primary }]}>{lessonPlan.difficulty}</Text>
              </View>
            </View>
            <View style={styles.planMeta}>
              <View style={styles.planMetaItem}>
                <Ionicons name="layers" size={14} color={colors.textTertiary} />
                <Text style={styles.planMetaText}>{lessonPlan.total_steps} steps</Text>
              </View>
              {lessonPlan.estimated_duration > 0 && (
                <View style={styles.planMetaItem}>
                  <Ionicons name="time" size={14} color={colors.textTertiary} />
                  <Text style={styles.planMetaText}>{Math.round(lessonPlan.estimated_duration / 60)} min</Text>
                </View>
              )}
              <View style={styles.planMetaItem}>
                <Ionicons name="book" size={14} color={colors.textTertiary} />
                <Text style={styles.planMetaText}>{lessonPlan.subject}</Text>
              </View>
            </View>
            {lessonPlan.prerequisites?.length > 0 && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.preReqRow}>
                {lessonPlan.prerequisites.map((pr, i) => (
                  <View key={i} style={styles.preReqChip}>
                    <Text style={styles.preReqText}>{pr}</Text>
                  </View>
                ))}
              </ScrollView>
            )}
          </GlassCard>
        )}

        {/* Teacher Speaking Indicator */}
        {teacherSpeaking && ['teaching', 'checkpoint'].includes(phase) && (
          <View style={styles.speakingIndicator}>
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }] }]} />
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.7 }]} />
            <Animated.View style={[styles.speakingBar, { transform: [{ scaleY: speakAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1.5] }) }], opacity: 0.5 }]} />
            <Text style={styles.speakingLabel}>Teacher is speaking...</Text>
          </View>
        )}

        {/* Concepts Chips */}
        {concepts.length > 0 && ['teaching', 'checkpoint'].includes(phase) && (
          <View style={styles.conceptsRow}>
            {concepts.map((c, i) => (
              <View key={i} style={styles.conceptChip}>
                <Ionicons name="bulb" size={12} color={colors.primary} />
                <Text style={styles.conceptChipText}>{c}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Analogy Card */}
        {analogy && phase === 'teaching' && (
          <GlassCard style={styles.analogyCard}>
            <View style={styles.analogyHeader}>
              <Ionicons name="bulb" size={20} color={colors.warning} />
              <Text style={styles.analogyTitle}>Real Life Example</Text>
            </View>
            <Text style={styles.analogyText}>{analogy}</Text>
          </GlassCard>
        )}

        {/* Checkpoint Question */}
        {phase === 'checkpoint' && (
          <GlassCard style={styles.checkpointCard}>
            <View style={styles.checkpointRow}>
              <Ionicons name="help-circle" size={22} color={colors.warning} />
              <Text style={styles.checkpointTitle}>Checkpoint</Text>
            </View>
            <TouchableOpacity
              style={styles.checkpointBtn}
              onPress={() => {
                setPhase('teaching');
                if (wsRef.current?.readyState === WebSocket.OPEN) {
                  wsRef.current.send(JSON.stringify({ type: 'student_response', text: 'Got it' }));
                }
              }}
            >
              <Ionicons name="checkmark-circle" size={20} color={colors.bg} />
              <Text style={styles.checkpointBtnText}>Samajh aa gaya!</Text>
            </TouchableOpacity>
          </GlassCard>
        )}

        {/* Quiz */}
        {phase === 'quiz' && quiz && (
          <GlassCard style={styles.quizCard}>
            <View style={styles.quizHeader}>
              <Ionicons name="bulb" size={24} color={colors.accent} />
              <Text style={styles.quizTitle}>Quick Quiz!</Text>
            </View>
            <Text style={styles.quizQuestion}>{quiz.question}</Text>
            <View style={styles.quizOptions}>
              {quiz.options.map((opt, i) => {
                const isSelected = quizSelected === i;
                const isCorrect = quizResult !== null && opt === quiz.correct_answer;
                const isWrong = quizResult !== null && isSelected && opt !== quiz.correct_answer;
                return (
                  <TouchableOpacity
                    key={i}
                    style={[
                      styles.quizOption,
                      isSelected && styles.quizOptionSelected,
                      isCorrect && styles.quizOptionCorrect,
                      isWrong && styles.quizOptionWrong,
                    ]}
                    onPress={() => handleQuizAnswer(i)}
                    disabled={quizResult !== null}
                  >
                    <Text style={[styles.quizLetter, isSelected && styles.quizLetterSelected]}>
                      {String.fromCharCode(65 + i)}
                    </Text>
                    <Text style={[styles.quizOptText, isSelected && styles.quizOptTextSelected]}>{opt}</Text>
                    {isCorrect && <Ionicons name="checkmark-circle" size={20} color={colors.success} />}
                    {isWrong && <Ionicons name="close-circle" size={20} color="#FF3D8A" />}
                  </TouchableOpacity>
                );
              })}
            </View>
            {quizResult !== null && (
              <View style={styles.quizResultBox}>
                <Text style={[styles.quizResultText, { color: quizResult ? colors.success : '#FF3D8A' }]}>
                  {quizResult ? 'Sahi jawab! 🎉' : 'Galat jawab. Sahi jawab: ' + quiz.correct_answer}
                </Text>
                <Text style={styles.quizExplanation}>{quiz.explanation}</Text>
                <TouchableOpacity style={styles.quizContBtn} onPress={handleQuizContinue}>
                  <Text style={styles.quizContText}>Continue</Text>
                  <Ionicons name="arrow-forward" size={16} color={colors.bg} />
                </TouchableOpacity>
              </View>
            )}
          </GlassCard>
        )}

        {/* Homework */}
        {phase === 'homework' && allHomework.length > 0 && (
          <GlassCard style={styles.homeworkCard}>
            <View style={styles.homeworkHeader}>
              <Ionicons name="book" size={24} color={colors.warning} />
              <Text style={styles.homeworkTitle}>Practice Time! 📝</Text>
            </View>
            {allHomework.map((item, i) => (
              <View key={i} style={styles.homeworkItem}>
                <View style={styles.hwBullet}><Text style={styles.hwNum}>{i + 1}</Text></View>
                <View style={styles.hwContent}>
                  <Text style={styles.hwItemTitle}>{item.title}</Text>
                  <Text style={styles.hwDesc}>{item.description}</Text>
                  {item.difficulty && <Text style={styles.hwDiff}>{item.difficulty}</Text>}
                </View>
              </View>
            ))}
            <TouchableOpacity style={styles.hwFinishBtn} onPress={() => setPhase('summary')}>
              <Ionicons name="checkmark-circle" size={18} color={colors.bg} />
              <Text style={styles.hwFinishText}>Complete Lesson</Text>
            </TouchableOpacity>
          </GlassCard>
        )}

        {/* Summary */}
        {phase === 'summary' && (
          <View style={styles.summarySection}>
            <GlassCard style={styles.summaryCard}>
              <View style={styles.summaryIcon}>
                <Ionicons name="checkmark-circle" size={48} color={colors.success} />
              </View>
              <Text style={styles.summaryTitle}>Lesson Complete! 🎉</Text>
              <Text style={styles.summaryTopic}>{currentTopic}</Text>

              {keyPoints.length > 0 && (
                <>
                  <Text style={styles.summarySectionTitle}>Key Points</Text>
                  {keyPoints.map((pt, i) => (
                    <View key={i} style={styles.summaryPoint}>
                      <Ionicons name="bulb" size={14} color={colors.warning} />
                      <Text style={styles.summaryPointText}>{pt}</Text>
                    </View>
                  ))}
                </>
              )}

              {concepts.length > 0 && (
                <View style={styles.summaryChips}>
                  {concepts.map((c, i) => (
                    <View key={i} style={styles.summaryChip}>
                      <Text style={styles.summaryChipText}>{c}</Text>
                    </View>
                  ))}
                </View>
              )}

              {recommendations.length > 0 && (
                <>
                  <Text style={styles.summarySectionTitle}>Recommendations</Text>
                  {recommendations.map((rec, i) => (
                    <View key={i} style={styles.recRow}>
                      <Ionicons name="arrow-forward" size={14} color={colors.primary} />
                      <Text style={styles.recText}>{rec}</Text>
                    </View>
                  ))}
                </>
              )}

              <TouchableOpacity style={styles.summaryBtn} onPress={handleFinish}>
                <Text style={styles.summaryBtnText}>Back to Dashboard</Text>
              </TouchableOpacity>
            </GlassCard>
          </View>
        )}

        {/* Error */}
        {phase === 'error' && (
          <View style={styles.errorCard}>
            <Ionicons name="alert-circle" size={48} color={colors.warning} />
            <Text style={styles.errorTitle}>Oops! 😅</Text>
            <Text style={styles.errorText}>{errorMessage}</Text>
            <View style={styles.errorActions}>
              <TouchableOpacity style={styles.errorRetryBtn} onPress={handleRetry}>
                <Ionicons name="refresh" size={18} color={colors.bg} />
                <Text style={styles.errorRetryText}>Try Again</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.errorBackBtn} onPress={() => router.back()}>
                <Text style={styles.errorBackText}>Go Back</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Transcript */}
        {showTranscript && lessonContent && phase !== 'summary' && phase !== 'error' && !['loading', 'planning'].includes(phase) && (
          <GlassCard style={styles.transcriptCard}>
            <View style={styles.transcriptHeader}>
              <Ionicons name="chatbubbles" size={16} color={colors.primary} />
              <Text style={styles.transcriptTitle}>Lesson</Text>
            </View>
            <Text style={styles.transcriptText}>{lessonContent}</Text>
          </GlassCard>
        )}

        {/* Sentiment badge */}
        {concepts.length > 0 && !['summary', 'error'].includes(phase) && (
          <View style={styles.conceptsFooter}>
            {concepts.map((c, i) => (
              <View key={i} style={styles.conceptChipSmall}>
                <Text style={styles.conceptSmallText}>{c}</Text>
              </View>
            ))}
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

  // Search
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
  difficultyBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  difficultyText: { fontSize: 10, fontWeight: '700' },

  // Loading
  loadingContainer: { alignItems: 'center', paddingVertical: spacing.xl },
  loadingCard: { backgroundColor: colors.surface, borderRadius: borderRadius.lg, padding: spacing.xl, alignItems: 'center', gap: spacing.md, borderWidth: 1, borderColor: colors.border, width: '100%' },
  loadingTitle: { fontSize: 18, fontWeight: '800', color: colors.text },
  loadingSub: { fontSize: 14, color: colors.textTertiary },

  // Lesson Plan Card
  planCard: { padding: spacing.md, gap: spacing.sm },
  planRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  planTopic: { fontSize: 16, fontWeight: '700', color: colors.text, flex: 1 },
  diffBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  diffBadgeText: { fontSize: 11, fontWeight: '700' },
  planMeta: { flexDirection: 'row', gap: spacing.md },
  planMetaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  planMetaText: { fontSize: 12, color: colors.textTertiary },
  preReqRow: { marginTop: spacing.xs },
  preReqChip: { backgroundColor: colors.primary + '15', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 8, marginRight: spacing.xs, borderWidth: 1, borderColor: colors.primary + '25' },
  preReqText: { fontSize: 11, color: colors.primary, fontWeight: '600' },

  // Speaking
  speakingIndicator: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: spacing.sm },
  speakingBar: { width: 3, height: 16, borderRadius: 2, backgroundColor: colors.success },
  speakingLabel: { color: colors.success, fontSize: 13, fontWeight: '600', marginLeft: spacing.sm },

  // Concepts
  conceptsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  conceptChip: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.primary + '18', paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: colors.primary + '25' },
  conceptChipText: { fontSize: 11, color: colors.primary, fontWeight: '600' },
  conceptsFooter: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.sm },
  conceptChipSmall: { backgroundColor: colors.primary + '12', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  conceptSmallText: { fontSize: 10, color: colors.primary, fontWeight: '500' },

  // Analogy
  analogyCard: { padding: spacing.md, gap: spacing.sm, backgroundColor: colors.warning + '10', borderColor: colors.warning + '30' },
  analogyHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  analogyTitle: { fontSize: 15, fontWeight: '700', color: colors.warning },
  analogyText: { fontSize: 14, color: colors.text, lineHeight: 20, fontStyle: 'italic' },

  // Checkpoint
  checkpointCard: { padding: spacing.md, gap: spacing.md, alignItems: 'center' },
  checkpointRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  checkpointTitle: { fontSize: 18, fontWeight: '700', color: colors.text },
  checkpointBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  checkpointBtnText: { color: colors.bg, fontWeight: '700', fontSize: 15 },

  // Quiz
  quizCard: { padding: spacing.md, gap: spacing.md },
  quizHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  quizTitle: { fontSize: 18, fontWeight: '800', color: colors.text },
  quizQuestion: { fontSize: 16, fontWeight: '600', color: colors.text, lineHeight: 22 },
  quizOptions: { gap: spacing.sm },
  quizOption: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, padding: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg },
  quizOptionSelected: { borderColor: colors.primary, backgroundColor: colors.primary + '15' },
  quizOptionCorrect: { borderColor: colors.success, backgroundColor: colors.success + '20' },
  quizOptionWrong: { borderColor: '#FF3D8A', backgroundColor: '#FF3D8A20' },
  quizLetter: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', fontWeight: '700', fontSize: 13, color: colors.text, borderWidth: 1, borderColor: colors.border, textAlign: 'center', lineHeight: 26 },
  quizLetterSelected: { backgroundColor: colors.primary, color: colors.bg, borderColor: colors.primary },
  quizOptText: { flex: 1, fontSize: 14, color: colors.text },
  quizOptTextSelected: { fontWeight: '600' },
  quizResultBox: { marginTop: spacing.sm, padding: spacing.md, backgroundColor: colors.bg, borderRadius: borderRadius.md, gap: spacing.sm },
  quizResultText: { fontSize: 16, fontWeight: '700' },
  quizExplanation: { fontSize: 13, color: colors.textSecondary, lineHeight: 18 },
  quizContBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, backgroundColor: colors.primary, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: borderRadius.md, marginTop: spacing.sm },
  quizContText: { color: colors.bg, fontWeight: '700', fontSize: 14 },

  // Homework
  homeworkCard: { padding: spacing.md, gap: spacing.sm },
  homeworkHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  homeworkTitle: { fontSize: 18, fontWeight: '800', color: colors.text },
  homeworkItem: { flexDirection: 'row', gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border + '60' },
  hwBullet: { width: 24, height: 24, borderRadius: 12, backgroundColor: colors.primary + '30', alignItems: 'center', justifyContent: 'center' },
  hwNum: { color: colors.primary, fontSize: 12, fontWeight: '700' },
  hwContent: { flex: 1, gap: 2 },
  hwItemTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  hwDesc: { color: colors.textSecondary, fontSize: 12, lineHeight: 16 },
  hwDiff: { fontSize: 10, color: colors.warning, fontWeight: '600', marginTop: 2 },
  hwFinishBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, backgroundColor: colors.primary, paddingVertical: spacing.md, borderRadius: borderRadius.md, marginTop: spacing.sm },
  hwFinishText: { color: colors.bg, fontWeight: '700', fontSize: 15 },

  // Summary
  summarySection: { paddingTop: spacing.md },
  summaryCard: { padding: spacing.xl, gap: spacing.md, alignItems: 'center' },
  summaryIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.success + '20', alignItems: 'center', justifyContent: 'center', marginBottom: spacing.sm },
  summaryTitle: { fontSize: 22, fontWeight: '800', color: colors.text },
  summaryTopic: { fontSize: 16, color: colors.primary, fontWeight: '600' },
  summarySectionTitle: { fontSize: 16, fontWeight: '700', color: colors.text, alignSelf: 'flex-start', marginTop: spacing.sm },
  summaryPoint: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm, alignSelf: 'flex-start' },
  summaryPointText: { fontSize: 13, color: colors.textSecondary, flex: 1 },
  summaryChips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },
  summaryChip: { backgroundColor: colors.primary + '20', paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: colors.primary + '30' },
  summaryChipText: { fontSize: 11, color: colors.primary, fontWeight: '600' },
  recRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, alignSelf: 'flex-start' },
  recText: { fontSize: 13, color: colors.textSecondary, flex: 1 },
  summaryBtn: { backgroundColor: colors.primary, paddingVertical: spacing.md, paddingHorizontal: spacing.xl, borderRadius: borderRadius.md, marginTop: spacing.md, width: '100%', alignItems: 'center' },
  summaryBtnText: { color: colors.bg, fontWeight: '700', fontSize: 16 },

  // Error
  errorCard: { alignItems: 'center', gap: spacing.md, padding: spacing.xl },
  errorTitle: { fontSize: 22, fontWeight: '800', color: colors.text },
  errorText: { fontSize: 14, color: colors.textSecondary, textAlign: 'center' },
  errorActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
  errorRetryBtn: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.primary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md },
  errorRetryText: { color: colors.bg, fontWeight: '700', fontSize: 15 },
  errorBackBtn: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border },
  errorBackText: { color: colors.textSecondary, fontWeight: '600', fontSize: 15 },

  // Transcript
  transcriptCard: { padding: spacing.md, gap: spacing.sm },
  transcriptHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  transcriptTitle: { fontSize: 14, fontWeight: '700', color: colors.text },
  transcriptText: { fontSize: 13, color: colors.textSecondary, lineHeight: 20 },
});
