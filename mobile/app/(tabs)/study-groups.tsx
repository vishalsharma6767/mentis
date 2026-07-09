import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import { api } from '../../src/lib/api';

export default function StudyGroupsScreen() {
  const router = useRouter();
  const [groups, setGroups] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadGroups();
  }, []);

  async function loadGroups() {
    setLoading(true);
    try {
      const data = await api.getStudyGroups();
      setGroups(data.groups ?? []);
    } catch {
      setGroups([]);
    } finally {
      setLoading(false);
    }
  }

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

        {loading ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.loadingText}>Loading groups...</Text>
          </View>
        ) : groups.length === 0 ? (
          <View style={styles.emptyRow}>
            <Ionicons name="people-outline" size={48} color={colors.textTertiary} />
            <Text style={styles.emptyText}>No study groups yet. Create one to get started!</Text>
          </View>
        ) : (
          <View style={styles.groupsList}>
            {groups.map((group) => (
              <TouchableOpacity key={group.$id} style={styles.groupCard}>
                <GlassCard style={styles.groupInner}>
                  <View style={styles.groupHeader}>
                    <View style={[styles.groupIcon, { backgroundColor: colors.primary + '20' }]}>
                      <Ionicons name="people" size={24} color={colors.primary} />
                    </View>
                    <View style={styles.groupInfo}>
                      <Text style={styles.groupName}>{group.name}</Text>
                      <Text style={styles.groupMeta}>{group.members ?? 0} members · {group.active ?? 0} active</Text>
                    </View>
                  </View>

                  <View style={styles.groupDetails}>
                    {group.nextSession ? (
                      <View style={styles.detailRow}>
                        <Ionicons name="time-outline" size={16} color={colors.textTertiary} />
                        <Text style={styles.detailText}>{group.nextSession}</Text>
                      </View>
                    ) : null}
                    <View style={styles.detailRow}>
                      <Ionicons name="book-outline" size={16} color={colors.textTertiary} />
                      <Text style={styles.detailText}>{group.subject}</Text>
                    </View>
                  </View>

                  <TouchableOpacity style={[styles.joinGroupButton, { borderColor: colors.primary }]}>
                    <Text style={[styles.joinGroupText, { color: colors.primary }]}>Join Group</Text>
                  </TouchableOpacity>
                </GlassCard>
              </TouchableOpacity>
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
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { fontSize: 28, fontWeight: '700', color: colors.text },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 4 },
  createButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.xl },
  loadingText: { color: colors.textSecondary, fontSize: 14 },
  emptyRow: { alignItems: 'center', paddingVertical: spacing.xl, gap: spacing.md },
  emptyText: { color: colors.textTertiary, fontSize: 14, textAlign: 'center' },
  groupsList: { gap: spacing.md },
  groupCard: { gap: spacing.sm },
  groupInner: { padding: spacing.md, gap: spacing.md },
  groupHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  groupIcon: { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  groupInfo: { flex: 1 },
  groupName: { fontSize: 16, fontWeight: '700', color: colors.text },
  groupMeta: { fontSize: 13, color: colors.textSecondary, marginTop: 2 },
  groupDetails: { flexDirection: 'row', gap: spacing.md },
  detailRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  detailText: { fontSize: 13, color: colors.textTertiary, fontWeight: '500' },
  joinGroupButton: { marginTop: spacing.sm, paddingVertical: spacing.sm, borderRadius: borderRadius.sm, borderWidth: 1, alignItems: 'center' },
  joinGroupText: { fontSize: 14, fontWeight: '700' },
});
