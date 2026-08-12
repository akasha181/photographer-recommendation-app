import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import React from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { Button } from '../../../components/ui/Button';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatCount, formatPKR } from '../../../utils/format';
import { ProductThumb } from '../components/ProductThumb';
import {
  useAddToCart,
  useCart,
  useProduct,
  useToggleWishlist,
} from '../hooks/useShop';

/**
 * A product page.
 *
 * The file manifest is shown before purchase deliberately: someone deciding
 * whether to spend Rs 5,700 needs to know they get 42 presets and not one.
 * The names and sizes are public; the bytes are not, and nothing on this
 * screen can reach them — a download link only exists after a purchase.
 */
export function ProductDetailScreen({
  slug,
  onBack,
  onOpenCart,
  onTopUp,
}: {
  slug: string;
  onBack: () => void;
  onOpenCart: () => void;
  onTopUp: () => void;
}) {
  const { width } = useWindowDimensions();
  const query = useProduct(slug);
  const cart = useCart();
  const addToCart = useAddToCart();
  const toggleSave = useToggleWishlist();

  if (query.isLoading) return <LoadingState label="Loading product…" />;
  if (query.isError || !query.data) {
    return (
      <ErrorState
        message={(query.error as ApiError)?.message}
        onRetry={() => query.refetch()}
      />
    );
  }

  const product = query.data;
  const balance = Number(cart.data?.wallet_balance ?? 0);
  const affordable = balance >= Number(product.price);

  const add = () => {
    addToCart.mutate(product.id, {
      onError: (error) =>
        Alert.alert('Could not add to cart', (error as ApiError).message),
    });
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Pressable
          onPress={() => toggleSave.mutate({ product: product.id })}
          hitSlop={12}
          accessibilityLabel={product.is_wishlisted ? 'Remove from saved' : 'Save'}
        >
          <Ionicons
            name={product.is_wishlisted ? 'heart' : 'heart-outline'}
            size={22}
            color={product.is_wishlisted ? colors.red : colors.text}
          />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* ─── Gallery ─────────────────────────────────────────────────── */}
        <View style={[styles.hero, { height: width * 0.62 }]}>
          <ProductThumb
            uri={product.thumbnail_url}
            title={product.title}
            productType={product.product_type}
            style={styles.heroImage}
            iconSize={38}
            showLabel
          />
        </View>

        {product.preview_image_urls.length ? (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.previews}
          >
            {product.preview_image_urls.map((uri) => (
              <Image key={uri} source={{ uri }} style={styles.preview} contentFit="cover" />
            ))}
          </ScrollView>
        ) : null}

        <View style={styles.main}>
          <Text style={styles.type}>{product.type_label}</Text>
          <Text style={styles.title}>{product.title}</Text>

          <View style={styles.priceRow}>
            <Text style={styles.price}>{formatPKR(product.price)}</Text>
            {product.compare_at_price &&
            Number(product.compare_at_price) > Number(product.price) ? (
              <>
                <Text style={styles.was}>{formatPKR(product.compare_at_price)}</Text>
                <View style={styles.discountPill}>
                  <Text style={styles.discountText}>
                    Save {product.discount_percent}%
                  </Text>
                </View>
              </>
            ) : null}
          </View>

          <View style={styles.stats}>
            <Stat icon="download-outline" value={formatCount(product.sales_count)} label="sales" />
            <Stat icon="document-outline" value={String(product.file_count)} label="files" />
            <Stat icon="server-outline" value={`${product.total_size_mb} MB`} label="total" />
          </View>

          {/* ─── Seller ────────────────────────────────────────────────── */}
          <View style={styles.seller}>
            <Avatar
              uri={product.seller.avatar_url}
              name={product.seller.display_name}
              size={38}
            />
            <View style={styles.sellerBody}>
              <Text style={styles.sellerName}>{product.seller.display_name}</Text>
              <Text style={styles.sellerMeta}>
                {product.license_type === 'PERSONAL'
                  ? 'Personal use licence'
                  : product.license_type === 'COMMERCIAL'
                    ? 'Commercial licence'
                    : 'Extended commercial licence'}
              </Text>
            </View>
            {product.seller.is_verified ? (
              <Ionicons name="checkmark-circle" size={18} color={colors.blue} />
            ) : null}
          </View>

          {product.description ? (
            <Section title="About this pack">
              <Text style={styles.body}>{product.description}</Text>
            </Section>
          ) : null}

          {product.compatible_with?.length ? (
            <Section title="Works with">
              <View style={styles.tags}>
                {product.compatible_with.map((entry) => (
                  <View key={entry} style={styles.tag}>
                    <Text style={styles.tagText}>{entry}</Text>
                  </View>
                ))}
              </View>
            </Section>
          ) : null}

          {/* ─── Manifest ──────────────────────────────────────────────── */}
          {product.files.length ? (
            <Section title={`What you get (${product.files.length})`}>
              {product.files.map((file) => (
                <View key={file.id} style={styles.fileRow}>
                  <Ionicons name="document-outline" size={15} color={colors.dim} />
                  <Text style={styles.fileName} numberOfLines={1}>
                    {file.name}
                  </Text>
                  <Text style={styles.fileSize}>{file.file_size_mb} MB</Text>
                </View>
              ))}
            </Section>
          ) : null}
        </View>
      </ScrollView>

      {/* ─── Action bar ──────────────────────────────────────────────────── */}
      <View style={styles.actionBar}>
        {product.is_owned ? (
          <View style={styles.ownedBar}>
            <Ionicons name="checkmark-circle" size={18} color={colors.green} />
            <Text style={styles.ownedText}>
              You own this — find it in Purchases to download.
            </Text>
          </View>
        ) : product.in_cart ? (
          <Button label="Go to cart" onPress={onOpenCart} />
        ) : (
          <>
            <Button
              label="Add to cart"
              onPress={add}
              loading={addToCart.isPending}
            />
            {!affordable && cart.data ? (
              <Pressable onPress={onTopUp} style={styles.shortfall}>
                <Ionicons name="information-circle-outline" size={14} color={colors.amber} />
                <Text style={styles.shortfallText}>
                  Your balance is {formatPKR(cart.data.wallet_balance)} — top up to buy.
                </Text>
              </Pressable>
            ) : null}
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Stat({
  icon,
  value,
  label,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  value: string;
  label: string;
}) {
  return (
    <View style={styles.stat}>
      <Ionicons name={icon} size={15} color={colors.gold} />
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
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
  content: { paddingBottom: spacing.huge },
  hero: { backgroundColor: colors.surface },
  heroImage: { width: '100%', height: '100%', borderRadius: 0 },
  previews: { gap: spacing.sm, padding: spacing.lg },
  preview: { width: 90, height: 64, borderRadius: radius.sm },
  main: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  type: { ...typography.tiny, color: colors.dim, textTransform: 'uppercase' },
  title: { ...typography.h1, color: colors.text, marginTop: 2 },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  price: { ...typography.h2, color: colors.gold },
  was: { ...typography.caption, color: colors.dim, textDecorationLine: 'line-through' },
  discountPill: {
    backgroundColor: colors.greenDim,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  discountText: { ...typography.tiny, color: colors.green, fontWeight: '700' },
  stats: {
    flexDirection: 'row',
    gap: spacing.xxl,
    marginTop: spacing.xl,
    paddingVertical: spacing.lg,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.border,
  },
  stat: { alignItems: 'center', gap: 2 },
  statValue: { ...typography.bodyBold, color: colors.text },
  statLabel: { ...typography.tiny, color: colors.sub },
  seller: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.xl,
  },
  sellerBody: { flex: 1 },
  sellerName: { ...typography.bodyBold, color: colors.text },
  sellerMeta: { ...typography.caption, color: colors.sub },
  section: { marginTop: spacing.xxl },
  sectionTitle: { ...typography.h3, color: colors.text, marginBottom: spacing.md },
  body: { ...typography.body, color: colors.sub, lineHeight: 22 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  tag: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.pill,
  },
  tagText: { ...typography.caption, color: colors.sub },
  fileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  fileName: { ...typography.caption, color: colors.text, flex: 1 },
  fileSize: { ...typography.tiny, color: colors.dim },
  actionBar: {
    padding: spacing.xl,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  ownedBar: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  ownedText: { ...typography.caption, color: colors.green, flex: 1 },
  shortfall: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs + 2,
    marginTop: spacing.md,
  },
  shortfallText: { ...typography.tiny, color: colors.amber },
});
