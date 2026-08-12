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
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate, formatPKR, timeAgo } from '../../../utils/format';
import type { BookingSummary } from '../../../types/models';
import {
  useAcceptBooking,
  useBookingCounts,
  useBookings,
  useRejectBooking,
} from '../hooks/useBookings';

/**
 * The photographer's triage screen.
 *
 * WHY THIS IS NOT JUST THE BOOKINGS LIST WITH A FILTER
 * ----------------------------------------------------
 * A pending request is the only thing in this app with a deadline: it expires
 * in 48 hours and takes the calendar slot with it. Accepting has to be one
 * tap from the list, not one tap to open a detail screen and another to act.
 * The decline path deliberately costs more — it opens a sheet and demands a
 * reason, because a bare "declined" leaves the buyer with nothing to do next.
 */
export function RequestsScreen({
  onOpenBooking,
}: {
  onOpenBooking: (bookingId: number) => void;
}) {
  const requests = useBookings('pending');
  const counts = useBookingCounts();

  const accept = useAcceptBooking();
  const reject = useRejectBooking();

  const [declining, setDeclining] = useState<BookingSummary | null>(null);
  const [reason, setReason] = useState('');

  const rows = requests.data?.pages.flatMap((page) => page.items) ?? [];
  const fail = (error: unknown) =>
    Alert.alert('Could not do that', (error as ApiError)?.message ?? 'Please try again.');

  const confirmAccept = (booking: BookingSummary) => {
    Alert.alert(
      'Accept this booking?',
      `${formatDate(booking.event_date)} at ${booking.start_time.slice(0, 5)} — ` +
        `${booking.location_city}. The date will be blocked on your calendar.`,
      [
        { text: 'Not now', style: 'cancel' },
        {
          text: 'Accept',
          onPress: () => accept.mutate({ id: booking.id }, { onError: fail }),
        },
      ],
    );
  };

  const submitDecline = () => {
    if (!declining) return;
    if (reason.trim().length < 5) {
      Alert.alert('A reason is required', 'Tell the buyer why, so they can rebook.');
      return;
    }
    reject.mutate(
      { id: declining.id, reason: reason.trim() },
      {
        onSuccess: () => {
          setDeclining(null);
          setReason('');
        },
        onError: fail,
      },
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Text style={styles.title}>Requests</Text>
        <Text style={styles.subtitle}>
          {counts.data?.pending
            ? `${counts.data.pending} waiting for your reply`
            : 'Nothing waiting on you'}
        </Text>
      </View>

      {requests.isLoading ? (
        <LoadingState label="Loading requests…" />
      ) : requests.isError ? (
        <ErrorState
          message={(requests.error as ApiError)?.message}
          onRetry={() => requests.refetch()}
        />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <RequestCard
              booking={item}
              busy={accept.isPending || reject.isPending}
              onOpen={() => onOpenBooking(item.id)}
              onAccept={() => confirmAccept(item)}
              onDecline={() => {
                setReason('');
                setDeclining(item);
              }}
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="checkmark-done-outline"
              title="All caught up"
              detail="New booking requests appear here. You have 48 hours to reply before they expire."
            />
          }
          onEndReachedThreshold={0.4}
          onEndReached={() => {
            if (requests.hasNextPage && !requests.isFetchingNextPage) {
              requests.fetchNextPage();
            }
          }}
          refreshControl={
            <RefreshControl
              refreshing={requests.isRefetching && !requests.isFetchingNextPage}
              onRefresh={() => {
                requests.refetch();
                counts.refetch();
              }}
              tintColor={colors.gold}
            />
          }
        />
      )}

      <Modal
        visible={declining !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setDeclining(null)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>Decline this request</Text>
            <Text style={styles.modalDetail}>
              {declining?.buyer.name} will see this. Suggesting an alternative date
              turns a dead end into a rebooking.
            </Text>
            <Input
              placeholder="Already booked that morning, but the afternoon is free."
              value={reason}
              onChangeText={setReason}
              multiline
              numberOfLines={3}
            />
            <Button
              label="Send decline"
              variant="danger"
              onPress={submitDecline}
              loading={reject.isPending}
            />
            <Button label="Never mind" variant="ghost" onPress={() => setDeclining(null)} />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function RequestCard({
  booking,
  busy,
  onOpen,
  onAccept,
  onDecline,
}: {
  booking: BookingSummary;
  busy: boolean;
  onOpen: () => void;
  onAccept: () => void;
  onDecline: () => void;
}) {
  return (
    <View style={styles.card}>
      <Pressable onPress={onOpen} accessibilityRole="button" style={styles.cardTop}>
        <Avatar uri={booking.buyer.avatar_url} name={booking.buyer.name} size={44} />
        <View style={styles.cardBody}>
          <Text style={styles.buyerName}>{booking.buyer.name}</Text>
          <Text style={styles.service} numberOfLines={1}>
            {booking.service_title}
          </Text>
          <Text style={styles.requested}>Requested {timeAgo(booking.created_at)}</Text>
        </View>
        <Text style={styles.price}>{formatPKR(booking.total_price)}</Text>
      </Pressable>

      <View style={styles.facts}>
        <Fact icon="calendar-outline" text={formatDate(booking.event_date)} />
        <Fact
          icon="time-outline"
          text={`${booking.start_time.slice(0, 5)} · ${booking.duration_hours}h`}
        />
        <Fact icon="location-outline" text={booking.location_city} />
      </View>

      <View style={styles.actions}>
        <View style={styles.actionButton}>
          <Button label="Decline" variant="danger" onPress={onDecline} disabled={busy} />
        </View>
        <View style={styles.actionButton}>
          <Button label="Accept" onPress={onAccept} disabled={busy} />
        </View>
      </View>
    </View>
  );
}

function Fact({
  icon,
  text,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  text: string;
}) {
  return (
    <View style={styles.fact}>
      <Ionicons name={icon} size={13} color={colors.sub} />
      <Text style={styles.factText} numberOfLines={1}>
        {text}
      </Text>
    </View>
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
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  cardBody: { flex: 1 },
  buyerName: { ...typography.bodyBold, color: colors.text },
  service: { ...typography.caption, color: colors.sub },
  requested: { ...typography.tiny, color: colors.dim, marginTop: 2 },
  price: { ...typography.bodyBold, color: colors.gold },
  facts: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  fact: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  factText: { ...typography.caption, color: colors.sub },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg },
  actionButton: { flex: 1 },
  modalBackdrop: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.xl,
    paddingBottom: spacing.xxxl,
    gap: spacing.sm,
  },
  modalTitle: { ...typography.h2, color: colors.text },
  modalDetail: {
    ...typography.caption,
    color: colors.sub,
    marginBottom: spacing.md,
    lineHeight: 19,
  },
});
