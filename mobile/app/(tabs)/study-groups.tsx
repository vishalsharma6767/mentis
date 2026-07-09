import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';

const groups = [
  {
    id: '1',
    name: 'Calculus Masters',
    members: 24,
    active: 8,
    subject: 'Math',
    color: colors.primary,
    nextSession: 'Today, 4:00 PM',
  },
  {
    id: '2',
    name: 'Python Warriors',
    members: 18,
    active: 5,
    subject: 'Coding',
    color: colors.secondary,
    nextSession: 'Tomorrow, 10:00 AM',
  },
  {
    id: '3',
    name: 'Physics Lab',
    members: 32,
    active: 12,
    subject: 'Science',
    color: colors.accent,
    nextSession: 'Wed, 3:00 PM',
  },
];

export default function StudyGroupsScreen() {
  const router = useRouter();

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>Study Groups</Text>
            <Text style={styles.subtitle}>Learn with peers</Text>
          </View>
          <TouchableOpacity style={styles.createButton}>
            <Ionicons name="add" size={24} color={colors.bg} />
          </TouchableOpacity>
        </View>

        <View style={styles.groupsList}>
          {groups.map((group) => (
            <TouchableOpacity key={group.id} style={styles.groupCard}>
              <GlassCard style={styles.groupInner}>
                <View style={styles.groupHeader}>
                  <View style={[styles.groupIcon, { backgroundColor: group.color + '20' }]}>
                    <Ionicons name="people" size={24} color={group.color} />
                  </View>
                  <View style={styles.groupInfo}>
                    <Text style={styles.groupName}>{group.name}</Text>
                    <Text style={styles.groupMeta}>{group.members} members · {group.active} active</Text>
                  </View>
                </View>

                <View style={styles.groupDetails}>
                  <View style={styles.detailRow}>
                    <Ionicons name="time-outline" size={16} color={colors.textTertiary} />
                    <Text style={styles.detailText}>{group.nextSession}</Text>
                  </View>
                  <View style={styles.detailRow}>
                    <Ionicons name="book-outline" size={16} color={colors.textTertiary} />
                    <Text style={styles.detailText}>{group.subject}</Text>
                  </View>
                </View>

                <TouchableOpacity style={[styles.joinGroupButton, { borderColor: group.color }]}>
                  <Text style={[styles.joinGroupText, { color: group.color }]}>Join Group</Text>
                </TouchableOpacity>
              </GlassCard>
            </TouchableOpacity>
          ))}
        </View>
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
  subtitle: {
    fontSize: 14,
    color: colors.textSecondary,
    marginTop: 4,
  },
  createButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  groupsList: {
    gap: spacing.md,
  },
  groupCard: {
    gap: spacing.sm,
  },
  groupInner: {
    padding: spacing.md,
    gap: spacing.md,
  },
  groupHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  groupIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  groupInfo: {
    flex: 1,
  },
  groupName: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  groupMeta: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 2,
  },
  groupDetails: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  detailText: {
    fontSize: 13,
    color: colors.textTertiary,
    fontWeight: '500',
  },
  joinGroupButton: {
    marginTop: spacing.sm,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.sm,
    borderWidth: 1,
    alignItems: 'center',
  },
  joinGroupText: {
    fontSize: 14,
    fontWeight: '700',
  },
});
