import React, { useState } from 'react';
import {
  FlatList,
  Image,
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
import type { PortfolioAlbum } from '../../../types/models';
import { usePortfolioAlbums } from '../hooks/usePortfolio';

export function PortfolioScreen() {
  const [selectedAlbum, setSelectedAlbum] = useState<PortfolioAlbum | null>(null);
  const albums = usePortfolioAlbums();

  const rows = albums.data?.items ?? [];

  if (albums.isLoading) {
    return <LoadingState label="Loading your portfolio…" />;
  }

  if (albums.isError) {
    return (
      <ErrorState
        message={(albums.error as ApiError)?.message}
        onRetry={() => albums.refetch()}
      />
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Text style={styles.title}>Portfolio</Text>
        <Text style={styles.subtitle}>
          {rows.length > 0
            ? `${rows.length} album${rows.length === 1 ? '' : 's'}`
            : 'Start building your portfolio'}
        </Text>
      </View>

      <FlatList
        data={rows}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
        renderItem={({ item }) => (
          <AlbumCard
            album={item}
            onPress={() => setSelectedAlbum(item)}
          />
        )}
        ListEmptyComponent={
          <EmptyState
            icon="images-outline"
            title="No albums yet"
            detail="Your portfolio albums will appear here. Add albums to showcase your work."
          />
        }
        refreshControl={
          <RefreshControl
            refreshing={albums.isRefetching}
            onRefresh={() => albums.refetch()}
            tintColor={colors.gold}
          />
        }
      />
    </SafeAreaView>
  );
}

function AlbumCard({
  album,
  onPress,
}: {
  album: PortfolioAlbum;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={styles.card}>
      {album.cover_image ? (
        <Image
          source={{ uri: album.cover_image }}
          style={styles.cardImage}
        />
      ) : (
        <View style={[styles.cardImage, styles.cardImagePlaceholder]}>
          <Text style={styles.placeholderText}>No image</Text>
        </View>
      )}

      <View style={styles.cardContent}>
        <Text style={styles.albumTitle} numberOfLines={2}>
          {album.title}
        </Text>
        <Text style={styles.albumMeta}>
          {album.image_count} photo{album.image_count === 1 ? '' : 's'} · {album.view_count} view{album.view_count === 1 ? '' : 's'}
        </Text>
        {album.location ? (
          <Text style={styles.albumLocation} numberOfLines={1}>
            {album.location}
          </Text>
        ) : null}
      </View>

      {album.is_featured ? (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>Featured</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.lg },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub, marginTop: 2 },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl },
  listEmpty: { flexGrow: 1 },

  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
    marginBottom: spacing.md,
  },
  cardImage: {
    width: '100%',
    height: 180,
    backgroundColor: colors.surface,
  },
  cardImagePlaceholder: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  placeholderText: {
    ...typography.caption,
    color: colors.dim,
  },

  cardContent: {
    padding: spacing.lg,
  },
  albumTitle: {
    ...typography.bodyBold,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  albumMeta: {
    ...typography.caption,
    color: colors.sub,
    marginBottom: spacing.xs,
  },
  albumLocation: {
    ...typography.tiny,
    color: colors.dim,
  },

  badge: {
    position: 'absolute',
    top: spacing.md,
    right: spacing.md,
    backgroundColor: colors.gold,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
  },
  badgeText: {
    ...typography.tiny,
    color: colors.bg,
    fontWeight: '600',
  },
});
