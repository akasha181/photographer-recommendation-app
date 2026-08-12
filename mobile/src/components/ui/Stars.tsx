import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { formatCount, formatRating } from '../../utils/format';
import { colors, spacing, typography } from '../../theme';

interface Props {
  rating: string | number;
  count?: number;
  size?: number;
  showNumber?: boolean;
  compact?: boolean;
}

export function Stars({
  rating,
  count,
  size = 13,
  showNumber = true,
  compact = false,
}: Props) {
  const value = typeof rating === 'string' ? parseFloat(rating) : rating;
  const safe = Number.isNaN(value) ? 0 : value;

  // Compact mode draws one star and the number — five glyphs per row is
  // visual noise in a dense list, and the number carries the information.
  if (compact) {
    return (
      <View style={styles.row}>
        <Ionicons name="star" size={size} color={colors.gold} />
        <Text style={[styles.number, { fontSize: size }]}>{formatRating(safe)}</Text>
        {count !== undefined ? (
          <Text style={[styles.count, { fontSize: size - 1 }]}>
            ({formatCount(count)})
          </Text>
        ) : null}
      </View>
    );
  }

  return (
    <View style={styles.row}>
      {[1, 2, 3, 4, 5].map((position) => {
        const filled = safe >= position;
        const half = !filled && safe >= position - 0.5;
        return (
          <Ionicons
            key={position}
            name={filled ? 'star' : half ? 'star-half' : 'star-outline'}
            size={size}
            color={filled || half ? colors.gold : colors.dim}
          />
        );
      })}
      {showNumber ? (
        <Text style={[styles.number, { fontSize: size }]}>{formatRating(safe)}</Text>
      ) : null}
      {count !== undefined ? (
        <Text style={[styles.count, { fontSize: size - 1 }]}>
          ({formatCount(count)})
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  number: { ...typography.bodyBold, color: colors.text, marginLeft: 2 },
  count: { ...typography.caption, color: colors.sub },
});
