import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography } from '../../src/theme';
import { GlassCard, ParticleBackground } from '../../src/components';
import { restoreSession } from '../../src/lib/auth';
import { api } from '../../src/lib/api';

const quickActions = [
  { title: 'Live Tutor', icon: 'scan-outline', color: colors.primary, route: '/scan' },
  { title: 'AR Realtime', icon: 'scan-outline', color: colors.accent, route: '/ar-tutor-realtime' },
  { title: 'Homework', icon: 'document-text-outline', color: colors.secondary, route: '/scan?mode=homework' },
  { title: 'Coding Help', icon: 'code-slash-outline', color: '#44FF88', route: '/scan?mode=coding' },
];

export default function HomeScreen() {
  const router = useRouter();
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const session = await restoreSession();
        if (session) {
          const data = await api.listSessions(session.userId, 5);
          setSessions(data.sessions);
        }
      } catch {} finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <View style={styles.container}>
      <ParticleBackground />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.greeting}>Welcome back</Text>
        <Text style={styles.headline}>What would you like to learn?</Text>

        <View style={styles.actionsGrid}>
          {quickActions.map((action, i) => (
            <TouchableOpacity key={i} style={styles.actionShell} onPress={() => router.push(action.route as any)}>
              <GlassCard style={styles.actionCard}>
                <View style={[styles.actionIcon, { backgroundColor: action.color + '20' }]}>
                  <Ionicons name={action.icon as any} size={24} color={action.color} />
                </View>
                <Text style={styles.actionTitle}>{action.title}</Text>
              </GlassCard>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.sectionTitle}>Recent Sessions</Text>
        {loading ? (
          <GlassCard style={styles.emptyCard}>
            <ActivityIndicator size="small" color={colors.primary} />
          </GlassCard>
        ) : sessions.length === 0 ? (
          <GlassCard style={styles.emptyCard}>
            <Ionicons name="time-outline" size={32} color={colors.textTertiary} />
            <Text style={styles.emptyText}>No sessions yet{'\n'}Scan your first problem to get started</Text>
          </GlassCard>
        ) : (
          <View style={styles.sessionList}>
            {sessions.map((s: any) => (
              <GlassCard key={s.$id} style={styles.sessionCard}>
                <View style={styles.sessionRow}>
                  <View style={[styles.sessionIcon, { backgroundColor: (s.problemType === 'math' ? colors.primary : colors.secondary) + '20' }]}>
                    <Ionicons
                      name={s.problemType === 'math' ? 'calculator-outline' : 'document-text-outline'}
                      size={20}
                      color={s.problemType === 'math' ? colors.primary : colors.secondary}
                    />
                  </View>
                  <View style={styles.sessionInfo}>
                    <Text style={styles.sessionTitle} numberOfLines={1}>{s.problemTitle || s.problemType || 'Problem'}</Text>
                    <Text style={styles.sessionDate}>{new Date(s.createdAt).toLocaleDateString()}</Text>
                  </View>
                  <Ionicons name="checkmark-circle" size={20} color={s.status === 'completed' ? '#44FF88' : colors.textTertiary} />
                </View>
              </GlassCard>
            ))}
          </View>
        )}
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
  },
  greeting: {
    fontSize: 16,
    color: colors.textSecondary,
    marginBottom: spacing.xs,
  },
  headline: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.xl,
    lineHeight: 36,
  },
  actionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginBottom: spacing.xl,
  },
  actionShell: {
    width: '47%',
    aspectRatio: 1,
  },
  actionCard: {
    flex: 1,
  },
  actionIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  actionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
    marginBottom: spacing.md,
  },
  emptyCard: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xl,
    gap: spacing.md,
  },
  emptyText: {
    fontSize: 14,
    color: colors.textTertiary,
    textAlign: 'center',
    lineHeight: 20,
  },
  sessionList: {
    gap: spacing.sm,
  },
  sessionCard: {
    padding: spacing.md,
  },
  sessionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  sessionIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sessionInfo: {
    flex: 1,
  },
  sessionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.text,
  },
  sessionDate: {
    fontSize: 12,
    color: colors.textTertiary,
    marginTop: 2,
  },
});
