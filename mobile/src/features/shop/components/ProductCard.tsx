import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, radius, spacing, typography } from '../../../theme';
import { formatPKR } from '../../../utils/format';
import type { DigitalProduct } from '../../../types/models';
import { ProductThumb } from './ProductThumb';

/**
 * A Shop grid card.
 *
 * The three state flags (`is_owned`, `in_cart`, `is_wishlisted`) are computed
 * server-side from sets loaded once per request, so drawing them costs
 * nothing here. Deriving "do I own this?" on the client would mean shipping
 * the buyer's whole purchase history to every screen.
 */
export function ProductCard({
  product,
  width,
  onPress,
  onToggleSave,
}: {
  product: DigitalProduct;
  width: number;
  onPress: () => void;
  onToggleSave?: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${product.title}, ${formatPKR(product.price)}`}
      style={({ pressed }) => [styles.card, { width }, pressed && styles.pressed]}
    >
      <View style={[styles.thumbWrap, { height: width * 0.72 }]}>
        <ProductThumb
          uri={product.thumbnail_url}
          title={product.title}
          productType={product.product_type}
          style={styles.thumb}
          iconSize={26}
        />

        {product.discount_percent > 0 && !product.is_owned ? (
          <View style={styles.discount}>
            <Text style={styles.discountText}>−{product.discount_percent}%</Text>
          </View>
        ) : null}

        {onToggleSave ? (
          <Pressable
            onPress={onToggleSave}
            hitSlop={10}
            accessibilityLabel={product.is_wishlisted ? 'Remove from saved' : 'Save'}
            style={styles.heart}
          >
            <Ionicons
              name={product.is_wishlisted ? 'heart' : 'heart-outline'}
              size={16}
              color={product.is_wishlisted ? colors.red : colors.text}
            />
          </Pressable>
        ) : null}

        {product.is_owned ? (
          <View style={styles.ownedBadge}>
            <Ionicons name="checkmark-circle" size={12} color={colors.green} />
            <Text style={styles.ownedText}>Owned</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.body}>
        <Text style={styles.type}>{product.type_label}</Text>
        <Text style={styles.title} numberOfLines={2}>
          {product.title}
        </Text>
        <Text style={styles.seller} numberOfLines={1}>
          {product.seller.display_name}
        </Text>

        <View style={styles.footer}>
          {product.is_owned ? (
            <Text style={styles.owned}>In your library</Text>
          ) : (
            <View style={styles.priceRow}>
              <Text style={styles.price}>{formatPKR(product.price)}</Text>
              {product.compare_at_price &&
              Number(product.compare_at_price) > Number(product.price) ? (
                <Text style={styles.was}>{formatPKR(product.compare_at_price)}</Text>
              ) : null}
            </View>
          )}
          {product.in_cart && !product.is_owned ? (
            <Ionicons name="cart" size={14} color={colors.gold} />
          ) : null}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
    marginBottom: spacing.md,
  },
  pressed: { opacity: 0.85 },
  thumbWrap: { position: 'relative', backgroundColor: colors.surface },
  thumb: { width: '100%', height: '100%', borderRadius: 0 },
  discount: {
    position: 'absolute',
    top: spacing.sm,
    left: spacing.sm,
    backgroundColor: colors.red,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  discountText: { ...typography.tiny, color: colors.white, fontWeight: '700' },
  heart: {
    position: 'absolute',
    top: spacing.sm,
    right: spacing.sm,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.overlay,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ownedBadge: {
    position: 'absolute',
    bottom: spacing.sm,
    left: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: colors.overlay,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  ownedText: { ...typography.tiny, color: colors.green, fontWeight: '600' },
  body: { padding: spacing.md, gap: 2 },
  type: { ...typography.tiny, color: colors.dim, textTransform: 'uppercase' },
  title: { ...typography.bodyBold, color: colors.text, lineHeight: 19 },
  seller: { ...typography.caption, color: colors.sub },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
  },
  priceRow: { flexDirection: 'row', alignItems: 'baseline', gap: spacing.sm },
  price: { ...typography.bodyBold, color: colors.gold },
  was: {
    ...typography.tiny,
    color: colors.dim,
    textDecorationLine: 'line-through',
  },
  owned: { ...typography.caption, color: colors.green, fontWeight: '600' },
});
