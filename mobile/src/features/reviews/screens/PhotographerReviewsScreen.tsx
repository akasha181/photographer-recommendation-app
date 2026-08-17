import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Stars } from '../../../components/ui/Stars';
import { colors, radius, spacing, typography } from '../../../theme';
import type { ReviewSort } from '../../../types/models';
import { ReviewCard } from '../components/ReviewCard';
import {
  useFlagReview,
  usePhotographerReviews,
  useReviewSummary,
  useToggleHelpful,
} from '../hooks/useReviews';

const SORTS: { key: ReviewSort; label: string }[] = [
  { key: 'helpful', label: 'Most helpful' },
  { key: 'recent', label: 'Newest' },
  { key: 'highest', label: 'Highest' },
  { key: 'lowest', label: 'Lowest' },
];

const SUB_LABELS: [string, string][] = [
  ['quality', 'Quality'],
  ['professionalism', 'Professionalism'],
  ['communication', 'Communication'],
  ['value', 'Value'],
  ['punctuality', 'Punctuality'],
];

/**
 * Every review for one photographer, with the distribution above it.
 *
 * WHY "MOST HELPFUL" IS THE DEFAULT SORT
 * -------------------------------------
 * On a profile with 300 reviews, the newest one is rarely the informative one.
 * The review other buyers voted useful is what they came to read, and putting it
 * first is the difference between a list that answers the question and a list
 * that has to be scrolled.
 *
 * WHY THE HISTOGRAM IS SHOWN, NOT JUST THE AVERAGE
 * -----------------------------------------------
 * A 4.6 built from mostly 5s with two 1s tells a very different story from a 4.6
 * built entirely from 4s and 5s. Buyers read that distribution before they read
 * the number, and the server computes it in one aggregate query.
 */
