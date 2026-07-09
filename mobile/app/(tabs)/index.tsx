import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography } from '../../src/theme';
import { GlassCard, AnimatedButton } from '../../src/components';
import { restoreSession } from '../../src/lib/auth';
import { api } from '../../src/lib/api';

export default function DashboardScreen() {
  const router = useRouter();
  const [greeting, setGreeting] = useState('Good morning');
  const [stats, setStats] = useState<{ totalSessions: number; completedSessions: number; topTopics: [string, number][] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [streak, setStreak] = useState(0);

  useEffect(() => {
    const hour = new Date().getHours();
    if (hour < 12) setGreeting('Good morning');
    else if (hour < 17) setGreeting('Good afternoon');
    else setGreeting('Good evening');

    async function load() {
      try {
        const session = await restoreSession();
        if (session) {
          const [data, streakData] = await Promise.all([
            api.getStats(session.userId),
            api.getStreak(session.userId),
          ]);
          setStats(data);
          setStreak(streakData.streak);
        }
      } catch {} finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const quickActions = [
    { title: 'Start AR Tutor', icon: 'scan', color: colors.primary, route: '/scan' },
    { title: 'Practice', icon: 'document-text', color: colors.accent, route: '/scan?mode=homework' },
    { title: 'Community', icon: 'people', color: colors.secondary, route: '/community' },
    { title: 'Study Groups', icon: 'people-circle', color: '#44FF88', route: '/study-groups' },
  ];

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
                  <Text style={styles.streakSub}>Keep it going!</Text>
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
          {quickActions.map((action, i) => (
            <TouchableOpacity key={i} style={styles.actionShell} onPress={() => router.push(action.route as any)}>
              <GlassCard style={styles.actionCard}>
                <View style={[styles.actionIcon, { backgroundColor: action.color + '20' }]}>
                  <Ionicons name={action.icon as any} size={28} color={action.color} />
                </View>
                <Text style={styles.actionTitle}>{action.title}</Text>
              </GlassCard>
            </TouchableOpacity>
          ))}
        </View>

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
            <Text style={styles.statValue}>{stats?.topTopics.length ?? 0}</Text>
            <Text style={styles.statLabel}>Topics</Text>
          </GlassCard>
        </View>

        {stats && stats.topTopics.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Top Topics</Text>
            <GlassCard style={styles.topicsCard}>
              {stats.topTopics.map(([topic, count], i) => (
                <View key={topic} style={[styles.topicRow, i > 0 && styles.topicBorder]}>
                  <View style={styles.topicLeft}>
                    <View style={[styles.topicDot, { backgroundColor: colors.primary }]} />
                    <Text style={styles.topicName}>{topic}</Text>
                  </View>
                  <Text style={styles.topicCount}>{count}x</Text>
                </View>
              ))}
            </GlassCard>
          </>
        )}

        <AnimatedButton
          title="Start AR Session"
          onPress={() => router.push('/scan')}
          style={styles.ctaButton}
        />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: spacing.lg,
    paddingTop: 60,
    paddingBottom: 100,
    gap: spacing.lg,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  greeting: {
    fontSize: 14,
    color: colors.textSecondary,
    marginBottom: 4,
  },
  headline: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.text,
    lineHeight: 34,
  },
  avatarButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.surfaceLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  streakCard: {
    padding: spacing.md,
    backgroundColor: colors.warning + '15',
    borderColor: colors.warning + '30',
  },
  streakRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  streakLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  streakNumber: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  streakSub: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 2,
  },
  streakDots: {
    flexDirection: 'row',
    gap: 6,
  },
  streakDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.border,
  },
  streakDotActive: {
    backgroundColor: colors.warning,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
  },
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  actionShell: {
    width: '47%',
  },
  actionCard: {
    padding: spacing.md,
    gap: spacing.sm,
  },
  actionIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
  },
  statsRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  statCard: {
    flex: 1,
    padding: spacing.md,
    alignItems: 'center',
    gap: spacing.xs,
  },
  statValue: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.text,
  },
  statLabel: {
    fontSize: 12,
    color: colors.textTertiary,
    fontWeight: '600',
  },
  topicsCard: {
    padding: spacing.md,
    gap: spacing.xs,
  },
  topicRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  topicBorder: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  topicLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  topicDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  topicName: {
    fontSize: 14,
    color: colors.text,
    fontWeight: '500',
    textTransform: 'capitalize',
  },
  topicCount: {
    fontSize: 14,
    color: colors.primary,
    fontWeight: '700',
  },
  ctaButton: {
    marginTop: spacing.md,
  },
});
