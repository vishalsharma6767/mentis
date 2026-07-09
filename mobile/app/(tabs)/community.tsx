import { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius } from '../../src/theme';
import { GlassCard } from '../../src/components';

const discussions = [
  {
    id: '1',
    author: 'Sarah Chen',
    avatar: 'S',
    title: 'Best approach for calculus derivatives?',
    replies: 12,
    likes: 34,
    time: '2h ago',
    tag: 'Math',
  },
  {
    id: '2',
    author: 'Alex Kumar',
    avatar: 'A',
    title: 'Python recursion help needed',
    replies: 8,
    likes: 21,
    time: '4h ago',
    tag: 'Coding',
  },
  {
    id: '3',
    author: 'Emma Wilson',
    avatar: 'E',
    title: 'Physics lab report tips',
    replies: 15,
    likes: 45,
    time: '6h ago',
    tag: 'Science',
  },
];

export default function CommunityScreen() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');

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

        <View style={styles.discussions}>
          {discussions.map((discussion) => (
            <TouchableOpacity key={discussion.id} style={styles.discussionCard}>
              <GlassCard style={styles.discussionInner}>
                <View style={styles.discussionHeader}>
                  <View style={styles.avatar}>
                    <Text style={styles.avatarText}>{discussion.avatar}</Text>
                  </View>
                  <View style={styles.discussionMeta}>
                    <Text style={styles.authorName}>{discussion.author}</Text>
                    <Text style={styles.timeText}>{discussion.time}</Text>
                  </View>
                  <View style={[styles.tagBadge, { backgroundColor: colors.primary + '20' }]}>
                    <Text style={[styles.tagBadgeText, { color: colors.primary }]}>{discussion.tag}</Text>
                  </View>
                </View>
                <Text style={styles.discussionTitle} numberOfLines={2}>{discussion.title}</Text>
                <View style={styles.discussionFooter}>
                  <View style={styles.footerItem}>
                    <Ionicons name="chatbubble-outline" size={16} color={colors.textTertiary} />
                    <Text style={styles.footerText}>{discussion.replies}</Text>
                  </View>
                  <View style={styles.footerItem}>
                    <Ionicons name="heart-outline" size={16} color={colors.textTertiary} />
                    <Text style={styles.footerText}>{discussion.likes}</Text>
                  </View>
                  <TouchableOpacity style={styles.joinButton}>
                    <Text style={styles.joinButtonText}>Join</Text>
                  </TouchableOpacity>
                </View>
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
  postButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchRow: {
    gap: spacing.sm,
  },
  searchInput: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.bgSecondary,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  searchText: {
    flex: 1,
    color: colors.text,
    fontSize: 15,
  },
  trendingRow: {
    gap: spacing.sm,
  },
  trendingTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  trendingTags: {
    gap: spacing.sm,
    paddingRight: spacing.lg,
  },
  tag: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.full,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tagText: {
    color: colors.textSecondary,
    fontSize: 13,
    fontWeight: '600',
  },
  discussions: {
    gap: spacing.md,
  },
  discussionCard: {
    gap: spacing.sm,
  },
  discussionInner: {
    padding: spacing.md,
    gap: spacing.sm,
  },
  discussionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surfaceLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    color: colors.primary,
    fontSize: 14,
    fontWeight: '700',
  },
  discussionMeta: {
    flex: 1,
  },
  authorName: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.text,
  },
  timeText: {
    fontSize: 12,
    color: colors.textTertiary,
    marginTop: 2,
  },
  tagBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: borderRadius.sm,
  },
  tagBadgeText: {
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  discussionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.text,
    lineHeight: 22,
  },
  discussionFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.xs,
  },
  footerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  footerText: {
    fontSize: 13,
    color: colors.textTertiary,
    fontWeight: '600',
  },
  joinButton: {
    marginLeft: 'auto',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.sm,
    backgroundColor: colors.primary + '20',
    borderWidth: 1,
    borderColor: colors.primary + '40',
  },
  joinButtonText: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: '700',
  },
});
