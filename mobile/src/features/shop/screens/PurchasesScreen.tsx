import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Linking,
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
import { formatDate, formatPKR } from '../../../utils/format';
import type { OrderItem, ProductFile } from '../../../types/models';
import { ProductThumb } from '../components/ProductThumb';
import { usePurchases, useRequestDownload } from '../hooks/useShop';

/**
 * The buyer's library.
 *
 * WHY DOWNLOADING OPENS THE BROWSER
 * ---------------------------------
 * The link is a single-use, 15-minute ticket the server mints on demand. It
 * carries no auth header — the token IS the credential — and handing it to
 * the OS lets the platform's own download manager save the file where the
 * user expects it. Streaming it inside the app would mean reimplementing
 * resumable downloads and file-system permissions for no benefit.
 *
 * Each tap spends one of the buyer's `max_downloads`, so the count is shown
 * before they use one.
 */
export function PurchasesScreen({
  onBack,
  onWriteReview,
}: {
  onBack?: () => void;
  /**
   * Module 9. Absent on the photographer's stack, which has no review route —
   * the row is then simply not offered rather than shown and dead.
   */
  onWriteReview?: (item: OrderItem) => void;
}) {
  const purchases = usePurchases();
  const requestDownload = useRequestDownload();
  const [busyItem, setBusyItem] = useState<number | null>(null);

  const download = (item: OrderItem, file: ProductFile) => {
    if (item.downloads_remaining <= 0) {
      Alert.alert(
        'No downloads left',
        `You have used all ${item.max_downloads} downloads for this item. Contact support if you need it again.`,
      );
      return;
    }

    setBusyItem(item.id);
    requestDownload.mutate(
      { itemId: item.id, fileId: file.id },
      {
        onSuccess: async (ticket) => {
          setBusyItem(null);
          const opened = await Linking.canOpenURL(ticket.download_url);
          if (opened) {
            Linking.openURL(ticket.download_url);
          } else {
            Alert.alert('Could not open the download', ticket.download_url);
          }
        },
        onError: (error) => {
          setBusyItem(null);
          Alert.alert('Download failed', (error as ApiError).message);
        },
      },
    );
  };

  const confirmDownload = (item: OrderItem, file: ProductFile) => {
    Alert.alert(
      file.name,
      `This uses one of your ${item.downloads_remaining} remaining downloads for this item.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Download', onPress: () => download(item, file) },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        {onBack ? (
          <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
            <Ionicons name="chevron-back" size={24} color={colors.text} />
          </Pressable>
        ) : null}
        <View>
          <Text style={styles.title}>Purchases</Text>
          <Text style={styles.subtitle}>Everything you own, ready to download</Text>
        </View>
      </View>

      {purchases.isLoading ? (
        <LoadingState label="Loading your library…" />
      ) : purchases.isError ? (
        <ErrorState
          message={(purchases.error as ApiError)?.message}
          onRetry={() => purchases.refetch()}
        />
      ) : (
        <FlatList
          data={purchases.data ?? []}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={purchases.data?.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <PurchaseCard
              item={item}
              busy={busyItem === item.id}
              onDownload={(file) => confirmDownload(item, file)}
              onWriteReview={
                onWriteReview && !item.has_review
                  ? () => onWriteReview(item)
                  : undefined
              }
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="download-outline"
              title="Nothing purchased yet"
              detail="Presets and templates you buy appear here with their download links."
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={purchases.isRefetching}
              onRefresh={() => purchases.refetch()}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

function PurchaseCard({
  item,
  busy,
  onDownload,
  onWriteReview,
}: {
  item: OrderItem;
  busy: boolean;
  onDownload: (file: ProductFile) => void;
  onWriteReview?: () => void;
}) {
  const exhausted = item.downloads_remaining <= 0;

  return (
    <View style={styles.card}>
      <View style={styles.cardTop}>
        <ProductThumb
          uri={item.thumbnail_url}
          title={item.product_title}
          style={styles.thumb}
          iconSize={20}
        />

        <View style={styles.cardBody}>
          <Text style={styles.cardTitle} numberOfLines={2}>
            {item.product_title}
          </Text>
          <Text style={styles.cardMeta}>
            {item.seller_name} · {formatDate(item.created_at)}
          </Text>
          <Text style={[styles.downloads, exhausted && styles.downloadsOut]}>
            {exhausted
              ? 'No downloads left'
              : `${item.downloads_remaining} of ${item.max_downloads} downloads left`}
          </Text>
        </View>

        <Text style={styles.price}>{formatPKR(item.price)}</Text>
      </View>

      <View style={styles.files}>
        {item.files.map((file) => (
          <Pressable
            key={file.id}
            onPress={() => onDownload(file)}
            disabled={busy || exhausted}
            accessibilityRole="button"
            accessibilityLabel={`Download ${file.name}`}
            style={[styles.fileRow, (busy || exhausted) && styles.fileRowDisabled]}
          >
            <Ionicons
              name={exhausted ? 'lock-closed-outline' : 'download-outline'}
              size={16}
              color={exhausted ? colors.dim : colors.gold}
            />
            <Text style={styles.fileName} numberOfLines={1}>
              {file.name}
            </Text>
            <Text style={styles.fileSize}>{file.file_size_mb} MB</Text>
          </Pressable>
        ))}
        {item.files.length === 0 ? (
          <Text style={styles.noFiles}>
            This product has no downloadable files yet.
          </Text>
        ) : null}
      </View>

      {onWriteReview ? (
        <Pressable
          onPress={onWriteReview}
          style={styles.reviewRow}
          accessibilityRole="button"
          accessibilityLabel={`Review ${item.product_title}`}
        >
          <Ionicons name="star-outline" size={15} color={colors.gold} />
          <Text style={styles.reviewText}>Rate this pack</Text>
          <Ionicons name="chevron-forward" size={14} color={colors.dim} />
        </Pressable>
      ) : item.has_review ? (
        <View style={styles.reviewRow}>
          <Ionicons name="checkmark-circle-outline" size={15} color={colors.green} />
          <Text style={styles.reviewedText}>You reviewed this</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
  },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl },
  listEmpty: { flexGrow: 1 },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  cardTop: { flexDirection: 'row', gap: spacing.md },
  thumb: { width: 58, height: 46, borderRadius: radius.sm },
  cardBody: { flex: 1 },
  cardTitle: { ...typography.bodyBold, color: colors.text },
  cardMeta: { ...typography.tiny, color: colors.sub, marginTop: 1 },
  downloads: { ...typography.tiny, color: colors.green, marginTop: spacing.xs },
  downloadsOut: { color: colors.dim },
  price: { ...typography.caption, color: colors.gold, fontWeight: '600' },
  files: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  fileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
  },
  fileRowDisabled: { opacity: 0.5 },
  fileName: { ...typography.caption, color: colors.text, flex: 1 },
  fileSize: { ...typography.tiny, color: colors.dim },
  noFiles: { ...typography.caption, color: colors.dim },
  reviewRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  reviewText: { ...typography.caption, color: colors.gold, flex: 1 },
  reviewedText: { ...typography.tiny, color: colors.sub, flex: 1 },
});
