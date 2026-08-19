import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { PhotographerCard } from '../../explore/components/PhotographerCard';
import { ProductCard } from '../../shop/components/ProductCard';
import { colors, radius, spacing, typography } from '../../../theme';
import { useToggleWishlist, useWishlist } from '../../shop/hooks/useShop';

/**
 * Saved photographers and products.
 *
 * Each tab reuses the card its own feature already ships, so a saved
 * photographer looks exactly like one in Explore and a saved product exactly
 * like one in the Shop. A bespoke "saved item" card would be a third thing to
 * keep in sync with two others.
 */
export function WishlistScreen({
  onBack,
  onOpenPhotographer,
  onOpenProduct,
}: {
  onBack: () => void;
  onOpenPhotographer: (id: number) => void;
  onOpenProduct: (slug: string) => void;
}) {
  const { width } = useWindowDimensions();
  const [tab, setTab] = useState<'photographers' | 'products'>('photographers');

  const wishlist = useWishlist();
  const toggle = useToggleWishlist();

  const counts = wishlist.data?.counts ?? { photographers: 0, products: 0 };
  const cardWidth = (width - spacing.xl * 2 - spacing.md) / 2;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>Saved</Text>
        <View style={styles.headerSpacer} />
      </View>

      <View style={styles.tabs}>
        <Tab
          label="Photographers"
          count={counts.photographers}
          active={tab === 'photographers'}
          onPress={() => setTab('photographers')}
        />
        <Tab
          label="Products"
          count={counts.products}
          active={tab === 'products'}
          onPress={() => setTab('products')}
        />
      </View>

      {wishlist.isLoading ? (
        <LoadingState label="Loading saved items…" />
      ) : wishlist.isError ? (
        <ErrorState
          message={(wishlist.error as ApiError)?.message}
          onRetry={() => wishlist.refetch()}
        />
      ) : tab === 'photographers' ? (
        <FlatList
          data={wishlist.data?.photographers ?? []}
          keyExtractor={(row) => String(row.id)}
          contentContainerStyle={
            wishlist.data?.photographers.length ? styles.list : styles.listEmpty
          }
          renderItem={({ item }) => (
            <PhotographerCard
              photographer={item.photographer}
              onPress={() => onOpenPhotographer(item.photographer.id)}
              onToggleWishlist={() =>
                toggle.mutate({ photographer: item.photographer.id })
              }
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="heart-outline"
              title="No saved photographers"
              detail="Tap the heart on a profile to keep it here for later."
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={wishlist.isRefetching}
              onRefresh={() => wishlist.refetch()}
              tintColor={colors.gold}
            />
          }
        />
      ) : (
        <FlatList
          key="2-cols"
          data={wishlist.data?.products ?? []}
          keyExtractor={(row) => String(row.id)}
          numColumns={2}
          columnWrapperStyle={styles.column}
          contentContainerStyle={
            wishlist.data?.products.length ? styles.list : styles.listEmpty
          }
          renderItem={({ item }) => (
            <ProductCard
              product={item.product}
              width={cardWidth}
              onPress={() => onOpenProduct(item.product.slug)}
              onToggleSave={() => toggle.mutate({ product: item.product.id })}
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="heart-outline"
              title="No saved products"
              detail="Tap the heart on a preset or template to keep it here."
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={wishlist.isRefetching}
              onRefresh={() => wishlist.refetch()}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

function Tab({
  label,
  count,
  active,
  onPress,
}: {
  label: string;
  count: number;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      style={[styles.tab, active && styles.tabActive]}
    >
      <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>
        {label}
      </Text>
      {count > 0 ? (
        <View style={[styles.badge, active && styles.badgeActive]}>
          <Text style={[styles.badgeText, active && styles.badgeTextActive]}>
            {count}
          </Text>
        </View>
      ) : null}
    </Pressable>
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
  tabs: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
    marginBottom: spacing.md,
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  tabActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  tabLabel: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  tabLabelActive: { color: colors.bg },
  badge: {
    minWidth: 20,
    paddingHorizontal: 5,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: 'center',
  },
  badgeActive: { backgroundColor: colors.bg },
  badgeText: { ...typography.tiny, color: colors.sub },
  badgeTextActive: { color: colors.gold },
  column: { gap: spacing.md },
  list: { padding: spacing.xl, paddingTop: 0 },
  listEmpty: { flexGrow: 1 },
});
