import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatCount, formatPKR } from '../../../utils/format';
import type { SellerProduct } from '../../../types/models';
import { ProductThumb } from '../components/ProductThumb';
import { useSellerProducts, useSellerSummary } from '../hooks/useShop';

/**
 * What a photographer sells, and what it earned.
 *
 * Read-only: creating products means uploading files to private storage and
 * passing an admin moderation gate, which is scoped separately. Showing the
 * catalogue and the earnings is still worth doing on its own — a seller with
 * no visibility into their sales has no reason to list anything.
 */
export function SellerProductsScreen({
  onBack,
  onOpenProduct,
}: {
  onBack: () => void;
  onOpenProduct: (slug: string) => void;
}) {
  const products = useSellerProducts();
  const summary = useSellerSummary();

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>My products</Text>
        <View style={styles.headerSpacer} />
      </View>

      {products.isLoading ? (
        <LoadingState label="Loading your catalogue…" />
      ) : products.isError ? (
        <ErrorState
          message={(products.error as ApiError)?.message}
          onRetry={() => products.refetch()}
        />
      ) : (
        <FlatList
          data={products.data ?? []}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={products.data?.length ? styles.list : styles.listEmpty}
          ListHeaderComponent={
            summary.data ? (
              <View style={styles.summary}>
                <View style={styles.summaryRow}>
                  <Metric
                    value={formatPKR(summary.data.net_earnings)}
                    label="Net earnings"
                    highlight
                  />
                  <Metric
                    value={formatCount(summary.data.sales_count)}
                    label="Sales"
                  />
                </View>
                <View style={styles.summaryRow}>
                  <Metric
                    value={String(summary.data.products_live)}
                    label="Live listings"
                  />
                  <Metric
                    value={formatPKR(summary.data.gross_revenue)}
                    label="Gross revenue"
                  />
                </View>
                <Text style={styles.summaryNote}>
                  Earnings are credited to your wallet as each sale completes.
                </Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => (
            <SellerRow product={item} onPress={() => onOpenProduct(item.slug)} />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="pricetags-outline"
              title="No products yet"
              detail="Listings you sell in the SnapSphere shop appear here with their sales."
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={products.isRefetching}
              onRefresh={() => {
                products.refetch();
                summary.refetch();
              }}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

function SellerRow({
  product,
  onPress,
}: {
  product: SellerProduct;
  onPress: () => void;
}) {
  // A listing is only visible to buyers when the seller has published it AND
  // an admin has approved it. Showing the two states separately is what tells
  // a seller whether the ball is in their court or the platform's.
  const live = product.is_published && product.is_approved;
  const label = live ? 'Live' : product.is_published ? 'In review' : 'Draft';

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
      accessibilityRole="button"
    >
      <ProductThumb
        uri={product.thumbnail_url}
        title={product.title}
        productType={product.product_type}
        style={styles.thumb}
        iconSize={18}
      />

      <View style={styles.rowBody}>
        <Text style={styles.rowTitle} numberOfLines={2}>
          {product.title}
        </Text>
        <Text style={styles.rowMeta}>
          {product.type_label} · {formatCount(product.sales_count)} sold
        </Text>
      </View>

      <View style={styles.rowRight}>
        <Text style={styles.rowPrice}>{formatPKR(product.price)}</Text>
        <Text style={[styles.rowStatus, live ? styles.statusLive : styles.statusDraft]}>
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

function Metric({
  value,
  label,
  highlight,
}: {
  value: string;
  label: string;
  highlight?: boolean;
}) {
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricValue, highlight && styles.metricHighlight]} numberOfLines={1}>
        {value}
      </Text>
      <Text style={styles.metricLabel}>{label}</Text>
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
  },
  headerTitle: { ...typography.h3, color: colors.text },
  headerSpacer: { width: 24 },
  list: { padding: spacing.xl, paddingTop: 0 },
  listEmpty: { flexGrow: 1 },
  summary: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  summaryRow: { flexDirection: 'row', marginBottom: spacing.md },
  metric: { flex: 1 },
  metricValue: { ...typography.h3, color: colors.text },
  metricHighlight: { color: colors.gold },
  metricLabel: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  summaryNote: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  rowPressed: { backgroundColor: colors.cardHover },
  thumb: { width: 56, height: 44, borderRadius: radius.sm },
  rowBody: { flex: 1 },
  rowTitle: { ...typography.caption, color: colors.text, fontWeight: '600' },
  rowMeta: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  rowRight: { alignItems: 'flex-end' },
  rowPrice: { ...typography.caption, color: colors.gold, fontWeight: '700' },
  rowStatus: { ...typography.tiny, marginTop: 2 },
  statusLive: { color: colors.green },
  statusDraft: { color: colors.dim },
});
