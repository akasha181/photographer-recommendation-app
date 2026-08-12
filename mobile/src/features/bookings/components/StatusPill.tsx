import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { radius, spacing, statusColors, typography } from '../../../theme';
import type { BookingStatus } from '../../../types/models';

/**
 * The status badge, drawn from the shared token map.
 *
 * The same status appears on the list, the detail screen, the photographer's
 * Requests tab and (soon) notifications. Reading the colour from
 * `theme/colors.statusColors` is what stops those five places from quietly
 * disagreeing about what "Pending" looks like.
 */
export function StatusPill({
  status,
  label,
  size = 'md',
}: {
  status: BookingStatus;
  label?: string;
  size?: 'sm' | 'md';
}) {
  const tone = statusColors[status] ?? statusColors.EXPIRED;

  return (
    <View
      style={[
        styles.pill,
        size === 'sm' && styles.pillSm,
        { backgroundColor: tone.bg },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: tone.fg }]} />
      <Text style={[styles.label, size === 'sm' && styles.labelSm, { color: tone.fg }]}>
        {label ?? status}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: spacing.xs + 2,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.pill,
  },
  pillSm: { paddingHorizontal: spacing.sm, paddingVertical: 3 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: { ...typography.tiny, textTransform: 'uppercase', fontWeight: '700' },
  labelSm: { fontSize: 10 },
});
