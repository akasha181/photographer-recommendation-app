import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuthStore } from '../../../store/authStore';
import { useBookingCounts, useUpcomingBookings } from '../../bookings/hooks/useBookings';
import { useMyProfile } from '../../shop/hooks/useShop';
import { colors, radius, spacing, typography } from '../../../theme';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import type { BookingSummary, PhotographerSelfProfile } from '../../../types/models';
import { formatDate, formatPKR } from '../../../utils/format';

export function DashboardScreen() {
  const user = useAuthStore((s) => s.user);
  const profile = useMyProfile();
  const counts = useBookingCounts();
  const upcomingBookings = useUpcomingBookings();

  const onRefresh = () => {
    profile.refetch();
    counts.refetch();
    upcomingBookings.refetch();
  };

  if (profile.isLoading || counts.isLoading) {
    return <LoadingState label="Loading your dashboard…" />;
  }

  if (profile.isError) {
    return (
      <ErrorState
        message={(profile.error as any)?.message}
        onRetry={() => onRefresh()}
      />
    );
  }

  const photographerProfile = profile.data as PhotographerSelfProfile | null;
  const upcomingList = upcomingBookings.data ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={profile.isRefetching || counts.isRefetching}
            onRefresh={onRefresh}
            tintColor={colors.gold}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Dashboard</Text>
          <Text style={styles.subtitle}>Welcome back, {user?.full_name}</Text>
        </View>

        {/* Stats Grid */}
        <View style={styles.statsGrid}>
          <StatCard
            icon="notifications-outline"
            label="Pending Requests"
            value={counts.data?.pending ?? 0}
            color={colors.amber}
          />
          <StatCard
            icon="calendar-outline"
            label="Upcoming"
            value={counts.data?.upcoming ?? 0}
            color={colors.blue}
          />
          <StatCard
            icon="checkmark-done-outline"
            label="Completed"
            value={counts.data?.completed ?? 0}
            color={colors.green}
          />
          <StatCard
            icon="close-circle-outline"
            label="Cancelled"
            value={counts.data?.cancelled ?? 0}
            color={colors.red}
          />
        </View>

        {/* Profile Stats */}
        {photographerProfile && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Profile Metrics</Text>
            <View style={styles.metricsCard}>
              <MetricRow
                icon="star-outline"
                label="Rating"
                value={`${photographerProfile.avg_rating}/5`}
                subtitle={`${photographerProfile.reviews_count} reviews`}
              />
              <View style={styles.divider} />
              <MetricRow
                icon="thumbs-up-outline"
                label="Success Rate"
                value={`${(parseFloat(photographerProfile.success_rate) * 100).toFixed(0)}%`}
              />
              <View style={styles.divider} />
              <MetricRow
                icon="briefcase-outline"
                label="Total Bookings"
                value={String(photographerProfile.completed_bookings)}
              />
              <View style={styles.divider} />
              <MetricRow
                icon="time-outline"
                label="Avg Response Time"
                value={`${parseFloat(photographerProfile.avg_response_time_hours).toFixed(1)}h`}
              />
            </View>
          </View>
        )}

        {/* Upcoming Shoots */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Upcoming Shoots</Text>
          {upcomingList.length > 0 ? (
            <View>
              {upcomingList.slice(0, 3).map((booking) => (
                <UpcomingShootCard key={booking.id} booking={booking} />
              ))}
            </View>
          ) : (
            <EmptyState
              icon="calendar-outline"
              title="No upcoming shoots"
              detail="You don't have any confirmed shoots scheduled."
            />
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function StatCard({
  icon,
  label,
  value,
  color,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <View style={styles.statCard}>
      <View style={[styles.statIcon, { backgroundColor: `${color}20` }]}>
        <Ionicons name={icon} size={24} color={color} />
      </View>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function MetricRow({
  icon,
  label,
  value,
  subtitle,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
  subtitle?: string;
}) {
  return (
    <View style={styles.metricRow}>
      <View style={styles.metricIcon}>
        <Ionicons name={icon} size={20} color={colors.gold} />
      </View>
      <View style={styles.metricContent}>
        <Text style={styles.metricLabel}>{label}</Text>
        {subtitle ? (
          <Text style={styles.metricSubtitle}>{subtitle}</Text>
        ) : null}
      </View>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function UpcomingShootCard({ booking }: { booking: BookingSummary }) {
  return (
    <View style={styles.shootCard}>
      <View style={styles.shootCardTop}>
        <View style={styles.shootInfo}>
          <Text style={styles.shootDate}>{formatDate(booking.event_date)}</Text>
          <Text style={styles.shootTime}>
            {booking.start_time.slice(0, 5)} · {booking.duration_hours}h
          </Text>
        </View>
        <Text style={styles.shootPrice}>{formatPKR(booking.total_price)}</Text>
      </View>
      <View style={styles.shootCardBottom}>
        <View>
          <Text style={styles.shootClient}>{booking.buyer.name}</Text>
          <Text style={styles.shootService} numberOfLines={1}>
            {booking.service_title}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color={colors.dim} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: { paddingBottom: spacing.xxl },

  header: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
  },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub, marginTop: 2 },

  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: spacing.xl,
    marginBottom: spacing.lg,
    gap: spacing.md,
  },
  statCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    alignItems: 'center',
  },
  statIcon: {
    width: 48,
    height: 48,
    borderRadius: radius.lg,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  statValue: {
    ...typography.h2,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  statLabel: {
    ...typography.caption,
    color: colors.sub,
    textAlign: 'center',
  },

  section: {
    paddingHorizontal: spacing.xl,
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    ...typography.bodyBold,
    color: colors.text,
    marginBottom: spacing.md,
  },

  metricsCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  metricRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  metricIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  metricContent: {
    flex: 1,
  },
  metricLabel: {
    ...typography.caption,
    color: colors.sub,
  },
  metricSubtitle: {
    ...typography.tiny,
    color: colors.dim,
    marginTop: 2,
  },
  metricValue: {
    ...typography.bodyBold,
    color: colors.text,
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.md,
  },

  shootCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  shootCardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  shootInfo: {},
  shootDate: {
    ...typography.bodyBold,
    color: colors.text,
  },
  shootTime: {
    ...typography.caption,
    color: colors.sub,
    marginTop: 2,
  },
  shootPrice: {
    ...typography.h3,
    color: colors.gold,
  },
  shootCardBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  shootClient: {
    ...typography.bodyBold,
    color: colors.text,
  },
  shootService: {
    ...typography.caption,
    color: colors.sub,
    marginTop: 2,
  },
});
