import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { colors, radius, spacing, typography } from '../../../theme';
import { timeAgo } from '../../../utils/format';
import type { Notification, NotificationCategory } from '../../../types/models';
import {
  useClearNotifications,
  useDeleteNotification,
  useMarkRead,
  useNotifications,
  useUnreadBadge,
} from '../hooks/useNotifications';

const CHIPS: { key?: NotificationCategory; label: string }[] = [
  { label: 'All' },
  { key: 'bookings', label: 'Bookings' },
  { key: 'messages', label: 'Messages' },
  { key: 'reviews', label: 'Reviews' },
  { key: 'marketplace', label: 'Shop' },
  { key: 'account', label: 'Account' },
];

const ICONS: Record<NotificationCategory, keyof typeof Ionicons.glyphMap> = {
  bookings: 'calendar-outline',
  messages: 'chatbubble-outline',
  reviews: 'star-outline',
  marketplace: 'bag-handle-outline',
  account: 'person-circle-outline',
  platform: 'megaphone-outline',
};

/**
 * The bell.
 *
 * WHY OPENING THE SCREEN DOES NOT CLEAR THE BADGE
 * ----------------------------------------------
 * Glancing at a list is not reading it. Auto-clearing on open means the badge
 * disappears and the user can no longer find what it was about — so tapping a
 * row marks that one, and "Mark all read" is an explicit button.
 *
 * WHY EVERY ROW IS A DEEP LINK BUILT FROM DATA
 * -------------------------------------------
 * `action_screen` + `action_id` come from the server as a structured pair, so
 * this screen routes to `BookingDetail(42)` without parsing meaning out of the
 * notification text. A copy edit upstream cannot break navigation.
 */
