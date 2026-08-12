import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Avatar } from '../../../components/ui/Avatar';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate, formatPKR } from '../../../utils/format';
import type { BookingSummary } from '../../../types/models';
import { StatusPill } from './StatusPill';

/**
 * One row in the Bookings list.
 *
 * `perspective` decides which party is drawn. The payload carries both sides
 * so the buyer's tab and the photographer's Requests tab share this component
 * — the alternative is two nearly-identical cards that drift apart.
 */
export function BookingCard({
  booking,
  perspective,
  onPress,
}: {
  booking: BookingSummary;
  perspective: 'buyer' | 'photographer';
  onPress: () => void;
}) {
  const other = perspective === 'buyer' ? booking.photographer : booking.buyer;
  const timing = countdownLabel(booking);

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`Booking ${booking.reference}, ${booking.status_label}`}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.header}>
        <StatusPill status={booking.status} label={booking.status_label} size="sm" />
        <Text style={styles.reference}>{booking.reference}</Text>
      </View>

      <View style={styles.body}>
        <Avatar uri={other.avatar_url} name={other.name} size={44} />

        <View style={styles.details}>
          <Text style={styles.name} numberOfLines={1}>
            {other.name}
          </Text>
          <Text style={styles.service} numberOfLines={1}>
            {booking.service_title}
          </Text>

          <View style={styles.metaRow}>
            <Ionicons name="calendar-outline" size={13} color={colors.sub} />
            <Text style={styles.meta}>
              {formatDate(booking.event_date)} · {shortTime(booking.start_time)}
            </Text>
          </View>

          <View style={styles.metaRow}>
            <Ionicons name="location-outline" size={13} color={colors.sub} />
            <Text style={styles.meta} numberOfLines={1}>
              {booking.location_city}
            </Text>
          </View>
        </View>

        <View style={styles.right}>
          <Text style={styles.price}>{formatPKR(booking.total_price)}</Text>
          {timing ? <Text style={[styles.timing, timing.style]}>{timing.text}</Text> : null}
        </View>
      </View>

      {booking.is_reviewable ? (
        <View style={styles.footer}>
          <Ionicons name="star-outline" size={13} color={colors.gold} />
          <Text style={styles.footerText}>Leave a review</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

/** "14:00" from "14:00:00" — seconds are noise on a card. */
function shortTime(value: string): string {
  return value?.slice(0, 5) ?? '';
}

/**
 * The one line that tells a user whether they need to do something.
 *
 * A pending request that expires tomorrow is the most urgent thing on this
 * screen, and a date alone does not communicate that.
 */
function countdownLabel(
  booking: BookingSummary,
): { text: string; style: object } | null {
  const { status, days_until_event: days } = booking;

  if (status === 'PENDING') {
    return { text: 'Awaiting reply', style: styles.timingWarn };
  }
  if (status === 'ACCEPTED') {
    if (days < 0) return { text: 'Shoot done', style: styles.timingMuted };
    if (days === 0) return { text: 'Today', style: styles.timingGood };
    if (days === 1) return { text: 'Tomorrow', style: styles.timingGood };
    return { text: `in ${days} days`, style: styles.timingGood };
  }
  return null;
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
  pressed: { opacity: 0.8, backgroundColor: colors.cardHover },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  reference: { ...typography.tiny, color: colors.dim },
  body: { flexDirection: 'row', gap: spacing.md },
  details: { flex: 1, gap: 2 },
  name: { ...typography.bodyBold, color: colors.text },
  service: { ...typography.caption, color: colors.sub, marginBottom: spacing.xs },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs + 2 },
  meta: { ...typography.caption, color: colors.sub, flexShrink: 1 },
  right: { alignItems: 'flex-end', justifyContent: 'space-between' },
  price: { ...typography.bodyBold, color: colors.gold },
  timing: { ...typography.tiny, marginTop: spacing.sm },
  timingGood: { color: colors.green },
  timingWarn: { color: colors.amber },
  timingMuted: { color: colors.dim },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs + 2,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  footerText: { ...typography.caption, color: colors.gold, fontWeight: '600' },
});
