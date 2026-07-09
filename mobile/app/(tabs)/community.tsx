import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';
import { api } from '../../src/lib/api';
import { restoreSession } from '../../src/lib/auth';

export default function CommunityScreen() {
  const router = useRouter();
  const [discussions, setDiscussions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadDiscussions();
  }, []);

  async function loadDiscussions() {
    setLoading(true);
    try {
      const data = await api.getDiscussions();
      setDiscussions(data.discussions ?? []);
    } catch {
      setDiscussions([]);
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
            <Text style={styles.title}>Community</Text>
            <Text style={styles.subtitle}>Learn together, grow together</Text>
          </View>
          <TouchableOpacity style={styles.postButton}>
            <Ionicons name="add" size={24} color={colors.bg} />
          </TouchableOpacity>
        </View>

        <View style={styles.searchRow}>
          <View style={styles.searchInput}>
            <Ionicons name="search" size={20} color={colors.textTertiary} />
            <TextInput
              style={styles.searchText}
              placeholder="Search discussions..."
              placeholderTextColor={colors.textTertiary}
              value={searchQuery}
              onChangeText={setSearchQuery}
            />
          </View>
        </View>

        <View style={styles.trendingRow}>
          <Text style={styles.trendingTitle}>Trending</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.trendingTags}>
            {['Math', 'Science', 'Coding', 'Physics', 'Chemistry'].map((tag) => (
              <TouchableOpacity key={tag} style={styles.tag}>
                <Text style={styles.tagText}>{tag}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>

        {loading ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.loadingText}>Loading discussions...</Text>
          </View>
        ) : discussions.length === 0 ? (
          <View style={styles.emptyRow}>
            <Ionicons name="people-outline" size={48} color={colors.textTertiary} />
            <Text style={styles.emptyText}>No discussions yet. Be the first to start one!</Text>
          </View>
        ) : (
          <View style={styles.discussions}>
            {discussions.map((discussion) => (
              <TouchableOpacity key={discussion.$id} style={styles.discussionCard}>
                <GlassCard style={styles.discussionInner}>
                  <View style={styles.discussionHeader}>
                    <View style={styles.avatar}>
                      <Text style={styles.avatarText}>{(discussion.authorName || '?')[0]?.toUpperCase() ?? '?'}</Text>
                    </View>
                    <View style={styles.discussionMeta}>
                      <Text style={styles.authorName}>{discussion.authorName || 'Anonymous'}</Text>
                      <Text style={styles.timeText}>{discussion.createdAt ? new Date(discussion.createdAt).toLocaleDateString() : ''}</Text>
                    </View>
                    {discussion.tag ? (
                      <View style={[styles.tagBadge, { backgroundColor: colors.primary + '20' }]}>
                        <Text style={[styles.tagBadgeText, { color: colors.primary }]}>{discussion.tag}</Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={styles.discussionTitle} numberOfLines={2}>{discussion.title}</Text>
                  <View style={styles.discussionFooter}>
                    <View style={styles.footerItem}>
                      <Ionicons name="chatbubble-outline" size={16} color={colors.textTertiary} />
                      <Text style={styles.footerText}>{discussion.replies ?? 0}</Text>
                    </View>
                    <View style={styles.footerItem}>
                      <Ionicons name="heart-outline" size={16} color={colors.textTertiary} />
                      <Text style={styles.footerText}>{discussion.likes ?? 0}</Text>
                    </View>
                  </View>
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
  postButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  searchRow: { gap: spacing.sm },
  searchInput: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.bgSecondary, borderRadius: borderRadius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  searchText: { flex: 1, color: colors.text, fontSize: 15 },
  trendingRow: { gap: spacing.sm },
  trendingTitle: { fontSize: 16, fontWeight: '700', color: colors.text },
  trendingTags: { gap: spacing.sm, paddingRight: spacing.lg },
  tag: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: borderRadius.full, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  tagText: { color: colors.textSecondary, fontSize: 13, fontWeight: '600' },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.xl },
  loadingText: { color: colors.textSecondary, fontSize: 14 },
  emptyRow: { alignItems: 'center', paddingVertical: spacing.xl, gap: spacing.md },
  emptyText: { color: colors.textTertiary, fontSize: 14, textAlign: 'center' },
  discussions: { gap: spacing.md },
  discussionCard: { gap: spacing.sm },
  discussionInner: { padding: spacing.md, gap: spacing.sm },
  discussionHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surfaceLight, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.primary, fontSize: 14, fontWeight: '700' },
  discussionMeta: { flex: 1 },
  authorName: { fontSize: 14, fontWeight: '600', color: colors.text },
  timeText: { fontSize: 12, color: colors.textTertiary, marginTop: 2 },
  tagBadge: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: borderRadius.sm },
  tagBadgeText: { fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  discussionTitle: { fontSize: 15, fontWeight: '600', color: colors.text, lineHeight: 22 },
  discussionFooter: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginTop: spacing.xs },
  footerItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  footerText: { fontSize: 13, color: colors.textTertiary, fontWeight: '600' },
});
