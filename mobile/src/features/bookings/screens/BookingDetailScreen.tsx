import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate, formatPKR, timeAgo } from '../../../utils/format';
import type { BookingAction, BookingDetail } from '../../../types/models';
import { StatusPill } from '../components/StatusPill';
import {
  useAcceptBooking,
  useBookingDetail,
  useCancelBooking,
  useCompleteBooking,
  useRejectBooking,
} from '../hooks/useBookings';

/**
 * One booking, end to end.
 *
 * THE BUTTONS COME FROM THE SERVER
 * --------------------------------
 * `available_actions` is computed by the same state machine that enforces the
 * rules, so this screen never has to know that a photographer may accept but
 * not cancel a pending request, or that completion is blocked before the
 * event date. Reimplementing those rules in TypeScript would guarantee the
 * two drift, and a button that always errors is worse than no button.
 */
export function BookingDetailScreen({
  bookingId,
  perspective,
  onBack,
}: {
  bookingId: number;
  perspective: 'buyer' | 'photographer';
  onBack: () => void;
}) {
  const query = useBookingDetail(bookingId);
  const [prompt, setPrompt] = useState<'reject' | 'cancel' | null>(null);
  const [reason, setReason] = useState('');

  const accept = useAcceptBooking();
  const reject = useRejectBooking();
  const cancel = useCancelBooking();
  const complete = useCompleteBooking();

  const busy =
    accept.isPending || reject.isPending || cancel.isPending || complete.isPending;

  if (query.isLoading) return <LoadingState label="Loading booking…" />;
  if (query.isError || !query.data) {
    return (
      <ErrorState
        message={(query.error as ApiError)?.message}
        onRetry={() => query.refetch()}
      />
    );
  }

  const booking = query.data;
  const other = perspective === 'buyer' ? booking.photographer : booking.buyer;
  const otherPhone =
    perspective === 'buyer'
      ? booking.contact?.photographer_phone
      : booking.contact?.buyer_phone;

  const fail = (error: unknown) =>
    Alert.alert('Could not do that', (error as ApiError)?.message ?? 'Please try again.');

  const runAction = (action: BookingAction) => {
    if (action === 'accept') {
      accept.mutate({ id: bookingId }, { onError: fail });
      return;
    }
    if (action === 'complete') {
      Alert.alert(
        'Mark this shoot complete?',
        'Both of you will be able to leave a review afterwards. This cannot be undone.',
        [
          { text: 'Not yet', style: 'cancel' },
          {
            text: 'Mark complete',
            onPress: () => complete.mutate({ id: bookingId }, { onError: fail }),
          },
        ],
      );
      return;
    }
    // Reject and cancel both need words from the user, so they open a sheet
    // rather than firing straight away.
    setReason('');
    setPrompt(action === 'reject' ? 'reject' : 'cancel');
  };

  const submitPrompt = () => {
    const text = reason.trim();
    if (prompt === 'reject') {
      if (text.length < 5) {
        Alert.alert('A reason is required', 'Tell the buyer why, so they can rebook.');
        return;
      }
      reject.mutate(
        { id: bookingId, reason: text },
        { onSuccess: () => setPrompt(null), onError: fail },
      );
    } else {
      cancel.mutate(
        { id: bookingId, note: text },
        { onSuccess: () => setPrompt(null), onError: fail },
      );
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>{booking.reference}</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.statusRow}>
          <StatusPill status={booking.status} label={booking.status_label} />
          {booking.status === 'PENDING' ? (
            <Text style={styles.expiry}>
              Expires {formatDate(booking.expires_at)}
            </Text>
          ) : null}
        </View>

        {/* ─── The other party ─────────────────────────────────────────── */}
        <View style={styles.party}>
          <Avatar uri={other.avatar_url} name={other.name} size={52} />
          <View style={styles.partyBody}>
            <Text style={styles.partyName}>{other.name}</Text>
            <Text style={styles.partyMeta}>
              {perspective === 'buyer' ? 'Photographer' : 'Buyer'} · {other.city}
            </Text>
          </View>
          {otherPhone ? (
            <Pressable
              onPress={() => Linking.openURL(`tel:${otherPhone}`)}
              style={styles.callButton}
              accessibilityLabel={`Call ${other.name}`}
            >
              <Ionicons name="call-outline" size={18} color={colors.gold} />
            </Pressable>
          ) : null}
        </View>

        {booking.contact === null ? (
          <Text style={styles.privacyNote}>
            Phone numbers are shared once the booking is confirmed.
          </Text>
        ) : null}

        {/* ─── The shoot ───────────────────────────────────────────────── */}
        <Card title="The shoot">
          <Row icon="camera-outline" label="Service" value={booking.service_title} />
          <Row icon="pricetag-outline" label="Category" value={booking.category_name} />
          <Row
            icon="calendar-outline"
            label="Date"
            value={formatDate(booking.event_date)}
          />
          <Row
            icon="time-outline"
            label="Time"
            value={`${booking.start_time.slice(0, 5)}${
              booking.end_time ? ` – ${booking.end_time.slice(0, 5)}` : ''
            } · ${booking.duration_hours}h`}
          />
          <Row
            icon="location-outline"
            label="Venue"
            value={`${booking.location_address}, ${booking.location_city}`}
          />
          {booking.guest_count ? (
            <Row
              icon="people-outline"
              label="Guests"
              value={String(booking.guest_count)}
            />
          ) : null}
          {booking.notes ? (
            <Row icon="document-text-outline" label="Notes" value={booking.notes} />
          ) : null}
        </Card>

        {/* ─── Money ───────────────────────────────────────────────────── */}
        <Card title="Price">
          {booking.price_breakdown.map((line, index) => {
            const isTotal = index === booking.price_breakdown.length - 1;
            return (
              <View key={line.label} style={[styles.priceRow, isTotal && styles.priceTotal]}>
                <Text style={[styles.priceLabel, isTotal && styles.priceTotalText]}>
                  {line.label}
                </Text>
                <Text style={[styles.priceValue, isTotal && styles.priceTotalValue]}>
                  {formatPKR(line.amount)}
                </Text>
              </View>
            );
          })}
          {perspective === 'photographer' ? (
            <Text style={styles.payout}>
              Your payout after {booking.commission_percent}% platform fee:{' '}
              {formatPKR(booking.photographer_payout)}
            </Text>
          ) : null}
        </Card>

        {/* ─── Why it ended, when it did ───────────────────────────────── */}
        {booking.rejection_reason ? (
          <Card title="Why it was declined">
            <Text style={styles.reasonText}>{booking.rejection_reason}</Text>
          </Card>
        ) : null}
        {booking.cancellation_note ? (
          <Card title="Cancellation note">
            <Text style={styles.reasonText}>{booking.cancellation_note}</Text>
          </Card>
        ) : null}

        {/* ─── Timeline ────────────────────────────────────────────────── */}
        <Card title="History">
          {booking.timeline.map((entry, index) => (
            <View key={entry.id} style={styles.timelineRow}>
              <View style={styles.timelineMarker}>
                <View style={styles.timelineDot} />
                {index < booking.timeline.length - 1 ? (
                  <View style={styles.timelineLine} />
                ) : null}
              </View>
              <View style={styles.timelineBody}>
                <Text style={styles.timelineLabel}>{entry.label}</Text>
                <Text style={styles.timelineMeta}>
                  {entry.changed_by_name} · {timeAgo(entry.created_at)}
                </Text>
                {entry.note ? (
                  <Text style={styles.timelineNote}>{entry.note}</Text>
                ) : null}
              </View>
            </View>
          ))}
        </Card>
      </ScrollView>

      <ActionBar
        actions={booking.available_actions}
        busy={busy}
        onAction={runAction}
        booking={booking}
      />

      {/* ─── Reason sheet ──────────────────────────────────────────────── */}
      <Modal
        visible={prompt !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setPrompt(null)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>
              {prompt === 'reject' ? 'Decline this request' : 'Cancel this booking'}
            </Text>
            <Text style={styles.modalDetail}>
              {prompt === 'reject'
                ? 'The buyer sees this. Suggesting an alternative turns a dead end into a rebooking.'
                : 'Let the other person know what changed. This is kept on the booking record.'}
            </Text>

            <Input
              placeholder={
                prompt === 'reject'
                  ? "Already booked that morning, but the afternoon is free."
                  : 'Optional note'
              }
              value={reason}
              onChangeText={setReason}
              multiline
              numberOfLines={3}
            />

            <Button
              label={prompt === 'reject' ? 'Send decline' : 'Cancel booking'}
              variant="danger"
              onPress={submitPrompt}
              loading={reject.isPending || cancel.isPending}
            />
            <Button label="Never mind" variant="ghost" onPress={() => setPrompt(null)} />
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const ACTION_LABELS: Record<BookingAction, string> = {
  accept: 'Accept',
  reject: 'Decline',
  cancel: 'Cancel booking',
  complete: 'Mark complete',
  review: 'Leave a review',
};

function ActionBar({
  actions,
  busy,
  onAction,
  booking,
}: {
  actions: BookingAction[];
  busy: boolean;
  onAction: (action: BookingAction) => void;
  booking: BookingDetail;
}) {
  if (!actions.length) {
    return (
      <View style={styles.actionBar}>
        <Text style={styles.closedNote}>
          This booking is {booking.status_label.toLowerCase()} and can no longer be changed.
        </Text>
      </View>
    );
  }

  // "review" is Module 9's screen; it is surfaced but not yet wired.
  const usable = actions.filter((a) => a !== 'review');
  const primary = usable.find((a) => a === 'accept' || a === 'complete');
  const secondary = usable.filter((a) => a !== primary);

  return (
    <View style={styles.actionBar}>
      {primary ? (
        <Button
          label={ACTION_LABELS[primary]}
          onPress={() => onAction(primary)}
          loading={busy}
        />
      ) : null}
      <View style={styles.secondaryRow}>
        {secondary.map((action) => (
          <View key={action} style={styles.secondaryButton}>
            <Button
              label={ACTION_LABELS[action]}
              variant={action === 'reject' || action === 'cancel' ? 'danger' : 'secondary'}
              onPress={() => onAction(action)}
              disabled={busy}
            />
          </View>
        ))}
      </View>
    </View>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
}) {
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={16} color={colors.dim} style={styles.rowIcon} />
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
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
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerTitle: { ...typography.h3, color: colors.text },
  headerSpacer: { width: 24 },
  content: { padding: spacing.xl, paddingBottom: spacing.huge },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.lg,
  },
  expiry: { ...typography.caption, color: colors.amber },
  party: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  partyBody: { flex: 1 },
  partyName: { ...typography.h3, color: colors.text },
  partyMeta: { ...typography.caption, color: colors.sub },
  callButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.borderMid,
  },
  privacyNote: {
    ...typography.tiny,
    color: colors.dim,
    marginTop: spacing.sm,
    marginLeft: spacing.xs,
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginTop: spacing.lg,
  },
  cardTitle: {
    ...typography.caption,
    color: colors.sub,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.md,
  },
  row: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: spacing.md },
  rowIcon: { marginTop: 1, width: 22 },
  rowLabel: { ...typography.caption, color: colors.sub, width: 76 },
  rowValue: { ...typography.caption, color: colors.text, flex: 1, lineHeight: 20 },
  priceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  priceTotal: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
    marginTop: spacing.xs,
  },
  priceLabel: { ...typography.caption, color: colors.sub, flex: 1 },
  priceValue: { ...typography.caption, color: colors.text },
  priceTotalText: { ...typography.bodyBold, color: colors.text },
  priceTotalValue: { ...typography.bodyBold, color: colors.gold },
  payout: { ...typography.tiny, color: colors.green, marginTop: spacing.sm },
  reasonText: { ...typography.caption, color: colors.text, lineHeight: 20 },
  timelineRow: { flexDirection: 'row', gap: spacing.md },
  timelineMarker: { alignItems: 'center', width: 12 },
  timelineDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.gold,
    marginTop: 5,
  },
  timelineLine: { flex: 1, width: 1, backgroundColor: colors.border, marginVertical: 3 },
  timelineBody: { flex: 1, paddingBottom: spacing.lg },
  timelineLabel: { ...typography.bodyBold, color: colors.text },
  timelineMeta: { ...typography.tiny, color: colors.sub, marginTop: 1 },
  timelineNote: {
    ...typography.caption,
    color: colors.sub,
    marginTop: spacing.xs,
    fontStyle: 'italic',
  },
  actionBar: {
    padding: spacing.xl,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
    gap: spacing.sm,
  },
  secondaryRow: { flexDirection: 'row', gap: spacing.sm },
  secondaryButton: { flex: 1 },
  closedNote: { ...typography.caption, color: colors.dim, textAlign: 'center' },
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