export function PhotographerReviewsScreen({
  photographerId,
  name,
  onBack,
}: {
  photographerId: number;
  name?: string;
  onBack: () => void;
}) {
  const [sort, setSort] = useState<ReviewSort>('helpful');
  const [rating, setRating] = useState<number | undefined>();
  const [photosOnly, setPhotosOnly] = useState(false);

  const summary = useReviewSummary(photographerId);
  const reviews = usePhotographerReviews(photographerId, {
    sort,
    rating,
    photos: photosOnly,
  });
  const helpful = useToggleHelpful();
  const flag = useFlagReview();

  const rows = reviews.data?.items ?? [];
  const stats = summary.data;
  const total = stats?.total_reviews ?? 0;

  const report = (reviewId: number) =>
    Alert.alert(
      'Report this review?',
      'Our team will look at it. Reporting does not hide the review — a person decides.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Report',
          style: 'destructive',
          onPress: () =>
            flag.mutate(
              { id: reviewId, reason: 'FAKE' },
              {
                onSuccess: () =>
                  Alert.alert('Reported', 'Thanks — we will take a look.'),
                onError: (error) =>
                  Alert.alert('Could not report', (error as ApiError).message),
              },
            ),
        },
      ],
    );

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <View>
          <Text style={styles.title}>Reviews</Text>
          {name ? <Text style={styles.subtitle}>{name}</Text> : null}
        </View>
      </View>

      {reviews.isLoading && !rows.length ? (
        <LoadingState label="Loading reviews…" />
      ) : reviews.isError ? (
        <ErrorState
          message={(reviews.error as ApiError)?.message}
          onRetry={() => reviews.refetch()}
        />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <ReviewCard
              review={item}
              onHelpful={() => helpful.mutate(item.id)}
              onFlag={() => report(item.id)}
            />
          )}
          ListHeaderComponent={
            <>
              {stats ? (
                <View style={styles.summaryCard}>
                  <View style={styles.summaryTop}>
                    <View style={styles.summaryScore}>
                      <Text style={styles.average}>
                        {stats.average_rating.toFixed(1)}
                      </Text>
                      <Stars rating={stats.average_rating} showNumber={false} size={13} />
                      <Text style={styles.summaryCount}>
                        {total} {total === 1 ? 'review' : 'reviews'}
                      </Text>
                    </View>

                    <View style={styles.bars}>
                      {[5, 4, 3, 2, 1].map((star) => {
                        const count = stats.breakdown[String(star) as '1'] ?? 0;
                        // Guard the divide: an empty profile would otherwise
                        // render NaN% width and collapse the whole row.
                        const share = total ? (count / total) * 100 : 0;
                        return (
                          <Pressable
                            key={star}
                            style={styles.barRow}
                            onPress={() =>
                              setRating((current) => (current === star ? undefined : star))
                            }
                          >
                            <Text
                              style={[
                                styles.barStar,
                                rating === star && styles.barStarOn,
                              ]}
                            >
                              {star}
                            </Text>
                            <View style={styles.barTrack}>
                              <View style={[styles.barFill, { width: `${share}%` }]} />
                            </View>
                            <Text style={styles.barCount}>{count}</Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>

                  {stats.recommend_percent > 0 ? (
                    <Text style={styles.recommend}>
                      {stats.recommend_percent}% of buyers rated this photographer 4★ or
                      above
                    </Text>
                  ) : null}

                  {SUB_LABELS.some(
                    ([key]) => stats.sub_ratings[key as 'quality'] != null,
                  ) ? (
                    <View style={styles.subGrid}>
                      {SUB_LABELS.map(([key, label]) => {
                        const value = stats.sub_ratings[key as 'quality'];
                        if (value == null) return null;
                        return (
                          <View key={key} style={styles.subItem}>
                            <Text style={styles.subLabel}>{label}</Text>
                            <Text style={styles.subValue}>{value.toFixed(1)}</Text>
                          </View>
                        );
                      })}
                    </View>
                  ) : null}
                </View>
              ) : null}

              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.chipRow}
              >
                {SORTS.map((option) => (
                  <Pressable
                    key={option.key}
                    onPress={() => setSort(option.key)}
                    style={[styles.chip, sort === option.key && styles.chipOn]}
                  >
                    <Text
                      style={[styles.chipText, sort === option.key && styles.chipTextOn]}
                    >
                      {option.label}
                    </Text>
                  </Pressable>
                ))}
                <Pressable
                  onPress={() => setPhotosOnly((on) => !on)}
                  style={[styles.chip, photosOnly && styles.chipOn]}
                >
                  <Text style={[styles.chipText, photosOnly && styles.chipTextOn]}>
                    With photos
                    {stats?.with_photos ? ` (${stats.with_photos})` : ''}
                  </Text>
                </Pressable>
                {rating ? (
                  <Pressable onPress={() => setRating(undefined)} style={styles.clearChip}>
                    <Ionicons name="close" size={12} color={colors.bg} />
                    <Text style={styles.chipTextOn}>{rating}★ only</Text>
                  </Pressable>
                ) : null}
              </ScrollView>
            </>
          }
          ListEmptyComponent={
            <EmptyState
              icon="star-outline"
              title={rating || photosOnly ? 'Nothing matches that filter' : 'No reviews yet'}
              detail={
                rating || photosOnly
                  ? 'Try clearing the filter.'
                  : 'Reviews appear once a shoot has been completed.'
              }
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={reviews.isRefetching}
              onRefresh={() => {
                reviews.refetch();
                summary.refetch();
              }}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
  },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl, flexGrow: 1 },
  summaryCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  summaryTop: { flexDirection: 'row', gap: spacing.xl },
  summaryScore: { alignItems: 'center', gap: 2 },
  average: { ...typography.display, color: colors.text },
  summaryCount: { ...typography.tiny, color: colors.sub },
  bars: { flex: 1, justifyContent: 'center', gap: 4 },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  barStar: { ...typography.tiny, color: colors.sub, width: 10 },
  barStarOn: { color: colors.gold },
  barTrack: {
    flex: 1,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.surface,
    overflow: 'hidden',
  },
  barFill: { height: 6, borderRadius: 3, backgroundColor: colors.gold },
  barCount: { ...typography.tiny, color: colors.dim, width: 26, textAlign: 'right' },
  recommend: {
    ...typography.caption,
    color: colors.green,
    marginTop: spacing.md,
  },
  subGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  subItem: { minWidth: 84 },
  subLabel: { ...typography.tiny, color: colors.sub },
  subValue: { ...typography.bodyBold, color: colors.text },
  chipRow: { gap: spacing.sm, paddingBottom: spacing.md },
  chip: {
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  chipOn: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { ...typography.tiny, color: colors.sub },
  chipTextOn: { ...typography.tiny, color: colors.bg },
  clearChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    borderRadius: radius.pill,
    backgroundColor: colors.goldLight,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
});
