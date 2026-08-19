import React, { useState } from 'react';
import {
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
import { colors, radius, spacing, typography } from '../../../theme';
import type { BookingGroup, BookingSummary } from '../../../types/models';
import { BookingCard } from '../components/BookingCard';
import { useBookingCounts, useBookings } from '../hooks/useBookings';

/**
 * The Bookings tab.
 *
 * Serves both roles: a buyer sees the photographers they booked, a
 * photographer sees the buyers who booked them. The tab labels differ because
 * "Requests" and "My bookings" mean different things depending on which side
 * of the transaction you are on, but the data and the card are identical.
 */
const TABS: { key: BookingGroup; buyerLabel: string; photographerLabel: string }[] = [
  { key: 'pending', buyerLabel: 'Pending', photographerLabel: 'Requests' },
  { key: 'upcoming', buyerLabel: 'Upcoming', photographerLabel: 'Confirmed' },
  { key: 'completed', buyerLabel: 'Completed', photographerLabel: 'Completed' },
  { key: 'cancelled', buyerLabel: 'Cancelled', photographerLabel: 'Cancelled' },
];

const EMPTY_COPY: Record<BookingGroup, { title: string; detail: string }> = {
  pending: {
    title: 'No pending requests',
    detail: 'Requests waiting for a reply appear here.',
  },
  upcoming: {
    title: 'Nothing confirmed yet',
    detail: 'Accepted bookings show up here with the countdown to the shoot.',
  },
  completed: {
    title: 'No completed shoots',
    detail: 'Finished bookings move here, ready for a review.',
  },
  cancelled: {
    title: 'Nothing cancelled',
    detail: 'Cancelled, declined and expired requests are kept here.',
  },
};

/** Pending wins when non-empty — it is the only group with a deadline. */
function firstNonEmpty(counts: Record<BookingGroup, number>): BookingGroup {
  const order: BookingGroup[] = ['pending', 'upcoming', 'completed', 'cancelled'];
  return order.find((key) => counts[key] > 0) ?? 'pending';
}

export function BookingsScreen({
  perspective,
  onOpenBooking,
  onBrowse,
}: {
  perspective: 'buyer' | 'photographer';
  onOpenBooking: (bookingId: number) => void;
  onBrowse?: () => void;
}) {
  const [group, setGroup] = useState<BookingGroup | null>(null);

  const counts = useBookingCounts();

  /**
   * Land on a tab that has something in it.
   *
   * Defaulting to "pending" opened an empty screen for an established
   * photographer with 410 completed shoots and nothing awaiting a reply —
   * which reads as "this app has no data for me" rather than "you're all
   * caught up". Pending still wins when it is non-empty, because an
   * unanswered request is the only thing here with a deadline.
   *
   * Once the user picks a tab, their choice sticks: `group` stays null only
   * until the counts arrive.
   */
  const activeGroup: BookingGroup =
    group ?? (counts.data ? firstNonEmpty(counts.data) : 'pending');

  const bookings = useBookings(activeGroup);

  const rows: BookingSummary[] =
    bookings.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Text style={styles.title}>
          {perspective === 'buyer' ? 'My bookings' : 'Bookings'}
        </Text>
        {counts.data ? (
          <Text style={styles.subtitle}>
            {counts.data.total} total · {counts.data.upcoming} upcoming
          </Text>
        ) : null}
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.tabs}
        style={styles.tabsWrap}
      >
        {TABS.map((tab) => {
          const active = tab.key === activeGroup;
          const count = counts.data?.[tab.key] ?? 0;
          return (
            <Pressable
              key={tab.key}
              onPress={() => setGroup(tab.key)}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              style={[styles.tab, active && styles.tabActive]}
            >
              <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>
                {perspective === 'buyer' ? tab.buyerLabel : tab.photographerLabel}
              </Text>
              {count > 0 ? (
                <View style={[styles.badge, active && styles.badgeActive]}>
                  <Text style={[styles.badgeText, active && styles.badgeTextActive]}>
                    {count}
                  </Text>
                </View>
              ) : null}
            </Pressable>
          );
        })}
      </ScrollView>

      {bookings.isLoading ? (
        <LoadingState label="Loading bookings…" />
      ) : bookings.isError ? (
        <ErrorState
          message={(bookings.error as ApiError)?.message}
          onRetry={() => bookings.refetch()}
        />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <BookingCard
              booking={item}
              perspective={perspective}
              onPress={() => onOpenBooking(item.id)}
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="calendar-outline"
              title={EMPTY_COPY[activeGroup].title}
              detail={EMPTY_COPY[activeGroup].detail}
              actionLabel={
                perspective === 'buyer' && activeGroup === 'pending'
                  ? 'Find a photographer'
                  : undefined
              }
              onAction={
                perspective === 'buyer' && activeGroup === 'pending' ? onBrowse : undefined
              }
            />
          }
          onEndReachedThreshold={0.4}
          onEndReached={() => {
            if (bookings.hasNextPage && !bookings.isFetchingNextPage) {
              bookings.fetchNextPage();
            }
          }}
          refreshControl={
            <RefreshControl
              refreshing={bookings.isRefetching && !bookings.isFetchingNextPage}
              onRefresh={() => {
                bookings.refetch();
                counts.refetch();
              }}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: spacing.xl, paddingTop: spacing.md },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub, marginTop: 2 },
  tabsWrap: { flexGrow: 0, marginTop: spacing.lg },
  tabs: { paddingHorizontal: spacing.xl, gap: spacing.sm },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  tabActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  tabLabel: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  tabLabelActive: { color: colors.bg },
  badge: {
    minWidth: 20,
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    alignItems: 'center',
  },
  badgeActive: { backgroundColor: colors.bg },
  badgeText: { ...typography.tiny, color: colors.sub },
  badgeTextActive: { color: colors.gold },
  list: { padding: spacing.xl, paddingTop: spacing.lg },
  listEmpty: { flexGrow: 1 },
});
