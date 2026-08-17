import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { Image } from 'expo-image';
import React, { useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { Button } from '../../../components/ui/Button';
import { colors, radius, spacing, typography } from '../../../theme';
import { useCreateProductReview, useCreateReview } from '../hooks/useReviews';

const MAX_PHOTOS = 5;

const SUB_RATINGS = [
  { key: 'rating_quality', label: 'Photo quality' },
  { key: 'rating_professionalism', label: 'Professionalism' },
  { key: 'rating_communication', label: 'Communication' },
  { key: 'rating_value', label: 'Value for money' },
  { key: 'rating_punctuality', label: 'Punctuality' },
] as const;

type Target =
  | { kind: 'booking'; bookingId: number; subject: string; detail?: string }
  | { kind: 'product'; orderItemId: number; subject: string; detail?: string };

/**
 * The review form — one screen for both a shoot and a purchased product.
 *
 * WHY A LOW RATING ASKS FOR WORDS BEFORE IT WILL SUBMIT
 * ---------------------------------------------------
 * The server refuses a 1★ or 2★ review with no comment, so the button is
 * disabled with an explanation rather than letting the user tap it and read a
 * validation error. The rule lives on the server; this screen just stops the
 * pointless round trip.
 *
 * WHY PHOTOS ARE OPTIONAL AND CAPPED AT FIVE
 * -----------------------------------------
 * Buyer photos are the strongest trust signal a profile can carry, but each one
 * is three renditions on disk and a row in every detail payload. Five is enough
 * to be evidence and few enough to stay cheap. The picker strips nothing itself
 * — the server re-encodes and drops EXIF, because a venue photo carries GPS.
 */
export function WriteReviewScreen({
  target,
  onBack,
  onDone,
}: {
  target: Target;
  onBack: () => void;
  onDone: () => void;
}) {
  const [rating, setRating] = useState(0);
  const [title, setTitle] = useState('');
  const [comment, setComment] = useState('');
  const [subRatings, setSubRatings] = useState<Record<string, number>>({});
  const [photos, setPhotos] = useState<ImagePicker.ImagePickerAsset[]>([]);
  const [showDetail, setShowDetail] = useState(false);

  const createReview = useCreateReview();
  const createProductReview = useCreateProductReview();
  const busy = createReview.isPending || createProductReview.isPending;

  const needsComment = rating > 0 && rating <= 2 && comment.trim().length === 0;
  const canSubmit = rating > 0 && !needsComment && !busy;

  const pickPhotos = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert(
        'Photo access needed',
        'Allow photo access to add pictures from the shoot to your review.',
      );
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      selectionLimit: MAX_PHOTOS - photos.length,
      quality: 0.9,
    });
    if (!result.canceled) {
      setPhotos((current) => [...current, ...result.assets].slice(0, MAX_PHOTOS));
    }
  };

  const fail = (error: unknown) =>
    Alert.alert(
      'Could not post your review',
      (error as ApiError)?.message ?? 'Please try again.',
    );

  const submit = () => {
    if (target.kind === 'product') {
      createProductReview.mutate(
        {
          order_item: target.orderItemId,
          rating,
          title: title.trim(),
          comment: comment.trim(),
        },
        { onSuccess: onDone, onError: fail },
      );
      return;
    }

    createReview.mutate(
      {
        booking: target.bookingId,
        rating,
        title: title.trim(),
        comment: comment.trim(),
        ...subRatings,
        images: photos.map((asset) => ({
          uri: asset.uri,
          name: asset.fileName ?? undefined,
          type: asset.mimeType ?? 'image/jpeg',
        })),
      },
      { onSuccess: onDone, onError: fail },
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <View style={styles.headerBody}>
          <Text style={styles.title}>Write a review</Text>
          <Text style={styles.subtitle} numberOfLines={1}>
            {target.subject}
          </Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {target.detail ? <Text style={styles.context}>{target.detail}</Text> : null}

        {/* ─── The star row ──────────────────────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>How was it?</Text>
          <View style={styles.starRow}>
            {[1, 2, 3, 4, 5].map((value) => (
              <Pressable
                key={value}
                onPress={() => setRating(value)}
                hitSlop={6}
                accessibilityRole="button"
                accessibilityLabel={`${value} star${value > 1 ? 's' : ''}`}
              >
                <Ionicons
                  name={rating >= value ? 'star' : 'star-outline'}
                  size={36}
                  color={rating >= value ? colors.gold : colors.dim}
                />
              </Pressable>
            ))}
          </View>
          <Text style={styles.ratingLabel}>{RATING_LABELS[rating] ?? 'Tap to rate'}</Text>
        </View>

        {/* ─── Words ─────────────────────────────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Add a headline (optional)</Text>
          <TextInput
            value={title}
            onChangeText={setTitle}
            placeholder="Worth every rupee"
            placeholderTextColor={colors.dim}
            maxLength={140}
            style={styles.input}
          />

          <Text style={[styles.cardTitle, styles.spaced]}>
            {rating > 0 && rating <= 2 ? 'What went wrong?' : 'Tell others about it'}
          </Text>
          <TextInput
            value={comment}
            onChangeText={setComment}
            placeholder={
              rating > 0 && rating <= 2
                ? 'Being specific helps us look into it and helps other buyers.'
                : 'What stood out? How was the shoot on the day?'
            }
            placeholderTextColor={colors.dim}
            multiline
            maxLength={3000}
            style={[styles.input, styles.textarea]}
          />
          {needsComment ? (
            <Text style={styles.required}>
              A low rating needs a few words — it moves this photographer's average, and
              we have to be able to say on what grounds.
            </Text>
          ) : (
            <Text style={styles.counter}>{comment.length}/3000</Text>
          )}
        </View>

        {/* ─── Booking-only extras ───────────────────────────────────────── */}
        {target.kind === 'booking' ? (
          <>
            <Pressable
              style={styles.disclosure}
              onPress={() => setShowDetail((open) => !open)}
            >
              <Text style={styles.disclosureText}>
                Rate the details (optional)
              </Text>
              <Ionicons
                name={showDetail ? 'chevron-up' : 'chevron-down'}
                size={18}
                color={colors.sub}
              />
            </Pressable>

            {showDetail ? (
              <View style={styles.card}>
                <Text style={styles.hint}>
                  A 3-star average tells a photographer nothing. "5 for quality, 2 for
                  punctuality" tells them exactly what to fix.
                </Text>
                {SUB_RATINGS.map((row) => (
                  <View key={row.key} style={styles.subRow}>
                    <Text style={styles.subLabel}>{row.label}</Text>
                    <View style={styles.subStars}>
                      {[1, 2, 3, 4, 5].map((value) => (
                        <Pressable
                          key={value}
                          hitSlop={4}
                          onPress={() =>
                            setSubRatings((current) => ({ ...current, [row.key]: value }))
                          }
                        >
                          <Ionicons
                            name={
                              (subRatings[row.key] ?? 0) >= value
                                ? 'star'
                                : 'star-outline'
                            }
                            size={18}
                            color={
                              (subRatings[row.key] ?? 0) >= value
                                ? colors.gold
                                : colors.dim
                            }
                          />
                        </Pressable>
                      ))}
                    </View>
                  </View>
                ))}
              </View>
            ) : null}

            <View style={styles.card}>
              <Text style={styles.cardTitle}>Add photos (optional)</Text>
              <Text style={styles.hint}>
                Location data is stripped from anything you upload.
              </Text>
              <View style={styles.photoRow}>
                {photos.map((asset, index) => (
                  <View key={asset.uri} style={styles.photoWrap}>
                    <Image source={{ uri: asset.uri }} style={styles.photo} contentFit="cover" />
                    <Pressable
                      style={styles.photoRemove}
                      hitSlop={6}
                      accessibilityLabel={`Remove photo ${index + 1}`}
                      onPress={() =>
                        setPhotos((current) => current.filter((p) => p.uri !== asset.uri))
                      }
                    >
                      <Ionicons name="close" size={13} color={colors.text} />
                    </Pressable>
                  </View>
                ))}
                {photos.length < MAX_PHOTOS ? (
                  <Pressable style={styles.photoAdd} onPress={pickPhotos}>
                    <Ionicons name="add" size={22} color={colors.sub} />
                  </Pressable>
                ) : null}
              </View>
            </View>
          </>
        ) : null}

        <Text style={styles.footnote}>
          You can correct a review for 24 hours after posting — and until the photographer
          replies to it.
        </Text>
      </ScrollView>

      <View style={styles.bar}>
        <Button
          label="Post review"
          onPress={submit}
          disabled={!canSubmit}
          loading={busy}
        />
      </View>
    </SafeAreaView>
  );
}

