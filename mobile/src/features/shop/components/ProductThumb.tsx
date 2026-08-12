import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import React, { useState } from 'react';
import { ImageStyle, StyleSheet, Text, View, ViewStyle } from 'react-native';

import { colors, radius, typography } from '../../../theme';
import { avatarColor } from '../../../utils/format';

const ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  LIGHTROOM_PRESET: 'color-filter-outline',
  PHOTOSHOP_TEMPLATE: 'layers-outline',
  ALBUM_TEMPLATE: 'book-outline',
  WEDDING_LUT: 'color-palette-outline',
  VIDEO_EFFECT: 'film-outline',
  STOCK_PHOTO: 'image-outline',
  OVERLAY: 'sparkles-outline',
};

/**
 * A product thumbnail, with a fallback that looks designed rather than broken.
 *
 * WHY THE FALLBACK IS NOT JUST A GREY ICON
 * ----------------------------------------
 * A wall of identical grey boxes reads as a failed screen, which is exactly
 * what the Shop looked like before any product had cover art. The fallback
 * derives a stable colour from the title — the same trick `Avatar` uses for
 * photographers without a photo — so each card stays visually distinct and
 * the grid still looks like a product.
 *
 * It also covers the case the seeder cannot: a real image that fails to load
 * on a bad connection. `onError` swaps to the fallback instead of leaving a
 * blank rectangle.
 */
export function ProductThumb({
  uri,
  title,
  productType,
  style,
  iconSize = 22,
  showLabel = false,
}: {
  uri: string | null;
  title: string;
  productType?: string;
  style?: ViewStyle;
  iconSize?: number;
  showLabel?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const icon = ICONS[productType ?? ''] ?? 'color-filter-outline';

  if (!uri || failed) {
    return (
      <View style={[styles.base, style, { backgroundColor: avatarColor(title) }]}>
        <Ionicons name={icon} size={iconSize} color="rgba(255,255,255,0.85)" />
        {showLabel ? (
          <Text style={styles.label} numberOfLines={1}>
            {title}
          </Text>
        ) : null}
      </View>
    );
  }

  return (
    <Image
      source={{ uri }}
      // ViewStyle and ImageStyle disagree only over `overflow: 'scroll'`,
      // which no caller passes. Every property used here (width, height,
      // borderRadius) is valid in both.
      style={[styles.base, style] as ImageStyle[]}
      contentFit="cover"
      transition={180}
      onError={() => setFailed(true)}
    />
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  label: {
    ...typography.tiny,
    color: 'rgba(255,255,255,0.9)',
    marginTop: 4,
    paddingHorizontal: 8,
    textAlign: 'center',
  },
});
