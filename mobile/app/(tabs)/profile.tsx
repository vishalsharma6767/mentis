import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography } from '../../src/theme';
import { GlassCard, AnimatedButton } from '../../src/components';
import { logout, restoreSession } from '../../src/lib/auth';
import { api } from '../../src/lib/api';

export default function ProfileScreen() {
  const router = useRouter();
  const [stats, setStats] = useState<{ totalSessions: number; completedSessions: number; topTopics: [string, number][] } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const session = await restoreSession();
        if (session) {
          const data = await api.getStats(session.userId);
          setStats(data);
        }
      } catch {} finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleLogout() {
    await logout();
    router.replace('/(auth)');
  }

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>Profile</Text>

        <GlassCard style={styles.profileCard}>
          <View style={styles.avatar}>
            <Ionicons name="person" size={32} color={colors.primary} />
          </View>
          <View>
            <Text style={styles.name}>Student</Text>
            <Text style={styles.email}>signed in via email</Text>
          </View>
        </GlassCard>

        <Text style={styles.sectionTitle}>Stats</Text>
        <GlassCard style={styles.statsRow}>
          {loading ? (
            <View style={styles.stat}>
              <ActivityIndicator size="small" color={colors.primary} />
            </View>
          ) : (
            <>
              <View style={styles.stat}>
                <Text style={styles.statValue}>{stats?.completedSessions ?? 0}</Text>
                <Text style={styles.statLabel}>Completed</Text>
              </View>
              <View style={styles.divider} />
              <View style={styles.stat}>
                <Text style={styles.statValue}>{stats?.totalSessions ?? 0}</Text>
                <Text style={styles.statLabel}>Total Sessions</Text>
              </View>
            </>
          )}
        </GlassCard>

        {stats && stats.topTopics.length > 0 && (
          <>
            <Text style={styles.sectionTitle}>Top Topics</Text>
            <GlassCard style={styles.topicsCard}>
              {stats.topTopics.map(([topic, count], i) => (
                <View key={topic} style={[styles.topicRow, i > 0 && styles.topicBorder]}>
                  <Text style={styles.topicName}>{topic}</Text>
                  <Text style={styles.topicCount}>{count}x</Text>
                </View>
              ))}
            </GlassCard>
          </>
        )}

        <Text style={styles.sectionTitle}>Settings</Text>
        <GlassCard style={styles.settingsCard}>
          <View style={styles.settingRow}>
            <Ionicons name="notifications-outline" size={20} color={colors.textSecondary} />
            <Text style={styles.settingText}>Notifications</Text>
          </View>
          <View style={styles.settingDivider} />
          <View style={styles.settingRow}>
            <Ionicons name="moon-outline" size={20} color={colors.textSecondary} />
            <Text style={styles.settingText}>Dark Mode (Always On)</Text>
          </View>
        </GlassCard>

        <AnimatedButton
          title="Sign Out"
          variant="secondary"
          onPress={handleLogout}
          style={styles.logoutButton}
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
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.lg,
  },
  profileCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginBottom: spacing.lg,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.surfaceLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
  },
  email: {
    fontSize: 14,
    color: colors.textSecondary,
    marginTop: 2,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.text,
    marginBottom: spacing.md,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  stat: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.text,
  },
  statLabel: {
    fontSize: 12,
    color: colors.textTertiary,
    marginTop: 4,
  },
  divider: {
    width: 1,
    height: 40,
    backgroundColor: colors.border,
  },
  topicsCard: {
    marginBottom: spacing.lg,
    padding: spacing.md,
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
  settingsCard: {
    marginBottom: spacing.xl,
  },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  settingText: {
    fontSize: 16,
    color: colors.textSecondary,
  },
  settingDivider: {
    height: 1,
    backgroundColor: colors.border,
  },
  logoutButton: {
    marginTop: spacing.lg,
  },
});
