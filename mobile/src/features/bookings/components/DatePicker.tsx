import { Ionicons } from '@expo/vector-icons';
import React, { useMemo } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { LoadingState } from '../../../components/feedback/States';
import { colors, radius, spacing, typography } from '../../../theme';
import type { AvailabilityDay } from '../../../types/models';

/**
 * Date and time selection, driven entirely by the server's calendar.
 *
 * WHY NOT A NATIVE DATE PICKER
 * ----------------------------
 * A stock picker happily lets a buyer choose a Sunday the photographer never
 * works, a date they are already booked on, or tomorrow morning when the
 * platform requires 24 hours' notice. Every one of those becomes a rejected
 * request and a confused user. Rendering the real calendar means an
 * unbookable date cannot be tapped in the first place — and when it is
 * disabled, the server's own sentence explains why.
 *
 * It also avoids adding a picker dependency, which matters on a project
 * pinned to Expo SDK 54 (see mobile/AGENTS.md).
 */
export function DatePicker({
  days,
  selectedDate,
  onSelectDate,
  isLoading,
}: {
  days: AvailabilityDay[];
  selectedDate: string | null;
  onSelectDate: (date: string) => void;
  isLoading?: boolean;
}) {
  // Past and too-soon dates are dropped rather than shown greyed out: a strip
  // that opens on four dead cells reads as a broken screen.
  const visible = useMemo(
    () => days.filter((d) => d.reason !== 'PAST' && d.reason !== 'TOO_SOON'),
    [days],
  );

  const grouped = useMemo(() => groupByMonth(visible), [visible]);

  if (isLoading) return <LoadingState label="Checking availability…" />;

  if (!visible.length) {
    return (
      <View style={styles.empty}>
        <Ionicons name="calendar-clear-outline" size={20} color={colors.dim} />
        <Text style={styles.emptyText}>No dates available in the next two months.</Text>
      </View>
    );
  }

  return (
    <View>
      {grouped.map(({ month, entries }) => (
        <View key={month} style={styles.monthBlock}>
          <Text style={styles.month}>{month}</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.strip}
          >
            {entries.map((day) => (
              <DateCell
                key={day.date}
                day={day}
                selected={day.date === selectedDate}
                onPress={() => onSelectDate(day.date)}
              />
            ))}
          </ScrollView>
        </View>
      ))}
    </View>
  );
}

function DateCell({
  day,
  selected,
  onPress,
}: {
  day: AvailabilityDay;
  selected: boolean;
  onPress: () => void;
}) {
  const date = new Date(`${day.date}T00:00:00`);
  const disabled = !day.is_available;

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ disabled, selected }}
      accessibilityLabel={
        disabled
          ? `${day.date} unavailable. ${day.message}`
          : `${day.date} available`
      }
      style={[styles.cell, selected && styles.cellSelected, disabled && styles.cellOff]}
    >
      <Text style={[styles.weekday, selected && styles.textSelected]}>
        {date.toLocaleDateString('en-GB', { weekday: 'short' })}
      </Text>
      <Text style={[styles.dayNumber, selected && styles.textSelected, disabled && styles.textOff]}>
        {date.getDate()}
      </Text>
      {disabled ? (
        <View style={styles.strike} />
      ) : (
        <View style={[styles.availableDot, selected && styles.dotSelected]} />
      )}
    </Pressable>
  );
}

/**
 * The reason a specific date is closed, shown under the strip.
 *
 * "Fully booked" and "the photographer does not work on Sundays" call for
 * completely different next actions from the buyer, so the message is worth
 * surfacing rather than collapsing into a generic "unavailable".
 */
export function UnavailableNotice({ day }: { day: AvailabilityDay | null }) {
  if (!day || day.is_available || !day.message) return null;
  return (
    <View style={styles.notice}>
      <Ionicons name="information-circle-outline" size={16} color={colors.amber} />
      <Text style={styles.noticeText}>{day.message}</Text>
    </View>
  );
}

/** Start-time chips for the chosen date, with taken slots already removed. */
export function TimePicker({
  times,
  selected,
  onSelect,
  isLoading,
}: {
  times: string[];
  selected: string | null;
  onSelect: (time: string) => void;
  isLoading?: boolean;
}) {
  if (isLoading) {
    return <Text style={styles.hint}>Loading times…</Text>;
  }
  if (!times.length) {
    return <Text style={styles.hint}>No start times left on this date.</Text>;
  }

  return (
    <View style={styles.chips}>
      {times.map((time) => {
        const active = time === selected;
        return (
          <Pressable
            key={time}
            onPress={() => onSelect(time)}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            style={[styles.chip, active && styles.chipActive]}
          >
            <Text style={[styles.chipText, active && styles.chipTextActive]}>
              {time}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function groupByMonth(days: AvailabilityDay[]) {
  const out: { month: string; entries: AvailabilityDay[] }[] = [];
  for (const day of days) {
    const label = new Date(`${day.date}T00:00:00`).toLocaleDateString('en-GB', {
      month: 'long',
      year: 'numeric',
    });
    const last = out[out.length - 1];
    if (last?.month === label) last.entries.push(day);
    else out.push({ month: label, entries: [day] });
  }
  return out;
}

const CELL = 58;

const styles = StyleSheet.create({
  monthBlock: { marginBottom: spacing.lg },
  month: {
    ...typography.caption,
    color: colors.sub,
    marginBottom: spacing.sm,
    fontWeight: '600',
  },
  strip: { gap: spacing.sm, paddingRight: spacing.lg },
  cell: {
    width: CELL,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
    alignItems: 'center',
    gap: 2,
  },
  cellSelected: { backgroundColor: colors.gold, borderColor: colors.gold },
  cellOff: { backgroundColor: colors.surface, borderColor: colors.border, opacity: 0.55 },
  weekday: { ...typography.tiny, color: colors.sub, textTransform: 'uppercase' },
  dayNumber: { ...typography.h3, color: colors.text },
  textSelected: { color: colors.bg },
  textOff: { color: colors.dim },
  availableDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.green,
    marginTop: 2,
  },
  dotSelected: { backgroundColor: colors.bg },
  strike: {
    width: 16,
    height: 1,
    backgroundColor: colors.dim,
    marginTop: 4,
  },
  notice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.amberDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.xs,
  },
  noticeText: { ...typography.caption, color: colors.amber, flex: 1 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.borderMid,
    backgroundColor: colors.card,
  },
  chipActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { ...typography.caption, color: colors.text, fontWeight: '600' },
  chipTextActive: { color: colors.bg },
  hint: { ...typography.caption, color: colors.sub },
  empty: {
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xxl,
  },
  emptyText: { ...typography.caption, color: colors.sub, textAlign: 'center' },
});
