import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import React from 'react';
import {
  Alert,
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
import { Avatar } from '../../../components/ui/Avatar';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate } from '../../../utils/format';
import type { PendingBookingReview, PendingProductReview } from '../../../types/models';
import { ReviewCard } from '../components/ReviewCard';
import { useDeleteReview, useMyReviews, usePendingReviews } from '../hooks/useReviews';

/**
 * "Reviews" from the buyer's side: what they owe, then what they have written.
 *
 * WHY THE PROMPTS COME FIRST
 * --------------------------
 * A marketplace with 40 completed shoots and 3 reviews has a discovery problem,
 * and the moment a buyer is most likely to write one is when they are already
 * looking at the list. Putting their own past reviews first would bury the only
 * part of this screen that produces anything.
 *
 * The pending list is the server's `/reviews/pending/` — the same set the
 * nightly reminder task uses, so the screen and the notification can never
 * disagree about what is still owed.
 */
export function MyReviewsScreen({
  onBack,
  onWriteBookingReview,
  onWriteProductReview,
}: {
  onBack: () => void;
  onWriteBookingReview: (target: PendingBookingReview) => void;
  onWriteProductReview: (target: PendingProductReview) => void;
}) {
  const pending = usePendingReviews();
  const mine = useMyReviews();
  const remove = useDeleteReview();

  const confirmDelete = (id: number) =>
    Alert.alert(
      'Withdraw this review?',
      'It stops counting towards the photographer’s rating. You cannot post another for the same shoot.',
      [
        { text: 'Keep it', style: 'cancel' },
        {
          text: 'Withdraw',
          style: 'destructive',
          onPress: () =>
            remove.mutate(id, {
              onError: (error) =>
                Alert.alert('Could not withdraw', (error as ApiError).message),
            }),
        },
      ],
    );

  const loading = pending.isLoading || mine.isLoading;
  const failed = pending.isError && mine.isError;
  const pendingBookings = pending.data?.bookings ?? [];
  const pendingProducts = pending.data?.order_items ?? [];
  const written = mine.data ?? [];
  const nothingAtAll =
    !pendingBookings.length && !pendingProducts.length && !written.length;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <View>
          <Text style={styles.title}>Reviews</Text>
          <Text style={styles.subtitle}>What you owe, and what you have written</Text>
        </View>
      </View>

      {loading ? (
        <LoadingState label="Loading your reviews…" />
      ) : failed ? (
        <ErrorState
          message={(pending.error as ApiError)?.message}
          onRetry={() => {
            pending.refetch();
            mine.refetch();
          }}
        />
      ) : (
        <ScrollView
          contentContainerStyle={styles.body}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={pending.isRefetching || mine.isRefetching}
              onRefresh={() => {
                pending.refetch();
                mine.refetch();
              }}
              tintColor={colors.gold}
            />
          }
        >
          {nothingAtAll ? (
            <EmptyState
              icon="star-outline"
              title="No reviews yet"
              detail="Once a shoot is marked complete, you can review it here — and so can the people you buy presets from."
            />
          ) : null}

          {pendingBookings.length ? (
            <>
              <Text style={styles.section}>Waiting on you</Text>
              {pendingBookings.map((row) => (
                <Pressable
                  key={row.booking_id}
                  style={styles.prompt}
                  onPress={() => onWriteBookingReview(row)}
                  accessibilityRole="button"
                  accessibilityLabel={`Review ${row.photographer_name}`}
                >
                  <Avatar
                    name={row.photographer_name}
                    uri={row.photographer_avatar}
                    size={40}
                  />
                  <View style={styles.promptBody}>
                    <Text style={styles.promptTitle} numberOfLines={1}>
                      {row.photographer_name}
                    </Text>
                    <Text style={styles.promptMeta} numberOfLines={1}>
                      {row.service_name} · {formatDate(row.event_date)}
                    </Text>
                  </View>
                  <View style={styles.promptCta}>
                    <Ionicons name="star-outline" size={14} color={colors.gold} />
                    <Text style={styles.promptCtaText}>Rate</Text>
                  </View>
                </Pressable>
              ))}
            </>
          ) : null}

          {pendingProducts.length ? (
            <>
              <Text style={styles.section}>Products you bought</Text>
              {pendingProducts.map((row) => (
                <Pressable
                  key={row.order_item_id}
                  style={styles.prompt}
                  onPress={() => onWriteProductReview(row)}
                  accessibilityRole="button"
                  accessibilityLabel={`Review ${row.product_title}`}
                >
                  {row.thumbnail_url ? (
                    <Image
                      source={{ uri: row.thumbnail_url }}
                      style={styles.thumb}
                      contentFit="cover"
                    />
                  ) : (
                    <View style={[styles.thumb, styles.thumbEmpty]}>
                      <Ionicons name="color-palette-outline" size={18} color={colors.dim} />
                    </View>
                  )}
                  <View style={styles.promptBody}>
                    <Text style={styles.promptTitle} numberOfLines={1}>
                      {row.product_title}
                    </Text>
                    <Text style={styles.promptMeta}>
                      Bought {formatDate(row.purchased_at)}
                    </Text>
                  </View>
                  <View style={styles.promptCta}>
                    <Ionicons name="star-outline" size={14} color={colors.gold} />
                    <Text style={styles.promptCtaText}>Rate</Text>
                  </View>
                </Pressable>
              ))}
            </>
          ) : null}

          {written.length ? (
            <>
              <Text style={styles.section}>Your reviews</Text>
              {written.map((review) => (
                <ReviewCard
                  key={review.id}
                  review={review}
                  onDelete={() => confirmDelete(review.id)}
                />
              ))}
            </>
          ) : null}
        </ScrollView>
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
    paddingBottom: spacing.lg,
  },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  body: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge, flexGrow: 1 },
  section: {
    ...typography.tiny,
    color: colors.sub,
    textTransform: 'uppercase',
    marginTop: spacing.lg,
    marginBottom: spacing.md,
  },
  prompt: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  promptBody: { flex: 1 },
  promptTitle: { ...typography.bodyBold, color: colors.text },
  promptMeta: { ...typography.tiny, color: colors.sub, marginTop: 1 },
  promptCta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.goldDim,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  promptCtaText: { ...typography.tiny, color: colors.goldLight },
  thumb: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.surface },
  thumbEmpty: { alignItems: 'center', justifyContent: 'center' },
});
