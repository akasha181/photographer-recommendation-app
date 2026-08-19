import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useState } from 'react';
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { recommendationsApi } from '../../../api/services/photographers.api';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { useCurrentUser } from '../../../store/authStore';
import type { Category, PhotographerSummary } from '../../../types/models';
import { colors, radius, spacing, typography } from '../../../theme';
import { useChatUnreadTotal } from '../../chat/hooks/useChat';
import { NotificationBell } from '../../notifications/components/NotificationBell';
import { PhotographerCard } from '../components/PhotographerCard';
import {
  useCategories,
  useFeaturedPhotographers,
  useRecommendations,
  useTrendingPhotographers,
} from '../hooks/usePhotographers';

interface Props {
  onOpenPhotographer: (id: number) => void;
  onOpenCategory: (slug: string) => void;
  onOpenSearch: () => void;
  /**
   * Notifications and Messages live in this header rather than in bottom tabs.
   *
   * Six bottom tabs is past the point where labels truncate on a small Android
   * device (the same reason selling sits inside Profile), and both of these are
   * glanceable badges rather than destinations people navigate to repeatedly.
   */
  onOpenNotifications?: () => void;
  onOpenMessages?: () => void;
}

export function HomeScreen({
  onOpenPhotographer,
  onOpenCategory,
  onOpenSearch,
  onOpenNotifications,
  onOpenMessages,
}: Props) {
  const user = useCurrentUser();
  const [refreshing, setRefreshing] = useState(false);
  const chatUnread = useChatUnreadTotal();

  const recommendations = useRecommendations({ limit: 50 });
  const categories = useCategories();
  const trending = useTrendingPhotographers(user?.city);
  const featured = useFeaturedPhotographers();

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([
      recommendations.refetch(),
      trending.refetch(),
      featured.refetch(),
    ]);
    setRefreshing(false);
  }, [recommendations, trending, featured]);

  const openPhotographer = useCallback(
    (id: number, fromRecommendation: boolean) => {
      // Close the feedback loop before navigating. Fire-and-forget — the
      // click is analytics, and it must never delay the screen transition.
      if (fromRecommendation) recommendationsApi.click(id);
      onOpenPhotographer(id);
    },
    [onOpenPhotographer],
  );

  if (recommendations.isLoading && !recommendations.data) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <LoadingState label="Finding photographers for you…" />
      </SafeAreaView>
    );
  }

  if (recommendations.isError && !recommendations.data) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ErrorState
          message={(recommendations.error as Error)?.message}
          onRetry={() => recommendations.refetch()}
        />
      </SafeAreaView>
    );
  }

  const feed = recommendations.data;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.gold}
          />
        }
      >
        {/* ─── Header ──────────────────────────────────────────────────── */}
        <View style={styles.header}>
          <View style={styles.headerText}>
            <Text style={styles.greeting}>
              {greetingFor(new Date())}, {user?.full_name?.split(' ')[0] ?? 'there'}
            </Text>
            <Text style={styles.headline}>Find your photographer</Text>
          </View>
          <View style={styles.headerActions}>
            {onOpenMessages ? (
              <NotificationBell
                onPress={onOpenMessages}
                icon="chatbubbles-outline"
                count={chatUnread.data?.unread_total ?? 0}
              />
            ) : null}
            {onOpenNotifications ? (
              <NotificationBell onPress={onOpenNotifications} />
            ) : null}
          </View>
        </View>

        {/* ─── Search entry point ──────────────────────────────────────── */}
        <Pressable onPress={onOpenSearch} style={styles.searchBar}>
          <Ionicons name="search" size={18} color={colors.dim} />
          <Text style={styles.searchPlaceholder}>
            Search by name, city or category
          </Text>
        </Pressable>

        {/* ─── Categories ──────────────────────────────────────────────── */}
        <SectionHeader title="Browse by event" />
        <FlatList
          horizontal
          data={categories.data ?? []}
          keyExtractor={(item: Category) => item.slug}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipRow}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => onOpenCategory(item.slug)}
              style={({ pressed }) => [styles.categoryChip, pressed && styles.chipPressed]}
            >
              <Text style={styles.categoryName}>{item.name}</Text>
              <Text style={styles.categoryCount}>
                {item.photographer_count} pros
              </Text>
            </Pressable>
          )}
        />

        {/* ─── AI recommendations ──────────────────────────────────────── */}
        <SectionHeader
          title={feed?.personalised ? 'Picked for you' : 'Top rated'}
          badge={feed?.personalised ? 'PERSONALISED' : undefined}
        />

        {/*
          When the engine had to widen the filters it says so. Silently
          showing near-matches as if they were exact matches is the kind of
          small dishonesty that erodes trust in the whole feature.
        */}
        {feed?.relaxed ? (
          <View style={styles.relaxedNotice}>
            <Ionicons name="information-circle-outline" size={14} color={colors.amber} />
            <Text style={styles.relaxedText}>
              No exact matches — {feed.relaxed}.
            </Text>
          </View>
        ) : null}

        <View style={styles.list}>
          {(feed?.items ?? []).map((photographer, index) => (
            <PhotographerCard
              key={`rec-${photographer.id}-${index}`}
              photographer={photographer}
              showReason
              onPress={() => openPhotographer(photographer.id, true)}
            />
          ))}
        </View>

        {/* ─── Trending ────────────────────────────────────────────────── */}
        {trending.data && trending.data.length > 0 ? (
          <>
            <SectionHeader
              title={user?.city ? `Trending in ${user.city}` : 'Trending now'}
            />
            <FlatList
              horizontal
              data={trending.data}
              keyExtractor={(item: PhotographerSummary, index: number) => `trend-${item.id}-${index}`}
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.chipRow}
              renderItem={({ item }) => (
                <MiniCard
                  photographer={item}
                  onPress={() => openPhotographer(item.id, false)}
                />
              )}
            />
          </>
        ) : null}

        {/* ─── Featured ────────────────────────────────────────────────── */}
        {featured.data && featured.data.length > 0 ? (
          <>
            <SectionHeader title="Featured photographers" />
            <View style={styles.list}>
              {featured.data.slice(0, 5).map((photographer, index) => (
                <PhotographerCard
                  key={`feat-${photographer.id}-${index}`}
                  photographer={photographer}
                  onPress={() => openPhotographer(photographer.id, false)}
                />
              ))}
            </View>
          </>
        ) : null}

        {/* Engine transparency — genuinely useful during the FYP demo. */}
        {feed ? (
          <Text style={styles.engineNote}>
            Ranked by {feed.strategy.toLowerCase()} strategy
            {feed.modelMode !== 'none' ? ` · model: ${feed.modelMode}` : ''}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function greetingFor(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

function SectionHeader({ title, badge }: { title: string; badge?: string }) {
  return (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {badge ? (
        <View style={styles.badge}>
          <Ionicons name="sparkles" size={9} color={colors.bg} />
          <Text style={styles.badgeText}>{badge}</Text>
        </View>
      ) : null}
    </View>
  );
}

function MiniCard({
  photographer,
  onPress,
}: {
  photographer: PhotographerSummary;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.miniCard, pressed && styles.chipPressed]}
    >
      <Text style={styles.miniName} numberOfLines={1}>
        {photographer.display_name}
      </Text>
      <Text style={styles.miniMeta} numberOfLines={1}>
        {photographer.city}
      </Text>
      <View style={styles.miniFooter}>
        <Ionicons name="star" size={11} color={colors.gold} />
        <Text style={styles.miniRating}>
          {parseFloat(photographer.avg_rating).toFixed(1)}
        </Text>
        <Text style={styles.miniBookings}>
          · {photographer.completed_bookings} shoots
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: { paddingBottom: spacing.huge },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
    paddingBottom: spacing.lg,
  },
  headerActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  headerText: { gap: 2, flex: 1 },
  greeting: { ...typography.caption, color: colors.sub },
  headline: { ...typography.h1, color: colors.text },
  searchBar: {
    marginHorizontal: spacing.xl,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    minHeight: 46,
  },
  searchPlaceholder: { ...typography.body, color: colors.dim },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
    marginTop: spacing.xxl,
    marginBottom: spacing.md,
  },
  sectionTitle: { ...typography.h3, color: colors.text },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: colors.gold,
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: radius.sm,
  },
  badgeText: {
    fontSize: 8,
    fontWeight: '800',
    color: colors.bg,
    letterSpacing: 0.4,
  },
  chipRow: { paddingHorizontal: spacing.xl, gap: spacing.md },
  categoryChip: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    minWidth: 104,
  },
  chipPressed: { backgroundColor: colors.cardHover, borderColor: colors.gold },
  categoryName: { ...typography.bodyBold, color: colors.text },
  categoryCount: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  list: { paddingHorizontal: spacing.xl },
  relaxedNotice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.xl,
    marginBottom: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
  },
  relaxedText: { ...typography.tiny, color: colors.amber, flex: 1 },
  miniCard: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    width: 158,
    gap: 3,
  },
  miniName: { ...typography.bodyBold, color: colors.text, fontSize: 14 },
  miniMeta: { ...typography.tiny, color: colors.sub },
  miniFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    marginTop: spacing.sm,
  },
  miniRating: { ...typography.tiny, color: colors.text, fontWeight: '700' },
  miniBookings: { ...typography.tiny, color: colors.sub },
  engineNote: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
    marginTop: spacing.xxl,
  },
});
