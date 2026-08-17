import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { useAuthStore } from '../../../store/authStore';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate, formatPKR, formatPKRShort } from '../../../utils/format';
import type {
  CategorySplit,
  Funnel,
  RevenuePoint,
  TopService,
} from '../../../types/models';
import { useChatUnreadTotal } from '../../chat/hooks/useChat';
import { NotificationBell } from '../../notifications/components/NotificationBell';
import { useDashboard } from '../hooks/useMyStudio';

/**
 * The photographer's Dashboard — Module 15.
 *
 * WHY THE CHARTS ARE PLAIN VIEWS
 * ------------------------------
 * No chart library. This project is pinned to Expo SDK 54 (see
 * mobile/AGENTS.md) and adding a charting dependency risks the native-module
 * compatibility that pin exists to protect. A bar is a `View` with a height,
 * and these charts are bars — the library would buy nothing here and could
 * cost the whole build.
 *
 * Every number is pre-computed server-side: rates, month labels, and the
 * gap-filled series. This screen does no arithmetic on money and no date
 * maths, which is exactly the split that keeps currency correct.
 */
export function DashboardScreen({
  onOpenRequests,
  onOpenJobs,
  onOpenServices,
  onOpenNotifications,
  onOpenMessages,
  onOpenReviews,
}: {
  onOpenRequests: () => void;
  onOpenJobs: () => void;
  onOpenServices: () => void;
  /** Header entry points — kept out of the tab bar, see PhotographerNavigator. */
  onOpenNotifications?: () => void;
  onOpenMessages?: () => void;
  onOpenReviews?: () => void;
}) {
  const user = useAuthStore((s) => s.user);
  const dashboard = useDashboard(30, 6);
  const chatUnread = useChatUnreadTotal();

  if (dashboard.isLoading) return <LoadingState label="Crunching your numbers…" />;
  if (dashboard.isError || !dashboard.data) {
    return (
      <ErrorState
        message={(dashboard.error as ApiError)?.message}
        onRetry={() => dashboard.refetch()}
      />
    );
  }

  const { overview, revenue_series, funnel, top_services, category_split, upcoming } =
    dashboard.data;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={dashboard.isRefetching}
            onRefresh={() => dashboard.refetch()}
            tintColor={colors.gold}
          />
        }
      >
        <View style={styles.topRow}>
          <View style={styles.topText}>
            <Text style={styles.greeting}>{greeting()},</Text>
            <Text style={styles.name}>{user?.full_name}</Text>
          </View>
          <View style={styles.topActions}>
            {onOpenReviews ? (
              <NotificationBell
                onPress={onOpenReviews}
                icon="star-outline"
                // No badge: "reviews received" is not a queue with a deadline,
                // and a permanent number beside it would read as unread mail.
                count={0}
              />
            ) : null}
            {onOpenMessages ? (
              <NotificationBell
                onPress={onOpenMessages}
                icon="chatbubbles-outline"
                count={chatUnread.data?.unread_total ?? 0}
              />
            ) : null}
            {onOpenNotifications ? (
              <NotificationBell onPress={onOpenNotifications} />
            ) : null}
          </View>
        </View>

        {!overview.is_accepting_bookings ? (
          <View style={styles.paused}>
            <Ionicons name="pause-circle-outline" size={16} color={colors.amber} />
            <Text style={styles.pausedText}>
              You are not accepting bookings — buyers cannot request dates.
            </Text>
          </View>
        ) : null}

        {/* ─── Needs you now ───────────────────────────────────────────── */}
        <View style={styles.actionRow}>
          <ActionTile
            icon="notifications-outline"
            value={overview.pending_requests}
            label={overview.pending_requests === 1 ? 'request' : 'requests'}
            hint="awaiting your reply"
            urgent={overview.pending_requests > 0}
            onPress={onOpenRequests}
          />
          <ActionTile
            icon="calendar-outline"
            value={overview.upcoming_shoots}
            label={overview.upcoming_shoots === 1 ? 'shoot' : 'shoots'}
            hint="confirmed ahead"
            onPress={onOpenJobs}
          />
        </View>

        {/* ─── Lifetime ────────────────────────────────────────────────── */}
        <View style={styles.earningsCard}>
          <Text style={styles.earningsLabel}>Lifetime earnings</Text>
          <Text style={styles.earningsValue}>
            {formatPKR(overview.lifetime_earnings)}
          </Text>
          <View style={styles.earningsMeta}>
            <Text style={styles.earningsMetaText}>
              {formatPKR(overview.earnings_this_month)} this month
            </Text>
            <Text style={styles.earningsMetaText}>
              {overview.completed_shoots} shoots delivered
            </Text>
          </View>
        </View>

        {/* ─── Quality ─────────────────────────────────────────────────── */}
        <View style={styles.statRow}>
          <Stat
            value={Number(overview.avg_rating).toFixed(1)}
            label={`from ${overview.reviews_count} reviews`}
            icon="star"
            tint={colors.gold}
          />
          <Stat
            value={`${Math.round(Number(overview.success_rate) * 100)}%`}
            label="completed"
            icon="checkmark-circle"
            tint={colors.green}
          />
          <Stat
            value={responseLabel(Number(overview.response_time_hours))}
            label="to reply"
            icon="time"
            tint={colors.blue}
          />
        </View>

        {/* ─── Revenue chart ───────────────────────────────────────────── */}
        <Section
          title="Earnings"
          hint="Net of the platform fee, by the month each shoot completed"
        >
          <RevenueChart points={revenue_series} />
        </Section>

        {/* ─── Funnel ──────────────────────────────────────────────────── */}
        <Section
          title="How buyers found you"
          hint={`Last ${funnel.days} days`}
        >
          <FunnelChart funnel={funnel} />
        </Section>

        {/* ─── Top services ────────────────────────────────────────────── */}
        {top_services.length ? (
          <Section title="Your best sellers" hint="Ranked by what they earned">
            {top_services.map((service, index) => (
              <ServiceRow key={service.service_id} service={service} rank={index + 1} />
            ))}
          </Section>
        ) : (
          <Section title="Your best sellers">
            <Pressable onPress={onOpenServices} style={styles.emptyAction}>
              <Ionicons name="add-circle-outline" size={18} color={colors.gold} />
              <Text style={styles.emptyActionText}>
                No bookings yet — add a service so buyers have something to book.
              </Text>
            </Pressable>
          </Section>
        )}

        {/* ─── Category split ──────────────────────────────────────────── */}
        {category_split.length ? (
          <Section title="Where the work comes from">
            <CategoryBars rows={category_split} />
          </Section>
        ) : null}

        {/* ─── Upcoming ────────────────────────────────────────────────── */}
        {upcoming.length ? (
          <Section title="Next up">
            {upcoming.map((booking) => (
              <Pressable key={booking.id} onPress={onOpenJobs} style={styles.upcomingRow}>
                <View style={styles.upcomingDate}>
                  <Text style={styles.upcomingDay}>
                    {new Date(`${booking.event_date}T00:00:00`).getDate()}
                  </Text>
                  <Text style={styles.upcomingMonth}>
                    {new Date(`${booking.event_date}T00:00:00`)
                      .toLocaleDateString('en-GB', { month: 'short' })
                      .toUpperCase()}
                  </Text>
                </View>
                <View style={styles.upcomingBody}>
                  <Text style={styles.upcomingName}>{booking.buyer.name}</Text>
                  <Text style={styles.upcomingMeta} numberOfLines={1}>
                    {booking.start_time.slice(0, 5)} · {booking.location_city}
                  </Text>
                </View>
                <Text style={styles.upcomingPrice}>
                  {formatPKRShort(booking.total_price)}
                </Text>
              </Pressable>
            ))}
          </Section>
        ) : null}

        <Text style={styles.footnote}>
          Charts read a nightly rollup; the counters above are live.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// CHARTS