const RATING_LABELS: Record<number, string> = {
  1: 'Poor',
  2: 'Below expectations',
  3: 'Fine',
  4: 'Very good',
  5: 'Outstanding',
};

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
  headerBody: { flex: 1 },
  title: { ...typography.h2, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  body: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  context: { ...typography.caption, color: colors.dim, marginBottom: spacing.md },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  cardTitle: { ...typography.bodyBold, color: colors.text },
  spaced: { marginTop: spacing.lg },
  starRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  ratingLabel: {
    ...typography.caption,
    color: colors.gold,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  input: {
    ...typography.body,
    color: colors.text,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
  },
  textarea: { minHeight: 110, textAlignVertical: 'top' },
  counter: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'right',
    marginTop: spacing.xs,
  },
  required: { ...typography.tiny, color: colors.amber, marginTop: spacing.sm, lineHeight: 16 },
  hint: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs, lineHeight: 16 },
  disclosure: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    marginBottom: spacing.xs,
  },
  disclosureText: { ...typography.bodyBold, color: colors.sub },
  subRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.md,
  },
  subLabel: { ...typography.caption, color: colors.text },
  subStars: { flexDirection: 'row', gap: spacing.xs },
  photoRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md },
  photoWrap: { position: 'relative' },
  photo: { width: 66, height: 66, borderRadius: radius.sm, backgroundColor: colors.surface },
  photoRemove: {
    position: 'absolute',
    top: -5,
    right: -5,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.borderMid,
    alignItems: 'center',
    justifyContent: 'center',
  },
  photoAdd: {
    width: 66,
    height: 66,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
  },
  footnote: {
    ...typography.tiny,
    color: colors.dim,
    lineHeight: 16,
    marginTop: spacing.sm,
  },
  bar: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
