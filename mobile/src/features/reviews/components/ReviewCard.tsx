import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Avatar } from '../../../components/ui/Avatar';
import { Stars } from '../../../components/ui/Stars';
import { colors, radius, spacing, typography } from '../../../theme';
import { timeAgo } from '../../../utils/format';
import type { OwnedReview, Review } from '../../../types/models';

const SENTIMENT_COLOR: Record<string, string> = {
  POSITIVE: colors.green,
  NEUTRAL: colors.amber,
  NEGATIVE: colors.red,
};

const SUB_RATING_LABELS: [keyof Review['sub_ratings'], string][] = [
  ['quality', 'Quality'],
  ['professionalism', 'Professional'],
  ['communication', 'Communication'],
  ['value', 'Value'],
  ['punctuality', 'Punctuality'],
];

/**
 * One review, used by the public list, the buyer's own list and the
 * photographer's inbox.
 *
 * WHY ONE COMPONENT FOR THREE SCREENS
 * -----------------------------------
 * The three differ only in which optional slots are filled: `onHelpful` for
 * the public list, `onEdit`/`onDelete` for the author, `onReply` and the
 * sentiment chip for the recipient. Three near-identical cards would drift, and
 * a review that renders differently depending on where you found it undermines
 * the thing reviews are for.
 *
 * The sentiment chip only appears when the payload carries one, which it does
 * exclusively on the photographer's own endpoint — a machine label on somebody
 * else's words is not shown to buyers.
 */
