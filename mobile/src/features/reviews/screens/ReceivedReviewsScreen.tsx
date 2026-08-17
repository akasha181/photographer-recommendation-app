import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { colors, radius, spacing, typography } from '../../../theme';
import type { OwnedReview } from '../../../types/models';
import { ReviewCard } from '../components/ReviewCard';
import { useReceivedReviews, useReplyToReview } from '../hooks/useReviews';

/**
 * The photographer's review inbox.
 *
 * WHY "NEEDS A REPLY" IS THE DEFAULT FILTER OFF, NOT ON
 * ---------------------------------------------------
 * A photographer with 300 reviews and none answered would open a screen showing
 * everything and read it as a backlog; one with the filter forced on and nothing
 * outstanding would see an empty screen and read it as "no reviews". So the list
 * opens complete, with the outstanding count stated above it — the same lesson
 * the Bookings tab taught when it defaulted to an empty group.
 *
 * WHY A REPLY IS ONE SHOT AND EDITABLE
 * -----------------------------------
 * A review is not a comment thread (see `reviews/models.py`) — an unbounded
 * public back-and-forth turns a dispute into a spectacle. Editing is allowed
 * because a reply written badly under pressure should be improvable; the review
 * above it, by contrast, freezes the moment a reply exists.
 */
export function ReceivedReviewsScreen({ onBack }: { onBack: () => void }) {
  const [unansweredOnly, setUnansweredOnly] = useState(false);
  const [replyTo, setReplyTo] = useState<OwnedReview | null>(null);
  const [draft, setDraft] = useState('');

  const reviews = useReceivedReviews(unansweredOnly);
  const reply = useReplyToReview();

  const openReply = (review: OwnedReview) => {
    setReplyTo(review);
    setDraft(review.reply?.comment ?? '');
  };

  const submitReply = () => {
    if (!replyTo) return;
    const comment = draft.trim();
    if (comment.length < 2) {
      Alert.alert('Write something first', 'A blank reply says nothing to the buyer.');
      return;
    }
    reply.mutate(
      { id: replyTo.id, comment, editing: Boolean(replyTo.reply) },
      {
        onSuccess: () => setReplyTo(null),
        onError: (error) =>
          Alert.alert('Could not post the reply', (error as ApiError).message),
      },
    );
  };

  const rows = reviews.data ?? [];
  const outstanding = (reviews.data ?? []).filter((row) => !row.reply).length;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <View style={styles.headerBody}>
          <Text style={styles.title}>Your reviews</Text>
          <Text style={styles.subtitle}>
            {unansweredOnly
              ? 'Only the ones you have not answered'
              : outstanding
                ? `${outstanding} still waiting for a reply`
                : 'All caught up on replies'}
          </Text>
        </View>
        <Pressable
          onPress={() => setUnansweredOnly((on) => !on)}
          style={[styles.filter, unansweredOnly && styles.filterOn]}
          accessibilityRole="button"
          accessibilityLabel="Show only unanswered reviews"
        >
          <Ionicons
            name="chatbubble-ellipses-outline"
            size={16}
            color={unansweredOnly ? colors.bg : colors.sub}
          />
        </Pressable>
      </View>

      {reviews.isLoading ? (
        <LoadingState label="Loading reviews…" />
      ) : reviews.isError ? (
        <ErrorState
          message={(reviews.error as ApiError)?.message}
          onRetry={() => reviews.refetch()}
        />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <ReviewCard review={item} onReply={() => openReply(item)} />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="star-outline"
              title={unansweredOnly ? 'Nothing unanswered' : 'No reviews yet'}
              detail={
                unansweredOnly
                  ? 'Every review you have received has a reply.'
                  : 'Buyers can review a shoot once you mark it complete. Replying to the first few is what makes a profile feel run by a person.'
              }
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={reviews.isRefetching}
              onRefresh={() => reviews.refetch()}
              tintColor={colors.gold}
            />
          }
        />
      )}

      <Modal
        visible={replyTo !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setReplyTo(null)}
      >
        <View style={styles.backdrop}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>
              {replyTo?.reply ? 'Edit your reply' : 'Reply publicly'}
            </Text>
            <Text style={styles.sheetDetail}>
              Everyone browsing your profile sees this. Answering a hard review well
              persuades more buyers than the review itself puts off.
            </Text>

            {replyTo ? (
              <View style={styles.quote}>
                <Text style={styles.quoteStars}>{'★'.repeat(replyTo.rating)}</Text>
                <Text style={styles.quoteText} numberOfLines={3}>
                  {replyTo.comment || replyTo.title || 'No comment left.'}
                </Text>
              </View>
            ) : null}

            <TextInput
              value={draft}
              onChangeText={setDraft}
              placeholder="Thank you for the kind words — it was a pleasure to shoot."
              placeholderTextColor={colors.dim}
              multiline
              maxLength={2000}
              style={styles.input}
            />

            <View style={styles.sheetActions}>
              <View style={styles.sheetButton}>
                <Button
                  label="Cancel"
                  variant="secondary"
                  onPress={() => setReplyTo(null)}
                />
              </View>
              <View style={styles.sheetButton}>
                <Button
                  label={replyTo?.reply ? 'Save' : 'Post reply'}
                  onPress={submitReply}
                  loading={reply.isPending}
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
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
  },
  headerBody: { flex: 1 },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  filter: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterOn: { backgroundColor: colors.gold, borderColor: colors.gold },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl },
  listEmpty: { flexGrow: 1 },
  backdrop: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.xl,
    paddingBottom: spacing.xxxl,
  },
  sheetTitle: { ...typography.h2, color: colors.text },
  sheetDetail: {
    ...typography.caption,
    color: colors.sub,
    lineHeight: 18,
    marginTop: spacing.xs,
  },
  quote: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  quoteStars: { ...typography.caption, color: colors.gold },
  quoteText: { ...typography.caption, color: colors.sub, marginTop: 2, lineHeight: 18 },
  input: {
    ...typography.body,
    color: colors.text,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    minHeight: 100,
    textAlignVertical: 'top',
    marginTop: spacing.lg,
  },
  sheetActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.lg },
  sheetButton: { flex: 1 },
});
