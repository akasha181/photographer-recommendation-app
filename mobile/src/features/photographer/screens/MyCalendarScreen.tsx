import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useState } from 'react';
import {
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate } from '../../../utils/format';
import type { AvailabilityRule, Blackout } from '../../../types/models';
import {
  useAddBlackout,
  useMyCalendar,
  useRemoveBlackout,
  useSaveSchedule,
} from '../hooks/useMyStudio';

const HOURS = Array.from({ length: 15 }, (_, i) => `${String(i + 6).padStart(2, '0')}:00`);

/**
 * The photographer's working calendar.
 *
 * TWO THINGS THIS SCREEN SAYS OUT LOUD
 * ------------------------------------
 * 1. The weekly pattern saves as ONE request. Seven separate saves would leave
 *    a half-applied week if the connection dropped, so the button is "Save
 *    week", not seven toggles that each fire.
 * 2. Blocking dates does NOT cancel bookings inside them. The server returns
 *    how many it clashes with and the screen reports that number, so a
 *    photographer cancels those deliberately rather than discovering the
 *    clash on the day.
 */
export function MyCalendarScreen({ onBack }: { onBack: () => void }) {
  const calendar = useMyCalendar();
  const saveSchedule = useSaveSchedule();
  const addBlackout = useAddBlackout();
  const removeBlackout = useRemoveBlackout();

  const [rules, setRules] = useState<AvailabilityRule[]>([]);
  const [dirty, setDirty] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [range, setRange] = useState({ start: '', end: '', reason: '' });

  // Seed the local form once the server data lands, but never overwrite edits
  // in progress — a background refetch must not discard what they typed.
  useEffect(() => {
    if (calendar.data && !dirty) setRules(calendar.data.rules);
  }, [calendar.data, dirty]);

  const patchRule = (weekday: number, patch: Partial<AvailabilityRule>) => {
    setDirty(true);
    setRules((current) =>
      current.map((rule) => (rule.weekday === weekday ? { ...rule, ...patch } : rule)),
    );
  };

  const fail = (error: unknown) =>
    Alert.alert('Could not save', (error as ApiError)?.message ?? 'Please try again.');

  const save = () => {
    saveSchedule.mutate(
      rules.map((rule) => ({
        weekday: rule.weekday,
        is_available: rule.is_available,
        start_time: rule.start_time,
        end_time: rule.end_time,
        max_bookings: rule.max_bookings,
      })),
      {
        onSuccess: () => {
          setDirty(false);
          Alert.alert('Saved', 'Your weekly schedule is live for buyers.');
        },
        onError: fail,
      },
    );
  };

  const submitBlackout = () => {
    if (!isDate(range.start) || !isDate(range.end)) {
      Alert.alert('Dates needed', 'Enter both dates as YYYY-MM-DD.');
      return;
    }
    addBlackout.mutate(
      { start_date: range.start, end_date: range.end, reason: range.reason.trim() },
      {
        onSuccess: (result) => {
          setSheetOpen(false);
          setRange({ start: '', end: '', reason: '' });
          if (result.conflicting_bookings > 0) {
            Alert.alert(
              'Dates blocked — check your bookings',
              `${result.conflicting_bookings} confirmed booking(s) fall inside this range. ` +
                `They have NOT been cancelled. Open Bookings to cancel them yourself so ` +
                `the buyer gets a reason.`,
            );
          }
        },
        onError: fail,
      },
    );
  };

  if (calendar.isLoading) return <LoadingState label="Loading your calendar…" />;
  if (calendar.isError || !calendar.data) {
    return (
      <ErrorState
        message={(calendar.error as ApiError)?.message}
        onRetry={() => calendar.refetch()}
      />
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>Availability</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {!calendar.data.is_accepting_bookings ? (
          <View style={styles.paused}>
            <Ionicons name="pause-circle-outline" size={16} color={colors.amber} />
            <Text style={styles.pausedText}>
              You are not accepting bookings. Turn it back on from your Profile.
            </Text>
          </View>
        ) : null}

        {/* ─── Weekly pattern ──────────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Working week</Text>
        <Text style={styles.sectionHint}>
          Buyers can only request dates that match this pattern.
        </Text>

        <View style={styles.week}>
          {rules.map((rule) => (
            <DayRow key={rule.weekday} rule={rule} onChange={patchRule} />
          ))}
        </View>

        {dirty ? (
          <Button label="Save week" onPress={save} loading={saveSchedule.isPending} />
        ) : null}

        {/* ─── Blackouts ───────────────────────────────────────────────── */}
        <View style={styles.blackoutHeader}>
          <View>
            <Text style={styles.sectionTitle}>Time off</Text>
            <Text style={styles.sectionHint}>
              Holidays or dates you are already committed elsewhere.
            </Text>
          </View>
          <Pressable onPress={() => setSheetOpen(true)} hitSlop={10}>
            <Ionicons name="add-circle-outline" size={24} color={colors.gold} />
          </Pressable>
        </View>

        {calendar.data.blackouts.length === 0 ? (
          <Text style={styles.empty}>Nothing blocked. Your week runs as above.</Text>
        ) : (
          <View style={styles.blackouts}>
            {calendar.data.blackouts.map((blackout) => (
              <BlackoutRow
                key={blackout.id}
                blackout={blackout}
                onRemove={() =>
                  Alert.alert(
                    'Unblock these dates?',
                    'Buyers will be able to request them again.',
                    [
                      { text: 'Keep blocked', style: 'cancel' },
                      {
                        text: 'Unblock',
                        onPress: () =>
                          removeBlackout.mutate(blackout.id, { onError: fail }),
                      },
                    ],
                  )
                }
              />
            ))}
          </View>
        )}
      </ScrollView>

      {/* ─── Block-dates sheet ───────────────────────────────────────────── */}
      <Modal
        visible={sheetOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setSheetOpen(false)}
      >
        <View style={styles.backdrop}>
          <ScrollView
            style={styles.sheet}
            contentContainerStyle={styles.sheetContent}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={styles.sheetTitle}>Block dates</Text>
            <Text style={styles.sheetDetail}>
              Buyers will not be able to request these dates. Bookings you have
              already accepted are not cancelled — we will tell you if any fall
              inside the range.
            </Text>

            <Input
              label="From (YYYY-MM-DD)"
              placeholder="2026-08-14"
              value={range.start}
              onChangeText={(start) => setRange({ ...range, start })}
              icon="calendar-outline"
              autoCapitalize="none"
            />
            <Input
              label="To (YYYY-MM-DD)"
              placeholder="2026-08-20"
              value={range.end}
              onChangeText={(end) => setRange({ ...range, end })}
              icon="calendar-outline"
              autoCapitalize="none"
            />
            <Input
              label="Reason (buyers see this)"
              placeholder="Away for a family wedding"
              value={range.reason}
              onChangeText={(reason) => setRange({ ...range, reason })}
            />

            <Button
              label="Block these dates"
              onPress={submitBlackout}
              loading={addBlackout.isPending}
            />
            <Button label="Cancel" variant="ghost" onPress={() => setSheetOpen(false)} />
          </ScrollView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function DayRow({
  rule,
  onChange,
}: {
  rule: AvailabilityRule;
  onChange: (weekday: number, patch: Partial<AvailabilityRule>) => void;
}) {
  const [picking, setPicking] = useState<'start' | 'end' | null>(null);

  return (
    <View style={styles.dayRow}>
      <View style={styles.dayTop}>
        <Text style={[styles.dayName, !rule.is_available && styles.dayOff]}>
          {rule.weekday_label}
        </Text>
        <Switch
          value={rule.is_available}
          onValueChange={(is_available) => onChange(rule.weekday, { is_available })}
          trackColor={{ false: colors.border, true: colors.goldDim }}
          thumbColor={rule.is_available ? colors.gold : colors.sub}
        />
      </View>

      {rule.is_available ? (
        <View style={styles.dayDetail}>
          <Pressable
            onPress={() => setPicking(picking === 'start' ? null : 'start')}
            style={styles.timeButton}
          >
            <Text style={styles.timeText}>{rule.start_time}</Text>
          </Pressable>
          <Text style={styles.dash}>–</Text>
          <Pressable
            onPress={() => setPicking(picking === 'end' ? null : 'end')}
            style={styles.timeButton}
          >
            <Text style={styles.timeText}>{rule.end_time}</Text>
          </Pressable>

          <Pressable
            onPress={() =>
              onChange(rule.weekday, {
                max_bookings: rule.max_bookings >= 3 ? 1 : rule.max_bookings + 1,
              })
            }
            style={styles.slotsButton}
            accessibilityLabel={`${rule.max_bookings} shoots per day`}
          >
            <Ionicons name="albums-outline" size={13} color={colors.sub} />
            <Text style={styles.slotsText}>
              {rule.max_bookings} {rule.max_bookings === 1 ? 'shoot' : 'shoots'}
            </Text>
          </Pressable>
        </View>
      ) : (
        <Text style={styles.dayOffText}>Not working</Text>
      )}

      {picking ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.hours}>
          {HOURS.map((hour) => (
            <Pressable
              key={hour}
              onPress={() => {
                onChange(rule.weekday, { [picking + '_time']: hour } as never);
                setPicking(null);
              }}
              style={styles.hourChip}
            >
              <Text style={styles.hourText}>{hour}</Text>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}
    </View>
  );
}

function BlackoutRow({
  blackout,
  onRemove,
}: {
  blackout: Blackout;
  onRemove: () => void;
}) {
  return (
    <View style={styles.blackoutRow}>
      <View style={styles.blackoutBody}>
        <Text style={styles.blackoutDates}>
          {formatDate(blackout.start_date)}
          {blackout.days > 1 ? ` – ${formatDate(blackout.end_date)}` : ''}
        </Text>
        <Text style={styles.blackoutMeta}>
          {blackout.days} day{blackout.days === 1 ? '' : 's'}
          {blackout.reason ? ` · ${blackout.reason}` : ''}
        </Text>
      </View>
      <Pressable onPress={onRemove} hitSlop={10} accessibilityLabel="Unblock">
        <Ionicons name="close-circle-outline" size={20} color={colors.dim} />
      </Pressable>
    </View>
  );
}

function isDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value));
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
  paused: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  pausedText: { ...typography.caption, color: colors.amber, flex: 1 },
  sectionTitle: { ...typography.h3, color: colors.text },
  sectionHint: {
    ...typography.caption,
    color: colors.sub,
    marginTop: 2,
    marginBottom: spacing.md,
  },
  week: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.lg,
    overflow: 'hidden',
  },
  dayRow: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  dayTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dayName: { ...typography.bodyBold, color: colors.text },
  dayOff: { color: colors.dim },
  dayOffText: { ...typography.tiny, color: colors.dim, marginTop: 2 },
  dayDetail: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  timeButton: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.borderMid,
    backgroundColor: colors.surface,
  },
  timeText: { ...typography.caption, color: colors.text },
  dash: { color: colors.dim },
  slotsButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginLeft: 'auto',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
  },
  slotsText: { ...typography.tiny, color: colors.sub },
  hours: { marginTop: spacing.sm },
  hourChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    marginRight: spacing.xs,
  },
  hourText: { ...typography.tiny, color: colors.text },
  blackoutHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginTop: spacing.xl,
  },
  empty: { ...typography.caption, color: colors.dim },
  blackouts: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  blackoutRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  blackoutBody: { flex: 1 },
  blackoutDates: { ...typography.caption, color: colors.text, fontWeight: '600' },
  blackoutMeta: { ...typography.tiny, color: colors.sub, marginTop: 2 },
  backdrop: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '85%',
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  sheetContent: { padding: spacing.xl, paddingBottom: spacing.xxxl, gap: spacing.sm },
  sheetTitle: { ...typography.h2, color: colors.text },
  sheetDetail: {
    ...typography.caption,
    color: colors.sub,
    lineHeight: 19,
    marginBottom: spacing.md,
  },
});