export function NotificationsScreen({
  onBack,
  onOpenBooking,
  onOpenChat,
  onOpenReviews,
  onOpenProduct,
  onOpenPreferences,
}: {
  onBack: () => void;
  onOpenBooking?: (bookingId: number) => void;
  onOpenChat?: (conversationId: number) => void;
  onOpenReviews?: () => void;
  onOpenProduct?: (slug: string) => void;
  onOpenPreferences?: () => void;
}) {
  const [category, setCategory] = useState<NotificationCategory | undefined>();
  const notifications = useNotifications({ category });
  const badge = useUnreadBadge();
  const markRead = useMarkRead();
  const remove = useDeleteNotification();
  const clear = useClearNotifications();

  const rows = notifications.data?.items ?? [];
  const unread = badge.data?.total ?? 0;

  const open = (row: Notification) => {
    if (!row.is_read) markRead.mutate([row.id]);

    const id = Number(row.action_id);
    switch (row.action_screen) {
      case 'BookingDetail':
        if (onOpenBooking && Number.isFinite(id)) onOpenBooking(id);
        return;
      case 'Chat':
        if (onOpenChat && Number.isFinite(id)) onOpenChat(id);
        return;
      case 'ReviewDetail':
      case 'WriteReview':
        onOpenReviews?.();
        return;
      case 'ProductDetail':
        if (onOpenProduct && row.action_id) onOpenProduct(row.action_id);
        return;
      default:
        // A notification with no route is still worth showing — an
        // announcement, an account decision. Tapping it just marks it read.
        return;
    }
  };

  const confirmClear = () =>
    Alert.alert(
      'Clear read notifications?',
      'Anything still unread stays — including booking changes you have not seen.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Clear',
          onPress: () =>
            clear.mutate(undefined, {
              onError: (error) =>
                Alert.alert('Could not clear', (error as ApiError).message),
            }),
        },
      ],
    );

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <View style={styles.headerBody}>
          <Text style={styles.title}>Notifications</Text>
          <Text style={styles.subtitle}>
            {unread ? `${unread} unread` : 'You are all caught up'}
          </Text>
        </View>
        {onOpenPreferences ? (
          <Pressable
            onPress={onOpenPreferences}
            hitSlop={10}
            accessibilityLabel="Notification settings"
          >
            <Ionicons name="options-outline" size={21} color={colors.sub} />
          </Pressable>
        ) : null}
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipStrip}
        contentContainerStyle={styles.chipRow}
      >
        {CHIPS.map((chip) => {
          const active = chip.key === category;
          return (
            <Pressable
              key={chip.label}
              onPress={() => setCategory(chip.key)}
              style={[styles.chip, active && styles.chipOn]}
            >
              <Text style={[styles.chipText, active && styles.chipTextOn]}>
                {chip.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {rows.length ? (
        <View style={styles.bulkRow}>
          {unread ? (
            <Pressable onPress={() => markRead.mutate(undefined)} hitSlop={8}>
              <Text style={styles.bulkAction}>Mark all read</Text>
            </Pressable>
          ) : (
            <View />
          )}
          <Pressable onPress={confirmClear} hitSlop={8}>
            <Text style={styles.bulkActionDim}>Clear read</Text>
          </Pressable>
        </View>
      ) : null}

      {notifications.isLoading ? (
        <LoadingState label="Loading notifications…" />
      ) : notifications.isError ? (
        <ErrorState
          message={(notifications.error as ApiError)?.message}
          onRetry={() => notifications.refetch()}
        />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <NotificationRow
              row={item}
              onPress={() => open(item)}
              onDismiss={() => remove.mutate(item.id)}
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="notifications-off-outline"
              title="Nothing here yet"
              detail="Booking updates, messages and review activity land here."
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={notifications.isRefetching}
              onRefresh={() => {
                notifications.refetch();
                badge.refetch();
              }}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

function NotificationRow({
  row,
  onPress,
  onDismiss,
}: {
  row: Notification;
  onPress: () => void;
  onDismiss: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.row, !row.is_read && styles.rowUnread]}
      accessibilityRole="button"
      accessibilityLabel={`${row.title}. ${row.body}`}
    >
      {row.actor_name ? (
        <Avatar name={row.actor_name} uri={row.actor_avatar} size={38} />
      ) : (
        <View style={styles.iconCircle}>
          <Ionicons
            name={ICONS[row.category] ?? 'notifications-outline'}
            size={18}
            color={colors.gold}
          />
        </View>
      )}

      <View style={styles.rowBody}>
        <Text style={styles.rowTitle} numberOfLines={2}>
          {row.title}
        </Text>
        <Text style={styles.rowText} numberOfLines={2}>
          {row.body}
        </Text>
        <Text style={styles.rowTime}>{timeAgo(row.created_at)}</Text>
      </View>

      <View style={styles.rowRight}>
        {!row.is_read ? <View style={styles.unreadDot} /> : null}
        <Pressable
          onPress={onDismiss}
          hitSlop={10}
          accessibilityLabel="Remove notification"
        >
          <Ionicons name="close" size={16} color={colors.dim} />
        </Pressable>
      </View>
    </Pressable>
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
    paddingBottom: spacing.md,
  },
  headerBody: { flex: 1 },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  chipStrip: { maxHeight: 44 },
  chipRow: { paddingHorizontal: spacing.xl, gap: spacing.sm, paddingBottom: spacing.sm },
  chip: {
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  chipOn: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { ...typography.tiny, color: colors.sub },
  chipTextOn: { color: colors.bg },
  bulkRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
  },
  bulkAction: { ...typography.tiny, color: colors.gold },
  bulkActionDim: { ...typography.tiny, color: colors.dim },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl },
  listEmpty: { flexGrow: 1 },
  row: {
    flexDirection: 'row',
    gap: spacing.md,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  rowUnread: { borderColor: colors.goldDim, backgroundColor: colors.cardHover },
  iconCircle: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowBody: { flex: 1 },
  rowTitle: { ...typography.bodyBold, color: colors.text },
  rowText: { ...typography.caption, color: colors.sub, marginTop: 1, lineHeight: 18 },
  rowTime: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs },
  rowRight: { alignItems: 'center', gap: spacing.md },
  unreadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.gold },
});