// ═══════════════════════════════════════════════════════════════════════════
function RevenueChart({ points }: { points: RevenuePoint[] }) {
  const values = points.map((p) => Number(p.net_earnings));
  const peak = Math.max(...values, 1);
  const latest = points[points.length - 1];

  if (values.every((v) => v === 0)) {
    return (
      <Text style={styles.empty}>
        No completed shoots in the last {points.length} months yet.
      </Text>
    );
  }

  return (
    <View>
      <View style={styles.chart}>
        {points.map((point) => {
          const value = Number(point.net_earnings);
          // Floor at 2% so a zero month is still a visible baseline rather
          // than a gap the eye reads as missing data.
          const height = value > 0 ? Math.max((value / peak) * 100, 6) : 2;
          const isLatest = point === latest;
          return (
            <View key={`${point.year}-${point.month}`} style={styles.barColumn}>
              <Text style={styles.barValue}>
                {value > 0 ? formatPKRShort(point.net_earnings).replace('Rs ', '') : ''}
              </Text>
              <View style={styles.barTrack}>
                <View
                  style={[
                    styles.bar,
                    { height: `${height}%` },
                    isLatest && styles.barLatest,
                  ]}
                />
              </View>
              <Text style={[styles.barLabel, isLatest && styles.barLabelLatest]}>
                {point.label}
              </Text>
            </View>
          );
        })}
      </View>

      {latest && latest.growth_percent !== 0 ? (
        <View style={styles.growthRow}>
          <Ionicons
            name={latest.growth_percent > 0 ? 'trending-up' : 'trending-down'}
            size={15}
            color={latest.growth_percent > 0 ? colors.green : colors.red}
          />
          <Text
            style={[
              styles.growthText,
              { color: latest.growth_percent > 0 ? colors.green : colors.red },
            ]}
          >
            {latest.growth_percent > 0 ? '+' : ''}
            {latest.growth_percent}% vs last month
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function FunnelChart({ funnel }: { funnel: Funnel }) {
  const steps = [
    { label: 'Seen in search', value: funnel.impressions },
    { label: 'Profile viewed', value: funnel.profile_views },
    { label: 'Enquired', value: funnel.inquiries },
    { label: 'Booked', value: funnel.bookings },
  ];
  const peak = Math.max(...steps.map((s) => s.value), 1);

  if (steps.every((s) => s.value === 0)) {
    return (
      <Text style={styles.empty}>
        Not enough activity in the last {funnel.days} days to chart yet.
      </Text>
    );
  }

  return (
    <View>
      {steps.map((step) => (
        <View key={step.label} style={styles.funnelRow}>
          <Text style={styles.funnelLabel}>{step.label}</Text>
          <View style={styles.funnelTrack}>
            <View
              style={[
                styles.funnelFill,
                { width: `${Math.max((step.value / peak) * 100, step.value ? 4 : 0)}%` },
              ]}
            />
          </View>
          <Text style={styles.funnelValue}>{step.value}</Text>
        </View>
      ))}
      {funnel.profile_views > 0 ? (
        <Text style={styles.funnelNote}>
          {(funnel.view_to_booking_rate * 100).toFixed(1)}% of profile views became
          a booking.
        </Text>
      ) : null}
    </View>
  );
}

function CategoryBars({ rows }: { rows: CategorySplit[] }) {
  const total = rows.reduce((sum, row) => sum + row.bookings, 0) || 1;
  return (
    <View>
      {rows.map((row) => (
        <View key={row.category} style={styles.funnelRow}>
          <Text style={styles.funnelLabel}>{row.category}</Text>
          <View style={styles.funnelTrack}>
            <View
              style={[
                styles.funnelFill,
                styles.categoryFill,
                { width: `${(row.bookings / total) * 100}%` },
              ]}
            />
          </View>
          <Text style={styles.funnelValue}>{row.bookings}</Text>
        </View>
      ))}
    </View>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// PIECES
// ═══════════════════════════════════════════════════════════════════════════
function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {hint ? <Text style={styles.sectionHint}>{hint}</Text> : null}
      <View style={styles.card}>{children}</View>
    </View>
  );
}

function ActionTile({
  icon,
  value,
  label,
  hint,
  urgent,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  value: number;
  label: string;
  hint: string;
  urgent?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${value} ${label} ${hint}`}
      style={({ pressed }) => [
        styles.actionTile,
        urgent && styles.actionTileUrgent,
        pressed && styles.pressed,
      ]}
    >
      <Ionicons name={icon} size={18} color={urgent ? colors.amber : colors.sub} />
      <Text style={[styles.actionValue, urgent && styles.actionValueUrgent]}>
        {value}
      </Text>
      <Text style={styles.actionLabel}>{label}</Text>
      <Text style={styles.actionHint}>{hint}</Text>
    </Pressable>
  );
}

function Stat({
  value,
  label,
  icon,
  tint,
}: {
  value: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  tint: string;
}) {
  return (
    <View style={styles.stat}>
      <Ionicons name={icon} size={14} color={tint} />
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function ServiceRow({ service, rank }: { service: TopService; rank: number }) {
  return (
    <View style={styles.serviceRow}>
      <Text style={styles.rank}>{rank}</Text>
      <View style={styles.serviceBody}>
        <Text style={styles.serviceTitle} numberOfLines={1}>
          {service.title}
        </Text>
        <Text style={styles.serviceMeta}>
          {service.completed} completed of {service.bookings}
        </Text>
      </View>
      <Text style={styles.serviceRevenue}>{formatPKRShort(service.revenue)}</Text>
    </View>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

/** Hours are engineering data; a photographer wants "within an hour". */
function responseLabel(hours: number): string {
  if (hours <= 1) return '<1h';
  if (hours < 24) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.xl, paddingBottom: spacing.huge },
  topRow: { flexDirection: 'row', alignItems: 'flex-start' },
  topText: { flex: 1 },
  topActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  greeting: { ...typography.caption, color: colors.sub },
  name: { ...typography.h1, color: colors.text, marginBottom: spacing.lg },
  paused: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  pausedText: { ...typography.caption, color: colors.amber, flex: 1 },
  actionRow: { flexDirection: 'row', gap: spacing.md },
  actionTile: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  actionTileUrgent: { borderColor: colors.amber },
  pressed: { opacity: 0.8 },
  actionValue: { ...typography.display, color: colors.text, marginTop: spacing.xs },
  actionValueUrgent: { color: colors.amber },
  actionLabel: { ...typography.caption, color: colors.text },
  actionHint: { ...typography.tiny, color: colors.dim, marginTop: 1 },
  earningsCard: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.borderMid,
    padding: spacing.lg,
    marginTop: spacing.md,
  },
  earningsLabel: { ...typography.caption, color: colors.sub },
  earningsValue: { ...typography.display, color: colors.gold, marginVertical: 2 },
  earningsMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
  },
  earningsMetaText: { ...typography.tiny, color: colors.dim },
  statRow: {
    flexDirection: 'row',
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.lg,
    marginTop: spacing.md,
  },
  stat: { flex: 1, alignItems: 'center', gap: 2 },
  statValue: { ...typography.h3, color: colors.text },
  statLabel: { ...typography.tiny, color: colors.sub },
  section: { marginTop: spacing.xxl },
  sectionTitle: { ...typography.h3, color: colors.text },
  sectionHint: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginTop: spacing.md,
  },
  empty: { ...typography.caption, color: colors.dim, textAlign: 'center' },
  chart: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    height: 168,
  },
  barColumn: { flex: 1, alignItems: 'center', height: '100%' },
  barValue: { ...typography.tiny, color: colors.sub, height: 14 },
  barTrack: { flex: 1, width: '58%', justifyContent: 'flex-end' },
  bar: {
    width: '100%',
    backgroundColor: colors.goldDim,
    borderTopLeftRadius: radius.sm,
    borderTopRightRadius: radius.sm,
    minHeight: 3,
  },
  barLatest: { backgroundColor: colors.gold },
  barLabel: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs },
  barLabelLatest: { color: colors.gold, fontWeight: '700' },
  growthRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  growthText: { ...typography.caption, fontWeight: '600' },
  funnelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  funnelLabel: { ...typography.tiny, color: colors.sub, width: 96 },
  funnelTrack: {
    flex: 1,
    height: 18,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    overflow: 'hidden',
  },
  funnelFill: { height: '100%', backgroundColor: colors.gold, borderRadius: radius.sm },
  categoryFill: { backgroundColor: colors.blue },
  funnelValue: {
    ...typography.caption,
    color: colors.text,
    width: 40,
    textAlign: 'right',
  },
  funnelNote: { ...typography.tiny, color: colors.dim, marginTop: spacing.xs },
  serviceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  rank: { ...typography.caption, color: colors.dim, width: 14 },
  serviceBody: { flex: 1 },
  serviceTitle: { ...typography.caption, color: colors.text, fontWeight: '600' },
  serviceMeta: { ...typography.tiny, color: colors.sub },
  serviceRevenue: { ...typography.caption, color: colors.gold, fontWeight: '700' },
  emptyAction: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  emptyActionText: { ...typography.caption, color: colors.sub, flex: 1 },
  upcomingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  upcomingDate: {
    width: 42,
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    paddingVertical: spacing.xs,
  },
  upcomingDay: { ...typography.bodyBold, color: colors.gold },
  upcomingMonth: { ...typography.tiny, color: colors.sub },
  upcomingBody: { flex: 1 },
  upcomingName: { ...typography.caption, color: colors.text, fontWeight: '600' },
  upcomingMeta: { ...typography.tiny, color: colors.sub },
  upcomingPrice: { ...typography.caption, color: colors.gold },
  footnote: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
    marginTop: spacing.xxl,
  },
});
