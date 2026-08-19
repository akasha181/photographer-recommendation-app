import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import React from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { Button } from '../../../components/ui/Button';
import { Stars } from '../../../components/ui/Stars';
import type { Service } from '../../../types/models';
import { formatPKR, formatRating, timeAgo } from '../../../utils/format';
import { colors, radius, spacing, typography } from '../../../theme';
import { usePhotographerDetail } from '../../explore/hooks/usePhotographers';

interface Props {
  photographerId: number;
  onBack: () => void;
  onBook: (serviceId: number) => void;
  /** Module 9 — the full, filterable review list with the distribution. */
  onOpenReviews?: (name: string) => void;
  onMessage?: (userId: number, name: string) => void;
}

export function PhotographerDetailScreen({
  photographerId,
  onBack,
  onBook,
  onOpenReviews,
  onMessage,
}: Props) {
  const { width } = useWindowDimensions();
  const { data, isLoading, isError, error, refetch } =
    usePhotographerDetail(photographerId);

  if (isLoading) return <Shell onBack={onBack}><LoadingState /></Shell>;
  if (isError || !data) {
    return (
      <Shell onBack={onBack}>
        <ErrorState message={(error as Error)?.message} onRetry={refetch} />
      </Shell>
    );
  }

  const breakdown = data.rating_breakdown ?? {};
  const totalRatings = Object.values(breakdown).reduce((a, b) => a + b, 0);
  const thumbSize = (width - spacing.xl * 2 - spacing.sm * 2) / 3;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        {/* ─── Header ──────────────────────────────────────────────────── */}
        <View style={styles.topBar}>
          <Pressable onPress={onBack} hitSlop={10} style={styles.backButton}>
            <Ionicons name="chevron-back" size={22} color={colors.text} />
          </Pressable>
          {onMessage ? (
            <Pressable
              onPress={() => onMessage(data.user_id, data.display_name)}
              hitSlop={10}
              style={styles.backButton}
              accessibilityRole="button"
              accessibilityLabel={`Message ${data.display_name}`}
            >
              <Ionicons name="chatbubble-outline" size={20} color={colors.text} />
            </Pressable>
          ) : null}
        </View>

        <View style={styles.identity}>
          <Avatar
            name={data.display_name}
            uri={data.avatar_url}
            size={78}
            verified={data.is_verified}
          />
          <Text style={styles.name}>{data.display_name}</Text>
          <Text style={styles.tagline}>{data.tagline}</Text>

          <View style={styles.ratingRow}>
            <Stars rating={data.avg_rating} count={data.reviews_count} size={15} />
          </View>

          <View style={styles.pillRow}>
            <Pill icon="location-outline" label={data.city} />
            <Pill icon="briefcase-outline" label={`${data.years_experience}y exp`} />
            <Pill icon="camera-outline" label={`${data.completed_bookings} shoots`} />
          </View>

          <View style={styles.responseRow}>
            <Ionicons name="flash-outline" size={13} color={colors.green} />
            <Text style={styles.responseText}>{data.response_time_label}</Text>
          </View>
        </View>

        {/* ─── Bio ─────────────────────────────────────────────────────── */}
        {data.bio ? (
          <Section title="About">
            <Text style={styles.bio}>{data.bio}</Text>
          </Section>
        ) : null}

        {/* ─── Portfolio ───────────────────────────────────────────────── */}
        {data.portfolio && data.portfolio.length > 0 ? (
          <Section title="Portfolio">
            <View style={styles.grid}>
              {data.portfolio.slice(0, 9).map((image) => (
                <Image
                  key={image.id}
                  source={{ uri: image.thumbnail_url ?? image.image_url ?? '' }}
                  style={[styles.thumb, { width: thumbSize, height: thumbSize }]}
                  contentFit="cover"
                  transition={200}
                />
              ))}
            </View>
          </Section>
        ) : (
          <Section title="Portfolio">
            <View style={styles.emptyPortfolio}>
              <Ionicons name="images-outline" size={22} color={colors.dim} />
              <Text style={styles.emptyPortfolioText}>
                This photographer hasn't uploaded portfolio images yet.
              </Text>
            </View>
          </Section>
        )}

        {/* ─── Services ────────────────────────────────────────────────── */}
        <Section title={`Services (${data.services?.length ?? 0})`}>
          {(data.services ?? []).map((service) => (
            <ServiceCard
              key={service.id}
              service={service}
              onBook={() => onBook(service.id)}
            />
          ))}
        </Section>

        {/* ─── Ratings breakdown ───────────────────────────────────────── */}
        {totalRatings > 0 ? (
          <Section title="Ratings">
            <View style={styles.breakdownCard}>
              <View style={styles.breakdownScore}>
                <Text style={styles.bigRating}>{formatRating(data.avg_rating)}</Text>
                <Stars rating={data.avg_rating} showNumber={false} size={12} />
                <Text style={styles.breakdownCount}>
                  {data.reviews_count} reviews
                </Text>
              </View>

              <View style={styles.breakdownBars}>
                {(['5', '4', '3', '2', '1'] as const).map((star) => {
                  const count = breakdown[star] ?? 0;
                  const pct = totalRatings ? (count / totalRatings) * 100 : 0;
                  return (
                    <View key={star} style={styles.barRow}>
                      <Text style={styles.barLabel}>{star}</Text>
                      <View style={styles.barTrack}>
                        <View style={[styles.barFill, { width: `${pct}%` }]} />
                      </View>
                      <Text style={styles.barCount}>{count}</Text>
                    </View>
                  );
                })}
              </View>
            </View>
          </Section>
        ) : null}

        {/* ─── Reviews ─────────────────────────────────────────────────── */}
        {data.recent_reviews && data.recent_reviews.length > 0 ? (
          <Section title="Recent reviews">
            {data.recent_reviews.map((review) => (
              <View key={review.id} style={styles.review}>
                <View style={styles.reviewHeader}>
                  <Avatar name={review.buyer_name} uri={review.buyer_avatar} size={32} />
                  <View style={styles.reviewMeta}>
                    <Text style={styles.reviewer}>{review.buyer_name}</Text>
                    <Text style={styles.reviewDate}>{timeAgo(review.created_at)}</Text>
                  </View>
                  <Stars rating={review.rating} showNumber={false} size={11} />
                </View>

                {review.title ? (
                  <Text style={styles.reviewTitle}>{review.title}</Text>
                ) : null}
                <Text style={styles.reviewBody}>{review.comment}</Text>

                {review.reply ? (
                  <View style={styles.reply}>
                    <Text style={styles.replyLabel}>
                      Reply from {data.display_name}
                    </Text>
                    <Text style={styles.replyBody}>{review.reply.comment}</Text>
                  </View>
                ) : null}
              </View>
            ))}

            {onOpenReviews && data.reviews_count > 0 ? (
              <Pressable
                onPress={() => onOpenReviews(data.display_name)}
                style={styles.seeAll}
                accessibilityRole="button"
              >
                <Text style={styles.seeAllText}>
                  See all {data.reviews_count} reviews
                </Text>
                <Ionicons name="chevron-forward" size={15} color={colors.gold} />
              </Pressable>
            ) : null}
          </Section>
        ) : null}

        <View style={styles.bottomSpace} />
      </ScrollView>

      {/* ─── Sticky booking bar ──────────────────────────────────────────── */}
      <View style={styles.bookingBar}>
        <View>
          <Text style={styles.bookingLabel}>Starting from</Text>
          <Text style={styles.bookingPrice}>{formatPKR(data.base_price)}</Text>
        </View>
        <View style={styles.bookingAction}>
          <Button
            label={data.is_accepting_bookings ? 'Book now' : 'Not available'}
            disabled={!data.is_accepting_bookings}
            onPress={() => onBook(data.services?.[0]?.id ?? 0)}
            size="lg"
          />
        </View>
      </View>
    </SafeAreaView>
  );
}

