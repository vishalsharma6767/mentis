import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing } from '../../src/theme';
import { GlassCard, AnimatedButton } from '../../src/components';
import { restoreSession } from '../../src/lib/auth';
import { api } from '../../src/lib/api';

const QUICK_ACTIONS = [
  { title: 'Ask Doubt', icon: 'camera', color: colors.primary, route: '/ask-doubt', desc: 'Camera or upload' },
  { title: 'Teach Me', icon: 'school', color: colors.accent, route: '/teach-me', desc: 'Any topic' },
  { title: 'Practice', icon: 'document-text', color: colors.secondary, route: '/ask-doubt', desc: 'Solve problems' },
  { title: 'Community', icon: 'people', color: '#44FF88', route: '/community', desc: 'Learn together' },
];

export default function DashboardScreen() {
  const router = useRouter();
  const [greeting, setGreeting] = useState('Good morning');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<{
    totalSessions: number;
    completedSessions: number;
    topTopics: [string, number][];
    weakTopics: string[];
    strongTopics: string[];
  } | null>(null);
  const [streak, setStreak] = useState(0);
  const [recentSessions, setRecentSessions] = useState<any[]>([]);
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    const hour = new Date().getHours();
    if (hour < 12) setGreeting('Namaste');
    else if (hour < 17) setGreeting('Good afternoon');
    else setGreeting('Good evening');

    async function load() {
      try {
        const session = await restoreSession();
        const uid = session?.userId || 'anonymous';
        setUserId(uid);

        const [data, streakData, sessionsData] = await Promise.all([
          api.getStats(uid).catch(() => null),
          api.getStreak(uid).catch(() => ({ streak: 0 })),
          api.listSessions(uid, 5).catch(() => ({ sessions: [] })),
        ]);

        if (data) {
          const weak: string[] = [];
          const strong: string[] = [];
          if (data.topTopics) {
            data.topTopics.forEach(([topic, count]) => {
              if (count < 3) weak.push(topic);
              else strong.push(topic);
            });
          }
          setStats({ ...data, weakTopics: weak, strongTopics: strong });
        }
        setStreak(streakData?.streak ?? 0);
        setRecentSessions(sessionsData?.sessions || []);
      } catch {} finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const weakTopics = stats?.weakTopics || [];
  const continueTopics = (stats?.topTopics || []).slice(0, 3);

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>{greeting}</Text>
            <Text style={styles.headline}>What will you learn today?</Text>
          </View>
          <TouchableOpacity style={styles.avatarButton} onPress={() => router.push('/profile')}>
            <View style={styles.avatar}>
              <Ionicons name="person" size={24} color={colors.primary} />
            </View>
          </TouchableOpacity>
        </View>

        {streak > 0 && (
          <GlassCard style={styles.streakCard}>
            <View style={styles.streakRow}>
              <View style={styles.streakLeft}>
                <Ionicons name="flame" size={28} color={colors.warning} />
                <View>
                  <Text style={styles.streakNumber}>{streak} Day Streak</Text>
                  <Text style={styles.streakSub}>Keep learning daily!</Text>
                </View>
              </View>
              <View style={styles.streakDots}>
                {[...Array(7)].map((_, i) => (
                  <View key={i} style={[styles.streakDot, i < Math.min(streak, 7) && styles.streakDotActive]} />
                ))}
              </View>
            </View>
          </GlassCard>
        )}

        <Text style={styles.sectionTitle}>Quick Actions</Text>
        <View style={styles.actionsGrid}>
          {QUICK_ACTIONS.map((action, i) => (
            <TouchableOpacity key={i} style={styles.actionShell} onPress={() => router.push(action.route as any)}>
              <GlassCard style={styles.actionCard}>
                <View style={[styles.actionIcon, { backgroundColor: action.color + '20' }]}>
                  <Ionicons name={action.icon as any} size={28} color={action.color} />
                </View>
                <Text style={styles.actionTitle}>{action.title}</Text>
                <Text style={styles.actionDesc}>{action.desc}</Text>
              </GlassCard>
            </TouchableOpacity>
          ))}
        </View>

        {continueTopics.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Continue Learning</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.continueRow}>
              {continueTopics.map(([topic, count], i) => (
                <TouchableOpacity key={i} onPress={() => router.push('/teach-me')}>
                  <GlassCard style={styles.continueCard}>
                    <View style={styles.continueHeader}>
                      <Text style={styles.continueName}>{topic}</Text>
                      {weakTopics.includes(topic) && (
                        <View style={styles.weakBadge}><Text style={styles.weakText}>Weak</Text></View>
                      )}
                    </View>
                    <View style={styles.progressBar}>
                      <View style={[styles.progressFill, { width: `${Math.min(count * 20, 100)}%` }]} />
                    </View>
                    <Text style={styles.progressText}>{Math.min(count * 20, 100)}% complete</Text>
                  </GlassCard>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </>
        )}

        {weakTopics.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Weak Topics — Need Revision</Text>
            <GlassCard style={styles.weakCard}>
              {weakTopics.map((topic, i) => (
                <TouchableOpacity key={i} style={[styles.weakRow, i > 0 && styles.weakBorder]} onPress={() => router.push('/teach-me')}>
                  <Ionicons name="alert-circle" size={18} color={colors.warning} />
                  <Text style={styles.weakName}>{topic}</Text>
                  <Ionicons name="arrow-forward" size={16} color={colors.textTertiary} />
                </TouchableOpacity>
              ))}
            </GlassCard>
          </>
        )}

        <Text style={styles.sectionTitle}>Your Progress</Text>
        <View style={styles.statsRow}>
          <GlassCard style={styles.statCard}>
            <Text style={styles.statValue}>{loading ? '-' : stats?.completedSessions ?? 0}</Text>
            <Text style={styles.statLabel}>Completed</Text>
          </GlassCard>
          <GlassCard style={styles.statCard}>
            <Text style={styles.statValue}>{loading ? '-' : stats?.totalSessions ?? 0}</Text>
            <Text style={styles.statLabel}>Total Sessions</Text>
          </GlassCard>
          <GlassCard style={styles.statCard}>
            <Text style={styles.statValue}>{streak}</Text>
            <Text style={styles.statLabel}>Day Streak</Text>
          </GlassCard>
        </View>

        {recentSessions.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Recent Sessions</Text>
            <GlassCard style={styles.recentCard}>
              {recentSessions.slice(0, 3).map((s: any, i: number) => (
                <View key={i} style={[styles.recentRow, i > 0 && styles.weakBorder]}>
                  <Ionicons name="book" size={16} color={colors.primary} />
                  <Text style={styles.recentName} numberOfLines={1}>
                    {(s.problemTitle || s.extractedText || 'Session')?.slice(0, 40)}
                  </Text>
                  <Text style={styles.recentStatus}>{s.status || 'completed'}</Text>
                </View>
              ))}
            </GlassCard>
          </>
        )}

        <AnimatedButton
          title="Ask a Doubt"
          onPress={() => router.push('/ask-doubt')}
          style={styles.ctaButton}
        />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { flex: 1 },
  scrollContent: { padding: spacing.lg, paddingTop: 60, paddingBottom: 100, gap: spacing.lg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: spacing.md },
  greeting: { fontSize: 14, color: colors.textSecondary, marginBottom: 4 },
  headline: { fontSize: 28, fontWeight: '700', color: colors.text, lineHeight: 34 },
  avatarButton: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.surfaceLight, alignItems: 'center', justifyContent: 'center' },
  streakCard: { padding: spacing.md, backgroundColor: colors.warning + '15', borderColor: colors.warning + '30' },
  streakRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  streakLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  streakNumber: { fontSize: 18, fontWeight: '700', color: colors.text },
  streakSub: { fontSize: 13, color: colors.textSecondary, marginTop: 2 },
  streakDots: { flexDirection: 'row', gap: 6 },
  streakDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.border },
  streakDotActive: { backgroundColor: colors.warning },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: spacing.sm },
  actionsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  actionShell: { width: '47%' },
  actionCard: { padding: spacing.md, gap: spacing.xs },
  actionIcon: { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  actionTitle: { fontSize: 14, fontWeight: '600', color: colors.text },
  actionDesc: { fontSize: 11, color: colors.textTertiary, fontWeight: '500' },
  continueRow: { marginBottom: spacing.sm },
  continueCard: { padding: spacing.md, marginRight: spacing.md, minWidth: 180, gap: spacing.sm },
  continueHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  continueName: { fontSize: 14, fontWeight: '700', color: colors.text, flex: 1 },
  weakBadge: { backgroundColor: colors.warning + '30', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  weakText: { fontSize: 10, fontWeight: '700', color: colors.warning },
  progressBar: { height: 4, backgroundColor: colors.border, borderRadius: 2, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: colors.primary, borderRadius: 2 },
  progressText: { fontSize: 11, color: colors.textTertiary, fontWeight: '600' },
  weakCard: { padding: spacing.md, gap: spacing.xs },
  weakRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.sm },
  weakBorder: { borderTopWidth: 1, borderTopColor: colors.border },
  weakName: { flex: 1, fontSize: 14, color: colors.text, fontWeight: '500' },
  statsRow: { flexDirection: 'row', gap: spacing.md },
  statCard: { flex: 1, padding: spacing.md, alignItems: 'center', gap: spacing.xs },
  statValue: { fontSize: 24, fontWeight: '700', color: colors.text },
  statLabel: { fontSize: 12, color: colors.textTertiary, fontWeight: '600' },
  recentCard: { padding: spacing.md, gap: spacing.xs },
  recentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.sm },
  recentName: { flex: 1, fontSize: 13, color: colors.text, fontWeight: '500' },
  recentStatus: { fontSize: 11, color: colors.textTertiary, fontWeight: '600', textTransform: 'capitalize' },
  ctaButton: { marginTop: spacing.md },
});
