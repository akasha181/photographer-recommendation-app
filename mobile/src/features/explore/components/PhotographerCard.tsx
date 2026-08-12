import { Ionicons } from '@expo/vector-icons';
import React, { memo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Avatar } from '../../../components/ui/Avatar';
import { Stars } from '../../../components/ui/Stars';
import type { PhotographerSummary, Recommendation } from '../../../types/models';
import { formatDistance, formatPKR } from '../../../utils/format';
import { colors, radius, spacing, typography } from '../../../theme';

interface Props {
  photographer: PhotographerSummary | Recommendation;
  onPress: () => void;
  /** Shows the AI reason strip when the item came from the recommender. */
  showReason?: boolean;
  /**
   * Renders a heart. Optional so Explore and Home are unchanged — only the
   * Saved screen needs a way to unsave from the list itself.
   */
  onToggleWishlist?: () => void;
}

function hasReason(p: PhotographerSummary | Recommendation): p is Recommendation {
  return 'reason' in p && Boolean((p as Recommendation).reason);
}

/**
 * The photographer card used in every list.
 *
 * memo() is not premature here: this renders 20+ times per screen inside a
 * FlatList, and without it every parent state change (a keystroke in the
 * search box) re-renders the whole visible list.
 */
export const PhotographerCard = memo(function PhotographerCard({
  photographer,
  onPress,
  showReason = false,
  onToggleWishlist,
}: Props) {
  const distance = formatDistance(photographer.distance_km);
  const category = photographer.categories?.[0]?.name;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${photographer.display_name}, ${photographer.avg_rating} stars, from ${formatPKR(photographer.base_price)}`}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.row}>
        <Avatar
          name={photographer.display_name}
          uri={photographer.avatar_url}
          size={54}
          verified={photographer.is_verified}
        />

        <View style={styles.body}>
          <View style={styles.titleRow}>
            <Text style={styles.name} numberOfLines={1}>
              {photographer.display_name}
            </Text>
            {photographer.is_featured ? (
              <View style={styles.featuredPill}>
                <Text style={styles.featuredText}>FEATURED</Text>
              </View>
            ) : null}
            {onToggleWishlist ? (
              <Pressable
                onPress={onToggleWishlist}
                hitSlop={10}
                accessibilityLabel={
                  photographer.is_wishlisted ? 'Remove from saved' : 'Save'
                }
              >
                <Ionicons
                  name={photographer.is_wishlisted ? 'heart' : 'heart-outline'}
                  size={18}
                  color={photographer.is_wishlisted ? colors.red : colors.dim}
                />
              </Pressable>
            ) : null}
          </View>

          <Text style={styles.tagline} numberOfLines={1}>
            {photographer.tagline || category || 'Photographer'}
          </Text>

          <View style={styles.metaRow}>
            <Stars
              rating={photographer.avg_rating}
              count={photographer.reviews_count}
              compact
            />
            <View style={styles.dot} />
            <Ionicons name="location-outline" size={12} color={colors.sub} />
            <Text style={styles.meta}>{photographer.city || '—'}</Text>
          </View>

          <View style={styles.metaRow}>
            <Text style={styles.price}>
              from {formatPKR(photographer.base_price)}
            </Text>
            {photographer.years_experience > 0 ? (
              <>
                <View style={styles.dot} />
                <Text style={styles.meta}>{photographer.years_experience}y exp</Text>
              </>
            ) : null}
            {distance ? (
              <>
                <View style={styles.dot} />
                <Text style={styles.meta}>{distance}</Text>
              </>
            ) : null}
          </View>
        </View>

        <Ionicons name="chevron-forward" size={18} color={colors.dim} />
      </View>

      {/*
        The explanation strip. A recommendation the user cannot understand is
        a recommendation they will not act on — see engine._reason() for how
        this sentence is composed.
      */}
      {showReason && hasReason(photographer) ? (
        <View style={styles.reasonStrip}>
          <Ionicons name="sparkles" size={11} color={colors.gold} />
          <Text style={styles.reasonText} numberOfLines={2}>
            {photographer.reason}
          </Text>
        </View>
      ) : null}
    </Pressable>
  );
});

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  pressed: { backgroundColor: colors.cardHover, borderColor: colors.borderMid },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  body: { flex: 1, gap: 3 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  name: { ...typography.bodyBold, color: colors.text, flexShrink: 1 },
  featuredPill: {
    backgroundColor: colors.goldDim,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  featuredText: {
    fontSize: 8,
    fontWeight: '800',
    color: colors.goldLight,
    letterSpacing: 0.5,
  },
  tagline: { ...typography.caption, color: colors.sub },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 5, flexWrap: 'wrap' },
  meta: { ...typography.tiny, color: colors.sub },
  price: { ...typography.tiny, color: colors.gold, fontWeight: '700' },
  dot: {
    width: 3,
    height: 3,
    borderRadius: 2,
    backgroundColor: colors.dim,
  },
  reasonStrip: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  reasonText: {
    ...typography.tiny,
    color: colors.sub,
    flex: 1,
    lineHeight: 15,
  },
});
