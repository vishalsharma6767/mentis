import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard, AnimatedButton } from '../../src/components';
import { logout, restoreSession } from '../../src/lib/auth';
import { api } from '../../src/lib/api';

export default function ProfileScreen() {
  const router = useRouter();
  const [stats, setStats] = useState<{ totalSessions: number; completedSessions: number; topTopics: [string, number][] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [streak, setStreak] = useState(0);

  useEffect(() => {
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

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <Text style={styles.title}>Profile</Text>
          <TouchableOpacity style={styles.settingsButton}>
            <Ionicons name="settings-outline" size={24} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>

        <GlassCard style={styles.profileCard}>
          <View style={styles.avatarRow}>
            <View style={styles.avatar}>
              <Ionicons name="person" size={32} color={colors.primary} />
            </View>
            <View style={styles.profileInfo}>
              <Text style={styles.name}>Student</Text>
              <Text style={styles.email}>signed in via email</Text>
            </View>
          </View>

          <View style={styles.streakRow}>
            <View style={styles.streakItem}>
              <Ionicons name="flame" size={24} color={colors.warning} />
              <Text style={styles.streakNumber}>{streak}</Text>
              <Text style={styles.streakLabel}>Day Streak</Text>
            </View>
            <View style={styles.streakDivider} />
            <View style={styles.streakItem}>
              <Ionicons name="trophy" size={24} color={colors.accent} />
              <Text style={styles.streakNumber}>{stats?.completedSessions ?? 0}</Text>
              <Text style={styles.streakLabel}>Completed</Text>
            </View>
            <View style={styles.streakDivider} />
            <View style={styles.streakItem}>
              <Ionicons name="time" size={24} color={colors.secondary} />
              <Text style={styles.streakNumber}>{stats?.totalSessions ?? 0}</Text>
              <Text style={styles.streakLabel}>Sessions</Text>
            </View>
          </View>
        </GlassCard>

        <Text style={styles.sectionTitle}>Achievements</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.achievementsRow}>
          {[
            { icon: 'flame', label: '7 Day Streak', color: colors.warning },
            { icon: 'star', label: 'First Session', color: colors.accent },
            { icon: 'school', label: 'Math Pro', color: colors.primary },
            { icon: 'code', label: 'Coder', color: colors.secondary },
          ].map((badge, i) => (
            <View key={i} style={styles.achievementCard}>
              <View style={[styles.achievementIcon, { backgroundColor: badge.color + '20' }]}>
                <Ionicons name={badge.icon as any} size={28} color={badge.color} />
              </View>
              <Text style={styles.achievementLabel}>{badge.label}</Text>
            </View>
          ))}
        </ScrollView>

        <Text style={styles.sectionTitle}>Settings</Text>
        <GlassCard style={styles.settingsCard}>
          <TouchableOpacity style={styles.settingRow}>
            <View style={styles.settingLeft}>
              <Ionicons name="notifications" size={22} color={colors.textSecondary} />
              <Text style={styles.settingText}>Notifications</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textTertiary} />
          </TouchableOpacity>
          <View style={styles.settingDivider} />
          <TouchableOpacity style={styles.settingRow}>
            <View style={styles.settingLeft}>
              <Ionicons name="moon" size={22} color={colors.textSecondary} />
              <Text style={styles.settingText}>Dark Mode</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textTertiary} />
          </TouchableOpacity>
          <View style={styles.settingDivider} />
          <TouchableOpacity style={styles.settingRow}>
            <View style={styles.settingLeft}>
              <Ionicons name="volume-high" size={22} color={colors.textSecondary} />
              <Text style={styles.settingText}>Voice Settings</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textTertiary} />
          </TouchableOpacity>
        </GlassCard>

        <AnimatedButton
          title="Sign Out"
          variant="secondary"
          onPress={async () => {
            await logout();
            router.replace('/(auth)');
          }}
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
    gap: spacing.lg,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.text,
  },
  settingsButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  profileCard: {
    padding: spacing.lg,
    gap: spacing.md,
  },
  avatarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.surfaceLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  profileInfo: {
    flex: 1,
  },
  name: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.text,
  },
  email: {
    fontSize: 14,
    color: colors.textSecondary,
    marginTop: 2,
  },
  streakRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  streakItem: {
    flex: 1,
    alignItems: 'center',
    gap: 4,
  },
  streakNumber: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.text,
  },
  streakLabel: {
    fontSize: 12,
    color: colors.textTertiary,
    fontWeight: '600',
  },
  streakDivider: {
    width: 1,
    height: 40,
    backgroundColor: colors.border,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.sm,
  },
  achievementsRow: {
    gap: spacing.md,
    paddingRight: spacing.lg,
  },
  achievementCard: {
    alignItems: 'center',
    gap: spacing.sm,
    width: 100,
  },
  achievementIcon: {
    width: 64,
    height: 64,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  achievementLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textSecondary,
    textAlign: 'center',
  },
  settingsCard: {
    padding: spacing.md,
    gap: spacing.sm,
  },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
  },
  settingLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  settingText: {
    fontSize: 15,
    color: colors.textSecondary,
  },
  settingDivider: {
    height: 1,
    backgroundColor: colors.border,
  },
  logoutButton: {
    marginTop: spacing.md,
  },
});
