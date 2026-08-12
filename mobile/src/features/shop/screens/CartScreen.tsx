import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatPKR } from '../../../utils/format';
import type { CartLine } from '../../../types/models';
import { ProductThumb } from '../components/ProductThumb';
import {
  useCart,
  useCheckout,
  useClearCart,
  useRemoveFromCart,
} from '../hooks/useShop';

/**
 * The basket and wallet checkout.
 *
 * WHY THE SHORTFALL IS A SERVER NUMBER
 * ------------------------------------
 * `can_checkout` and `shortfall` come from the API rather than being computed
 * here from `total - balance`. Money is DECIMAL on the server and a string on
 * the wire precisely because JavaScript cannot add currency exactly; doing
 * that subtraction in JS is how a cart says "you need Rs 0" and the checkout
 * then fails with insufficient balance.
 */
export function CartScreen({
  onBack,
  onOpenProduct,
  onTopUp,
  onPurchased,
}: {
  onBack: () => void;
  onOpenProduct: (slug: string) => void;
  onTopUp: () => void;
  onPurchased: (orderId: number) => void;
}) {
  const cart = useCart();
  const removeItem = useRemoveFromCart();
  const clearCart = useClearCart();
  const checkout = useCheckout();

  if (cart.isLoading) return <LoadingState label="Loading your cart…" />;
  if (cart.isError || !cart.data) {
    return (
      <ErrorState
        message={(cart.error as ApiError)?.message}
        onRetry={() => cart.refetch()}
      />
    );
  }

  const { items, total, wallet_balance, can_checkout, shortfall, unavailable_count } =
    cart.data;

  const buy = () => {
    checkout.mutate(undefined, {
      onSuccess: (order) => onPurchased(order.id),
      onError: (error) => {
        const api = error as ApiError;
        if (api.code === 'INSUFFICIENT_BALANCE') {
          Alert.alert('Not enough balance', api.message, [
            { text: 'Later', style: 'cancel' },
            { text: 'Top up', onPress: onTopUp },
          ]);
          return;
        }
        Alert.alert('Could not complete the purchase', api.message);
        cart.refetch();
      },
    });
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>Cart</Text>
        {items.length ? (
          <Pressable
            onPress={() =>
              Alert.alert('Empty the cart?', 'This removes everything in it.', [
                { text: 'Keep', style: 'cancel' },
                { text: 'Empty', style: 'destructive', onPress: () => clearCart.mutate(undefined) },
              ])
            }
            hitSlop={12}
          >
            <Text style={styles.clear}>Clear</Text>
          </Pressable>
        ) : (
          <View style={styles.headerSpacer} />
        )}
      </View>

      {items.length === 0 ? (
        <EmptyState
          icon="cart-outline"
          title="Your cart is empty"
          detail="Presets, LUTs and templates you add will show up here."
        />
      ) : (
        <>
          <ScrollView contentContainerStyle={styles.list}>
            {unavailable_count > 0 ? (
              <View style={styles.warning}>
                <Ionicons name="alert-circle-outline" size={16} color={colors.amber} />
                <Text style={styles.warningText}>
                  {unavailable_count === 1
                    ? 'One item can no longer be bought. Remove it to check out.'
                    : `${unavailable_count} items can no longer be bought. Remove them to check out.`}
                </Text>
              </View>
            ) : null}

            {items.map((line) => (
              <CartRow
                key={line.id}
                line={line}
                onPress={() => onOpenProduct(line.product.slug)}
                onRemove={() => removeItem.mutate(line.product.id)}
              />
            ))}
          </ScrollView>

          <View style={styles.footer}>
            <Row label="Subtotal" value={formatPKR(total)} />
            <Row label="Wallet balance" value={formatPKR(wallet_balance)} muted />
            {Number(shortfall) > 0 ? (
              <Row label="Still needed" value={formatPKR(shortfall)} warn />
            ) : null}

            <View style={styles.totalRow}>
              <Text style={styles.totalLabel}>Total</Text>
              <Text style={styles.totalValue}>{formatPKR(total)}</Text>
            </View>

            {can_checkout ? (
              <Button
                label="Pay from wallet"
                onPress={buy}
                loading={checkout.isPending}
              />
            ) : Number(shortfall) > 0 ? (
              <Button label={`Top up ${formatPKR(shortfall)}`} onPress={onTopUp} />
            ) : (
              <Button label="Pay from wallet" onPress={buy} disabled />
            )}

            <Text style={styles.note}>
              Paid from your SnapSphere wallet. Downloads unlock immediately.
            </Text>
          </View>
        </>
      )}
    </SafeAreaView>
  );
}

function CartRow({
  line,
  onPress,
  onRemove,
}: {
  line: CartLine;
  onPress: () => void;
  onRemove: () => void;
}) {
  return (
    <View style={[styles.row, !line.is_available && styles.rowDisabled]}>
      <Pressable onPress={onPress} style={styles.rowMain} accessibilityRole="button">
        <ProductThumb
          uri={line.product.thumbnail_url}
          title={line.product.title}
          productType={line.product.product_type}
          style={styles.thumb}
          iconSize={18}
        />

        <View style={styles.rowBody}>
          <Text style={styles.rowTitle} numberOfLines={2}>
            {line.product.title}
          </Text>
          <Text style={styles.rowSeller} numberOfLines={1}>
            {line.product.seller.display_name}
          </Text>
          {!line.is_available ? (
            <Text style={styles.rowUnavailable}>
              {line.is_owned ? 'Already in your library' : 'No longer on sale'}
            </Text>
          ) : null}
        </View>

        <Text style={styles.rowPrice}>{formatPKR(line.product.price)}</Text>
      </Pressable>

      <Pressable
        onPress={onRemove}
        hitSlop={10}
        accessibilityLabel={`Remove ${line.product.title}`}
        style={styles.remove}
      >
        <Ionicons name="trash-outline" size={16} color={colors.dim} />
      </Pressable>
    </View>
  );
}

function Row({
  label,
  value,
  muted,
  warn,
}: {
  label: string;
  value: string;
  muted?: boolean;
  warn?: boolean;
}) {
  return (
    <View style={styles.summaryRow}>
      <Text style={[styles.summaryLabel, muted && styles.muted]}>{label}</Text>
      <Text style={[styles.summaryValue, muted && styles.muted, warn && styles.warn]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { ...typography.h3, color: colors.text },
  headerSpacer: { width: 34 },
  clear: { ...typography.caption, color: colors.red, fontWeight: '600' },
  list: { padding: spacing.xl },
  warning: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  warningText: { ...typography.caption, color: colors.amber, flex: 1 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  rowDisabled: { opacity: 0.6, borderColor: colors.amberDim },
  rowMain: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, flex: 1 },
  thumb: { width: 56, height: 44, borderRadius: radius.sm },
  rowBody: { flex: 1 },
  rowTitle: { ...typography.caption, color: colors.text, fontWeight: '600' },
  rowSeller: { ...typography.tiny, color: colors.sub },
  rowUnavailable: { ...typography.tiny, color: colors.amber, marginTop: 2 },
  rowPrice: { ...typography.bodyBold, color: colors.gold },
  remove: { paddingLeft: spacing.md },
  footer: {
    padding: spacing.xl,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  summaryLabel: { ...typography.caption, color: colors.text },
  summaryValue: { ...typography.caption, color: colors.text },
  muted: { color: colors.sub },
  warn: { color: colors.amber, fontWeight: '600' },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: spacing.md,
    marginBottom: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  totalLabel: { ...typography.h3, color: colors.text },
  totalValue: { ...typography.h3, color: colors.gold },
  note: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
});
