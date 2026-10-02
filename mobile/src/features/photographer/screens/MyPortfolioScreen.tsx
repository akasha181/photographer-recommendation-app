import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
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
import { Button } from '../../../components/ui/Button';
import { colors, radius, spacing, typography } from '../../../theme';
import type { PortfolioImage } from '../../../types/models';
import {
  useCreateAlbum,
  useDeleteImage,
  useMyAlbums,
  useMyPortfolio,
  usePortfolioSummary,
  useToggleFeature,
  useUpdatePortfolioImage,
  useUploadImage,
} from '../hooks/useMyStudio';

/**
 * The photographer's portfolio — Module 6.
 *
 * WHY UPLOAD FEELS SLOW AND SAYS SO
 * ---------------------------------
 * A phone photo is 4-8 MB, and the server strips its EXIF and generates three
 * renditions before replying. That is a real wait on 3G, so the tile shows a
 * spinner in place rather than an indefinite modal — and the copy says the
 * location data is being removed, because that is the reason for the wait and
 * it is worth knowing.
 */
export function MyPortfolioScreen() {
  const { width } = useWindowDimensions();

  const portfolio = useMyPortfolio();
  const summary = usePortfolioSummary();
  const albums = useMyAlbums();
  const uploadImage = useUploadImage();
  const updateImage = useUpdatePortfolioImage();
  const toggleFeature = useToggleFeature();
  const deleteImage = useDeleteImage();
  const createAlbum = useCreateAlbum();

  const [viewing, setViewing] = useState<PortfolioImage | null>(null);
  const [activeAlbumId, setActiveAlbumId] = useState<number | null>(null);
  const [editingCaption, setEditingCaption] = useState(false);
  const [captionDraft, setCaptionDraft] = useState('');
  const [creatingAlbum, setCreatingAlbum] = useState(false);
  const [albumTitleDraft, setAlbumTitleDraft] = useState('');

  const columns = 3;
  const tile = (width - spacing.xl * 2 - spacing.sm * (columns - 1)) / columns;

  const fail = (error: unknown) =>
    Alert.alert('Upload failed', (error as ApiError)?.message ?? 'Please try again.');

  const pickAndUpload = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(
        'Photo access needed',
        'We need access to your photos so you can add work to your portfolio.',
      );
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      // Compressed client-side too: a 12 MB original would be rejected by the
      // server's size limit before it ever got resized.
      quality: 0.8,
      allowsMultipleSelection: true,
      selectionLimit: 5,
    });
    if (result.canceled) return;

    // Sequential, not parallel: five 6 MB uploads at once on a phone connection
    // time each other out.
    for (const asset of result.assets) {
      await new Promise<void>((resolve) => {
        uploadImage.mutate(
          {
            file: {
              uri: asset.uri,
              name: asset.fileName ?? `photo-${Date.now()}.jpg`,
              type: asset.mimeType ?? 'image/jpeg',
            },
            album: activeAlbumId ?? undefined,
          },
          { onSuccess: () => resolve(), onError: (error) => (fail(error), resolve()) },
        );
      });
    }
  };

  const confirmDelete = (image: PortfolioImage) => {
    setViewing(null);
    Alert.alert('Remove this photo?', 'It will disappear from your public profile.', [
      { text: 'Keep', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: () =>
          deleteImage.mutate(image.id, {
            onError: (error) =>
              Alert.alert('Could not remove', (error as ApiError).message),
          }),
      },
    ]);
  };

  const allImages = portfolio.data ?? [];
  const filteredData = activeAlbumId
    ? allImages.filter(
        (img) => img.album === activeAlbumId || (img as any).album_id === activeAlbumId,
      )
    : allImages;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Portfolio</Text>
          {summary.data ? (
            <Text style={styles.subtitle}>
              {summary.data.images} photo{summary.data.images === 1 ? '' : 's'} ·{' '}
              {summary.data.featured} featured
            </Text>
          ) : null}
        </View>
        <Pressable
          onPress={pickAndUpload}
          style={styles.addButton}
          accessibilityLabel="Add photos"
          disabled={uploadImage.isPending}
        >
          <Ionicons
            name={uploadImage.isPending ? 'cloud-upload' : 'add'}
            size={22}
            color={colors.bg}
          />
        </Pressable>
      </View>

      {/* ─── Album Filter Bar ───────────────────────────────────────────── */}
      <View style={styles.albumBar}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.albumBarContent}
        >
          <Pressable
            onPress={() => setActiveAlbumId(null)}
            style={[styles.albumPill, activeAlbumId === null && styles.albumPillActive]}
          >
            <Text
              style={[
                styles.albumPillText,
                activeAlbumId === null && styles.albumPillTextActive,
              ]}
            >
              All Photos ({allImages.length})
            </Text>
          </Pressable>
          {(albums.data ?? []).map((album) => {
            const count = allImages.filter(
              (img) => img.album === album.id || (img as any).album_id === album.id,
            ).length;
            return (
              <Pressable
                key={album.id}
                onPress={() => setActiveAlbumId(album.id)}
                style={[
                  styles.albumPill,
                  activeAlbumId === album.id && styles.albumPillActive,
                ]}
              >
                <Text
                  style={[
                    styles.albumPillText,
                    activeAlbumId === album.id && styles.albumPillTextActive,
                  ]}
                >
                  {album.title} ({count})
                </Text>
              </Pressable>
            );
          })}
          <Pressable
            onPress={() => {
              setAlbumTitleDraft('');
              setCreatingAlbum(true);
            }}
            style={styles.albumPillAdd}
          >
            <Ionicons name="add" size={14} color={colors.gold} />
            <Text style={styles.albumPillAddText}>New Album</Text>
          </Pressable>
        </ScrollView>
      </View>

      {uploadImage.isPending ? (
        <View style={styles.uploading}>
          <Ionicons name="shield-checkmark-outline" size={15} color={colors.gold} />
          <Text style={styles.uploadingText}>
            Uploading — removing location data and making three sizes…
          </Text>
        </View>
      ) : null}

      {portfolio.isLoading ? (
        <LoadingState label="Loading your work…" />
      ) : portfolio.isError ? (
        <ErrorState
          message={(portfolio.error as ApiError)?.message}
          onRetry={() => portfolio.refetch()}
        />
      ) : (
        <FlatList
          data={filteredData}
          keyExtractor={(item) => String(item.id)}
          numColumns={columns}
          columnWrapperStyle={styles.column}
          contentContainerStyle={filteredData.length ? styles.grid : styles.gridEmpty}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => setViewing(item)}
              style={[styles.tile, { width: tile, height: tile }]}
              accessibilityRole="button"
              accessibilityLabel={item.caption || 'Portfolio photo'}
            >
              <Image
                source={{ uri: item.thumbnail_url ?? item.image_url ?? '' }}
                style={styles.tileImage}
                contentFit="cover"
                transition={150}
              />
              {item.is_featured ? (
                <View style={styles.star}>
                  <Ionicons name="star" size={11} color={colors.gold} />
                </View>
              ) : null}
            </Pressable>
          )}
          ListEmptyComponent={
            <EmptyState
              icon="images-outline"
              title="No work in this view"
              detail="Add your best photos to showcase your photography skills."
              actionLabel="Add photos"
              onAction={pickAndUpload}
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={portfolio.isRefetching}
              onRefresh={() => {
                portfolio.refetch();
                summary.refetch();
                albums.refetch();
              }}
              tintColor={colors.gold}
            />
          }
        />
      )}

      {/* ─── Full-screen viewer ──────────────────────────────────────────── */}
      <Modal
        visible={viewing !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setViewing(null)}
      >
        <View style={styles.viewer}>
          <Pressable
            onPress={() => setViewing(null)}
            style={styles.viewerClose}
            hitSlop={12}
            accessibilityLabel="Close"
          >
            <Ionicons name="close" size={26} color={colors.text} />
          </Pressable>

          {viewing ? (
            <>
              {/* Only the large rendition is fetched, and only here. */}
              <Image
                source={{ uri: viewing.image_large_url ?? viewing.image_url ?? '' }}
                style={styles.viewerImage}
                contentFit="contain"
                transition={200}
              />

              <View style={styles.viewerBar}>
                {viewing.caption ? (
                  <Text style={styles.viewerCaption}>{viewing.caption}</Text>
                ) : (
                  <Text style={[styles.viewerCaption, { color: colors.dim }]}>
                    No caption added
                  </Text>
                )}
                <Text style={styles.viewerMeta}>
                  {viewing.width}×{viewing.height} · {viewing.like_count} likes
                </Text>

                <View style={styles.viewerActions}>
                  <View style={styles.viewerAction}>
                    <Button
                      label="Edit"
                      variant="secondary"
                      onPress={() => {
                        setCaptionDraft(viewing.caption || '');
                        setEditingCaption(true);
                      }}
                    />
                  </View>
                  <View style={styles.viewerAction}>
                    <Button
                      label={viewing.is_featured ? 'Unfeature' : 'Feature'}
                      variant="secondary"
                      onPress={() =>
                        toggleFeature.mutate(viewing.id, {
                          onSuccess: (updated) => setViewing(updated),
                          onError: (error) =>
                            Alert.alert(
                              'Could not feature',
                              (error as ApiError).message,
                            ),
                        })
                      }
                    />
                  </View>
                  <View style={styles.viewerAction}>
                    <Button
                      label="Remove"
                      variant="danger"
                      onPress={() => confirmDelete(viewing)}
                    />
                  </View>
                </View>
              </View>
            </>
          ) : null}
        </View>
      </Modal>

      {/* ─── Edit Caption Modal ─────────────────────────────────────────── */}
      <Modal
        visible={editingCaption}
        transparent
        animationType="fade"
        onRequestClose={() => setEditingCaption(false)}
      >
        <View style={styles.promptOverlay}>
          <View style={styles.promptCard}>
            <Text style={styles.promptTitle}>Edit Photo Caption</Text>
            <TextInput
              value={captionDraft}
              onChangeText={setCaptionDraft}
              placeholder="Add caption or description..."
              placeholderTextColor={colors.dim}
              style={styles.promptInput}
              autoFocus
            />
            <View style={styles.promptButtons}>
              <View style={{ flex: 1 }}>
                <Button
                  label="Cancel"
                  variant="secondary"
                  onPress={() => setEditingCaption(false)}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Button
                  label="Save"
                  variant="primary"
                  loading={updateImage.isPending}
                  onPress={() => {
                    if (!viewing) return;
                    updateImage.mutate(
                      { id: viewing.id, payload: { caption: captionDraft.trim() } },
                      {
                        onSuccess: () => {
                          setViewing({ ...viewing, caption: captionDraft.trim() });
                          setEditingCaption(false);
                        },
                        onError: (error) =>
                          Alert.alert('Update Failed', (error as ApiError).message),
                      },
                    );
                  }}
                />
              </View>
            </View>
          </View>
        </View>
      </Modal>

      {/* ─── Create Album Modal ─────────────────────────────────────────── */}
      <Modal
        visible={creatingAlbum}
        transparent
        animationType="fade"
        onRequestClose={() => setCreatingAlbum(false)}
      >
        <View style={styles.promptOverlay}>
          <View style={styles.promptCard}>
            <Text style={styles.promptTitle}>Create New Album</Text>
            <TextInput
              value={albumTitleDraft}
              onChangeText={setAlbumTitleDraft}
              placeholder="Album title (e.g. Weddings 2026)"
              placeholderTextColor={colors.dim}
              style={styles.promptInput}
              autoFocus
            />
            <View style={styles.promptButtons}>
              <View style={{ flex: 1 }}>
                <Button
                  label="Cancel"
                  variant="secondary"
                  onPress={() => setCreatingAlbum(false)}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Button
                  label="Create"
                  variant="primary"
                  loading={createAlbum.isPending}
                  onPress={() => {
                    if (!albumTitleDraft.trim()) {
                      Alert.alert('Title required', 'Please enter an album title.');
                      return;
                    }
                    createAlbum.mutate(
                      { title: albumTitleDraft.trim() },
                      {
                        onSuccess: () => {
                          setCreatingAlbum(false);
                          setAlbumTitleDraft('');
                          albums.refetch();
                        },
                        onError: (error) =>
                          Alert.alert('Could not create album', (error as ApiError).message),
                      },
                    );
                  }}
                />
              </View>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
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
    paddingBottom: spacing.lg,
  },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub, marginTop: 2 },
  addButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.gold,
    alignItems: 'center',
    justifyContent: 'center',
  },
  uploading: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.xl,
    marginBottom: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.goldDim,
  },
  uploadingText: { ...typography.caption, color: colors.sub, flex: 1 },
  grid: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl },
  gridEmpty: { flexGrow: 1 },
  column: { gap: spacing.sm, marginBottom: spacing.sm },
  tile: {
    borderRadius: radius.sm,
    overflow: 'hidden',
    backgroundColor: colors.card,
  },
  tileImage: { width: '100%', height: '100%' },
  star: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.overlay,
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewer: { flex: 1, backgroundColor: colors.black },
  viewerClose: {
    position: 'absolute',
    top: 52,
    right: spacing.xl,
    zIndex: 2,
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.overlay,
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewerImage: { flex: 1 },
  viewerBar: {
    padding: spacing.xl,
    paddingBottom: spacing.xxxl,
    backgroundColor: colors.surface,
    gap: spacing.xs,
  },
  viewerCaption: { ...typography.bodyBold, color: colors.text },
  viewerMeta: { ...typography.tiny, color: colors.sub },
  viewerActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  viewerAction: { flex: 1 },

  // ─── Album Filter Bar ───
  albumBar: { marginBottom: spacing.md },
  albumBarContent: { paddingHorizontal: spacing.xl, gap: spacing.sm, alignItems: 'center' },
  albumPill: {
    paddingHorizontal: spacing.md,
    paddingVertical: 7,
    borderRadius: radius.pill,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  albumPillActive: {
    backgroundColor: colors.goldDim,
    borderColor: colors.gold,
  },
  albumPillText: { ...typography.caption, color: colors.sub },
  albumPillTextActive: { color: colors.gold, fontWeight: '600' },
  albumPillAdd: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: 7,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.gold,
    borderStyle: 'dashed',
  },
  albumPillAddText: { ...typography.caption, color: colors.gold, fontWeight: '600' },

  // ─── Prompt Modal ───
  promptOverlay: {
    flex: 1,
    backgroundColor: colors.overlay,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  promptCard: {
    width: '100%',
    maxWidth: 380,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.md,
  },
  promptTitle: { ...typography.h3, color: colors.text },
  promptInput: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    color: colors.text,
    ...typography.body,
  },
  promptButtons: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
});
