import { Ionicons } from '@expo/vector-icons';
import React, { useMemo, useState } from 'react';
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { useDebounce } from '../../../hooks/useDebounce';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatPKR } from '../../../utils/format';
import type { DigitalProduct } from '../../../types/models';
import { ProductCard } from '../components/ProductCard';
import {
  useCart,
  useProducts,
  useShopFilterOptions,
  useToggleWishlist,
} from '../hooks/useShop';

const SORTS = [
  { value: '-popularity', label: 'Best selling' },
  { value: 'price', label: 'Price ↑' },
  { value: '-price', label: 'Price ↓' },
  { value: '-rating', label: 'Top rated' },
  { value: '-newest', label: 'Newest' },
];

/**
 * The Shop grid.
 *
 * The "I can afford it" chip is a server-side filter rather than a client
 * one: filtering locally would only hide products from the page already
 * downloaded, so a buyer with Rs 900 would still scroll past twenty things
 * they cannot buy on page two.
 */
export function ShopScreen({
  onOpenProduct,
  onOpenCart,
}: {
  onOpenProduct: (slug: string) => void;
  onOpenCart: () => void;
}) {
  const { width } = useWindowDimensions();
  const [search, setSearch] = useState('');
  const [type, setType] = useState<string | null>(null);
  const [ordering, setOrdering] = useState('-popularity');
  const [affordableOnly, setAffordableOnly] = useState(false);

  const debounced = useDebounce(search, 350);

  const filters = useMemo(
    () => ({
      q: debounced || undefined,
      product_type: type ?? undefined,
      ordering,
      affordable: affordableOnly || undefined,
    }),
    [debounced, type, ordering, affordableOnly],
  );

  const products = useProducts(filters);
  const options = useShopFilterOptions();
  const cart = useCart();
  const toggleSave = useToggleWishlist();

  const rows: DigitalProduct[] =
    products.data?.pages.flatMap((page) => page.items) ?? [];

  // Two columns, with the gutters subtracted before dividing — otherwise the
  // right-hand column is clipped on narrow devices.
  const cardWidth = (width - spacing.xl * 2 - spacing.md) / 2;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Shop</Text>
          <Text style={styles.subtitle}>Presets, LUTs and templates</Text>
        </View>

        <Pressable
          onPress={onOpenCart}
          style={styles.cartButton}
          accessibilityLabel={`Cart, ${cart.data?.count ?? 0} items`}
        >
          <Ionicons name="cart-outline" size={22} color={colors.text} />
          {cart.data?.count ? (
            <View style={styles.cartBadge}>
              <Text style={styles.cartBadgeText}>{cart.data.count}</Text>
            </View>
          ) : null}
        </Pressable>
      </View>

      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color={colors.dim} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Search presets, LUTs, templates…"
          placeholderTextColor={colors.dim}
          style={styles.searchInput}
          returnKeyType="search"
        />
        {search ? (
          <Pressable onPress={() => setSearch('')} hitSlop={10}>
            <Ionicons name="close-circle" size={16} color={colors.dim} />
          </Pressable>
        ) : null}
      </View>

      {/* ─── Type chips ──────────────────────────────────────────────────── */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsWrap}
        contentContainerStyle={styles.chips}
      >
        <Chip label="All" active={type === null} onPress={() => setType(null)} />
        {(options.data?.types ?? []).map((entry) => (
          <Chip
            key={entry.value}
            label={`${entry.label} (${entry.count})`}
            active={type === entry.value}
            onPress={() => setType(type === entry.value ? null : entry.value)}
          />
        ))}
      </ScrollView>

      {/* ─── Sort + affordability ────────────────────────────────────────── */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsWrap}
        contentContainerStyle={styles.chips}
      >
        <Chip
          label={
            cart.data
              ? `Under ${formatPKR(cart.data.wallet_balance)}`
              : 'I can afford'
          }
          icon="wallet-outline"
          active={affordableOnly}
          onPress={() => setAffordableOnly((value) => !value)}
        />
        {SORTS.map((sort) => (
          <Chip
            key={sort.value}
            label={sort.label}
            active={ordering === sort.value}
            onPress={() => setOrdering(sort.value)}
          />
        ))}
      </ScrollView>

      {products.isLoading ? (
        <LoadingState label="Loading the shop…" />
      ) : products.isError ? (
        <ErrorState
          message={(products.error as ApiError)?.message}
          onRetry={() => products.refetch()}
        />
      ) : (
        <FlatList
          key="2-cols"
          data={rows}
          keyExtractor={(item) => String(item.id)}
          numColumns={2}
          columnWrapperStyle={styles.column}
          contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <ProductCard
              product={item}
              width={cardWidth}
              onPress={() => onOpenProduct(item.slug)}
              onToggleSave={() => toggleSave.mutate({ product: item.id })}
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="pricetags-outline"
              title="Nothing matches"
              detail={
                affordableOnly
                  ? 'Nothing in this range for your current balance. Try clearing the wallet filter.'
                  : 'Try a different search or category.'
              }
            />
          }
          onEndReachedThreshold={0.4}
          onEndReached={() => {
            if (products.hasNextPage && !products.isFetchingNextPage) {
              products.fetchNextPage();
            }
          }}
          refreshControl={
            <RefreshControl
              refreshing={products.isRefetching && !products.isFetchingNextPage}
              onRefresh={() => products.refetch()}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

function Chip({
  label,
  active,
  onPress,
  icon,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  icon?: keyof typeof Ionicons.glyphMap;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={[styles.chip, active && styles.chipActive]}
    >
      {icon ? (
        <Ionicons name={icon} size={13} color={active ? colors.bg : colors.sub} />
      ) : null}
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
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
    paddingTop: spacing.md,
  },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  cartButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cartBadge: {
    position: 'absolute',
    top: -2,
    right: -2,
    minWidth: 18,
    height: 18,
    paddingHorizontal: 4,
    borderRadius: 9,
    backgroundColor: colors.gold,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cartBadgeText: { ...typography.tiny, color: colors.bg, fontWeight: '700' },
  searchWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.xl,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.md,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  searchInput: { flex: 1, ...typography.body, color: colors.text },
  chipsWrap: { flexGrow: 0, marginTop: spacing.md },
  chips: { paddingHorizontal: spacing.xl, gap: spacing.sm },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs + 2,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  chipActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  chipTextActive: { color: colors.bg },
  column: { gap: spacing.md },
  list: { padding: spacing.xl, paddingTop: spacing.lg },
  listEmpty: { flexGrow: 1 },
});