function Shell({ children, onBack }: { children: React.ReactNode; onBack: () => void }) {
  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.topBar}>
        <Pressable onPress={onBack} hitSlop={10} style={styles.backButton}>
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </Pressable>
      </View>
      {children}
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Pill({
  icon,
  label,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
}) {
  return (
    <View style={styles.pill}>
      <Ionicons name={icon} size={12} color={colors.sub} />
      <Text style={styles.pillText}>{label}</Text>
    </View>
  );
}

function ServiceCard({ service, onBook }: { service: Service; onBook: () => void }) {
  return (
    <View style={styles.serviceCard}>
      <View style={styles.serviceHeader}>
        <Text style={styles.serviceTitle}>{service.title}</Text>
        <Text style={styles.servicePrice}>{formatPKR(service.price)}</Text>
      </View>

      <Text style={styles.serviceDesc} numberOfLines={3}>
        {service.description}
      </Text>

      <View style={styles.serviceMeta}>
        <Pill icon="time-outline" label={`${service.duration_hours}h`} />
        <Pill icon="image-outline" label={`${service.edited_photos_count} photos`} />
        <Pill icon="calendar-outline" label={`${service.delivery_days}d delivery`} />
      </View>

      {service.includes && service.includes.length > 0 ? (
        <View style={styles.includes}>
          {service.includes.slice(0, 4).map((item, index) => (
            <View key={index} style={styles.includeRow}>
              <Ionicons name="checkmark" size={12} color={colors.green} />
              <Text style={styles.includeText}>{item}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <Button label="Book this package" onPress={onBook} variant="secondary" size="sm" />
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { paddingBottom: spacing.huge },
  topBar: { paddingHorizontal: spacing.lg, paddingTop: spacing.sm },
  backButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  identity: { alignItems: 'center', paddingHorizontal: spacing.xl, gap: spacing.sm },
  name: { ...typography.h1, color: colors.text, marginTop: spacing.md },
  tagline: { ...typography.caption, color: colors.sub, textAlign: 'center' },
  ratingRow: { marginTop: spacing.sm },
  pillRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.card,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 5,
  },
  pillText: { ...typography.tiny, color: colors.sub },
  responseRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginTop: spacing.sm,
  },
  responseText: { ...typography.tiny, color: colors.green, fontWeight: '600' },
  section: { paddingHorizontal: spacing.xl, marginTop: spacing.xxl },
  sectionTitle: { ...typography.h3, color: colors.text, marginBottom: spacing.md },
  bio: { ...typography.body, color: colors.sub, lineHeight: 22 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  thumb: { borderRadius: radius.sm, backgroundColor: colors.card },
  emptyPortfolio: {
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: spacing.xxl,
  },
  emptyPortfolioText: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
  },
  serviceCard: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    gap: spacing.md,
  },
  serviceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.md,
  },
  serviceTitle: { ...typography.bodyBold, color: colors.text, flex: 1 },
  servicePrice: { ...typography.bodyBold, color: colors.gold },
  serviceDesc: { ...typography.caption, color: colors.sub, lineHeight: 19 },
  serviceMeta: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  includes: { gap: 5 },
  includeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  includeText: { ...typography.tiny, color: colors.sub },
  breakdownCard: {
    flexDirection: 'row',
    gap: spacing.xl,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  breakdownScore: { alignItems: 'center', gap: 4, minWidth: 82 },
  bigRating: { ...typography.display, color: colors.text },
  breakdownCount: { ...typography.tiny, color: colors.sub },
  breakdownBars: { flex: 1, justifyContent: 'center', gap: 5 },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  barLabel: { ...typography.tiny, color: colors.sub, width: 8 },
  barTrack: {
    flex: 1,
    height: 5,
    borderRadius: 3,
    backgroundColor: colors.border,
    overflow: 'hidden',
  },
  barFill: { height: '100%', backgroundColor: colors.gold, borderRadius: 3 },
  barCount: { ...typography.tiny, color: colors.sub, width: 30, textAlign: 'right' },
  review: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: spacing.lg,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  reviewHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  reviewMeta: { flex: 1 },
  reviewer: { ...typography.caption, color: colors.text, fontWeight: '700' },
  reviewDate: { ...typography.tiny, color: colors.dim },
  reviewTitle: { ...typography.caption, color: colors.text, fontWeight: '700' },
  reviewBody: { ...typography.caption, color: colors.sub, lineHeight: 19 },
  reply: {
    backgroundColor: colors.surface,
    borderLeftWidth: 2,
    borderLeftColor: colors.gold,
    borderRadius: radius.sm,
    padding: spacing.md,
    gap: 3,
  },
  replyLabel: { ...typography.tiny, color: colors.gold, fontWeight: '700' },
  replyBody: { ...typography.tiny, color: colors.sub, lineHeight: 17 },
  bottomSpace: { height: spacing.huge },
  seeAll: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.md,
  },
  seeAllText: { ...typography.caption, color: colors.gold },
  bookingBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.lg,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  bookingLabel: { ...typography.tiny, color: colors.sub },
  bookingPrice: { ...typography.h3, color: colors.gold },
  bookingAction: { flex: 1, maxWidth: 190 },
});