export function ReviewCard({
  review,
  onHelpful,
  onReply,
  onEdit,
  onDelete,
  onFlag,
}: {
  review: Review | OwnedReview;
  onHelpful?: () => void;
  onReply?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
  onFlag?: () => void;
}) {
  const sentiment = (review as OwnedReview).sentiment;
  const subRatings = SUB_RATING_LABELS.filter(
    ([key]) => review.sub_ratings?.[key] != null,
  );

  return (
    <View style={styles.card}>
      <View style={styles.head}>
        <Avatar name={review.buyer_name} uri={review.buyer_avatar} size={38} />
        <View style={styles.headBody}>
          <Text style={styles.name} numberOfLines={1}>
            {review.buyer_name}
          </Text>
          <Text style={styles.meta} numberOfLines={1}>
            {review.service_name ? `${review.service_name} · ` : ''}
            {timeAgo(review.created_at)}
          </Text>
        </View>
        <Stars rating={review.rating} showNumber={false} size={12} />
      </View>

      {review.is_hidden ? (
        <View style={styles.hidden}>
          <Ionicons name="eye-off-outline" size={13} color={colors.amber} />
          <Text style={styles.hiddenText}>
            Hidden by moderation{review.hidden_reason ? ` — ${review.hidden_reason}` : ''}
          </Text>
        </View>
      ) : null}

      {review.title ? <Text style={styles.title}>{review.title}</Text> : null}
      {review.comment ? <Text style={styles.comment}>{review.comment}</Text> : null}

      {review.images?.length ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.photoStrip}
          contentContainerStyle={styles.photoRow}
        >
          {review.images.map((image) => (
            <Image
              key={image.id}
              source={{ uri: image.thumbnail_url ?? image.image_url ?? '' }}
              style={styles.photo}
              contentFit="cover"
              transition={150}
            />
          ))}
        </ScrollView>
      ) : null}

      {subRatings.length ? (
        <View style={styles.subRatings}>
          {subRatings.map(([key, label]) => (
            <View key={key} style={styles.subRating}>
              <Text style={styles.subLabel}>{label}</Text>
              <Text style={styles.subValue}>{review.sub_ratings[key]}/5</Text>
            </View>
          ))}
        </View>
      ) : null}

      {sentiment ? (
        <View style={styles.sentimentRow}>
          <View
            style={[
              styles.sentimentDot,
              { backgroundColor: SENTIMENT_COLOR[sentiment] ?? colors.dim },
            ]}
          />
          <Text style={styles.sentimentText}>
            Tone read as {sentiment.toLowerCase()}
          </Text>
        </View>
      ) : null}

      {review.reply ? (
        <View style={styles.reply}>
          <Text style={styles.replyName}>
            {review.reply.photographer_name} replied
            {review.reply.is_edited ? ' (edited)' : ''}
          </Text>
          <Text style={styles.replyText}>{review.reply.comment}</Text>
        </View>
      ) : null}

      <View style={styles.actions}>
        {onHelpful ? (
          <Pressable
            onPress={onHelpful}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Mark this review helpful"
            style={styles.action}
          >
            <Ionicons
              name={review.marked_helpful ? 'thumbs-up' : 'thumbs-up-outline'}
              size={15}
              color={review.marked_helpful ? colors.gold : colors.sub}
            />
            <Text
              style={[styles.actionText, review.marked_helpful && styles.actionTextOn]}
            >
              Helpful{review.helpful_count ? ` · ${review.helpful_count}` : ''}
            </Text>
          </Pressable>
        ) : (
          <Text style={styles.actionText}>
            {review.helpful_count
              ? `${review.helpful_count} found this helpful`
              : ''}
          </Text>
        )}

        <View style={styles.rightActions}>
          {onReply && !review.reply ? (
            <Pressable onPress={onReply} hitSlop={8} style={styles.action}>
              <Ionicons name="chatbubble-outline" size={15} color={colors.gold} />
              <Text style={[styles.actionText, styles.actionTextOn]}>Reply</Text>
            </Pressable>
          ) : null}
          {onReply && review.reply ? (
            <Pressable onPress={onReply} hitSlop={8} style={styles.action}>
              <Ionicons name="create-outline" size={15} color={colors.sub} />
              <Text style={styles.actionText}>Edit reply</Text>
            </Pressable>
          ) : null}
          {onEdit && review.can_edit ? (
            <Pressable onPress={onEdit} hitSlop={8} style={styles.action}>
              <Ionicons name="create-outline" size={15} color={colors.sub} />
              <Text style={styles.actionText}>Edit</Text>
            </Pressable>
          ) : null}
          {onDelete ? (
            <Pressable onPress={onDelete} hitSlop={8} style={styles.action}>
              <Ionicons name="trash-outline" size={15} color={colors.red} />
            </Pressable>
          ) : null}
          {onFlag ? (
            <Pressable
              onPress={onFlag}
              hitSlop={8}
              accessibilityLabel="Report this review"
              style={styles.action}
            >
              <Ionicons name="flag-outline" size={15} color={colors.dim} />
            </Pressable>
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  head: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  headBody: { flex: 1 },
  name: { ...typography.bodyBold, color: colors.text },
  meta: { ...typography.tiny, color: colors.sub, marginTop: 1 },
  hidden: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.amberDim,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    marginTop: spacing.md,
  },
  hiddenText: { ...typography.tiny, color: colors.amber, flex: 1 },
  title: { ...typography.bodyBold, color: colors.text, marginTop: spacing.md },
  comment: {
    ...typography.caption,
    color: colors.sub,
    lineHeight: 19,
    marginTop: spacing.xs,
  },
  photoStrip: { marginTop: spacing.md },
  photoRow: { gap: spacing.sm },
  photo: { width: 74, height: 74, borderRadius: radius.sm, backgroundColor: colors.surface },
  subRatings: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  subRating: {
    flexDirection: 'row',
    gap: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  subLabel: { ...typography.tiny, color: colors.sub },
  subValue: { ...typography.tiny, color: colors.text },
  sentimentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  sentimentDot: { width: 7, height: 7, borderRadius: 4 },
  sentimentText: { ...typography.tiny, color: colors.dim },
  reply: {
    marginTop: spacing.md,
    paddingLeft: spacing.md,
    borderLeftWidth: 2,
    borderLeftColor: colors.goldDim,
  },
  replyName: { ...typography.tiny, color: colors.gold },
  replyText: {
    ...typography.caption,
    color: colors.sub,
    lineHeight: 18,
    marginTop: 2,
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  rightActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  action: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  actionText: { ...typography.tiny, color: colors.sub },
  actionTextOn: { color: colors.gold },
});
