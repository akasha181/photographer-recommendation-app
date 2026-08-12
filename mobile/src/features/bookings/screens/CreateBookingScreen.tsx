import { Ionicons } from '@expo/vector-icons';
import React, { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { usePhotographerDetail } from '../../explore/hooks/usePhotographers';
import { useAuthStore } from '../../../store/authStore';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatPKR } from '../../../utils/format';
import type { Service } from '../../../types/models';
import {
  DatePicker,
  TimePicker,
  UnavailableNotice,
} from '../components/DatePicker';
import {
  useAvailabilityCalendar,
  useAvailableTimes,
  useCreateBooking,
} from '../hooks/useBookings';

/**
 * The booking request form.
 *
 * THE PRICE SHOWN HERE IS AN ESTIMATE, NOT AN INPUT
 * -------------------------------------------------
 * The total is rendered from the catalogue so the buyer knows what they are
 * committing to, but it is never sent. The server snapshots the real price
 * from the service row inside the same transaction that creates the booking —
 * a client that could name its own price could book an Rs 85,000 wedding for
 * one rupee. The two agree because they read the same source, not because
 * the client is trusted.
 */
export function CreateBookingScreen({
  photographerId,
  initialServiceId,
  onBack,
  onCreated,
}: {
  photographerId: number;
  initialServiceId?: number;
  onBack: () => void;
  onCreated: (bookingId: number) => void;
}) {
  const user = useAuthStore((s) => s.user);

  const photographer = usePhotographerDetail(photographerId);
  const calendar = useAvailabilityCalendar(photographerId, 60);

  const [serviceId, setServiceId] = useState<number | null>(initialServiceId ?? null);
  const [date, setDate] = useState<string | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const [address, setAddress] = useState('');
  const [city, setCity] = useState(user?.city ?? '');
  const [guests, setGuests] = useState('');
  const [notes, setNotes] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});

  const services = photographer.data?.services ?? [];
  const service = useMemo(
    () => services.find((s) => s.id === serviceId) ?? services[0] ?? null,
    [services, serviceId],
  );

  const duration = service?.duration_hours ?? 4;
  const times = useAvailableTimes(photographerId, date, duration);
  const createBooking = useCreateBooking();

  const selectedDay =
    calendar.data?.days.find((d) => d.date === date) ?? null;

  if (photographer.isLoading || calendar.isLoading) {
    return <LoadingState label="Loading booking options…" />;
  }
  if (photographer.isError || !photographer.data) {
    return (
      <ErrorState
        message={(photographer.error as ApiError)?.message}
        onRetry={() => photographer.refetch()}
      />
    );
  }

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!service) next.service = 'Choose a service.';
    if (!date) next.date = 'Choose a date.';
    if (!time) next.time = 'Choose a start time.';
    if (address.trim().length < 5) next.address = 'Where is the shoot? Give a full address.';
    if (!city.trim()) next.city = 'City is required.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const submit = () => {
    if (!validate() || !service || !date || !time) return;

    createBooking.mutate(
      {
        service: service.id,
        event_date: date,
        start_time: time,
        duration_hours: duration,
        location_address: address.trim(),
        location_city: city.trim(),
        guest_count: guests ? Number(guests) : null,
        notes: notes.trim(),
      },
      {
        onSuccess: (booking) => onCreated(booking.id),
        onError: (error) => {
          const api = error as ApiError;
          // Field errors go next to the field; a rule violation (a slot taken
          // in the last few seconds, a daily limit reached) is about the whole
          // request and belongs in an alert the user must acknowledge.
          const fieldErrors = api.fieldErrors ?? {};
          if (Object.keys(fieldErrors).length) {
            setErrors(fieldErrors);
          } else {
            Alert.alert('Could not send the request', api.message);
          }
          // The calendar may have moved on — refetch so the strip is honest.
          calendar.refetch();
          times.refetch();
        },
      },
    );
  };

  const estimate = service ? estimateTotal(service, duration) : null;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>Request a booking</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.photographer}>
          with <Text style={styles.photographerName}>{photographer.data.display_name}</Text>
        </Text>

        {/* ─── Service ─────────────────────────────────────────────────── */}
        <Section title="What do you need?" error={errors.service}>
          {services.length === 0 ? (
            <Text style={styles.hint}>
              This photographer has not published any services yet.
            </Text>
          ) : (
            services.map((s) => (
              <ServiceOption
                key={s.id}
                service={s}
                selected={s.id === service?.id}
                onPress={() => {
                  setServiceId(s.id);
                  // Duration changes with the service, so a time that fitted
                  // the old one may no longer fit. Clearing it is safer than
                  // silently submitting an overrun.
                  setTime(null);
                }}
              />
            ))
          )}
        </Section>

        {/* ─── Date ────────────────────────────────────────────────────── */}
        <Section title="When?" error={errors.date}>
          <DatePicker
            days={calendar.data?.days ?? []}
            selectedDate={date}
            onSelectDate={(value) => {
              setDate(value);
              setTime(null);
            }}
          />
          <UnavailableNotice day={selectedDay} />
        </Section>

        {/* ─── Time ────────────────────────────────────────────────────── */}
        {date ? (
          <Section
            title={`Start time · ${duration}h shoot`}
            error={errors.time}
          >
            <TimePicker
              times={times.data?.available_start_times ?? []}
              selected={time}
              onSelect={setTime}
              isLoading={times.isLoading}
            />
          </Section>
        ) : null}

        {/* ─── Location ────────────────────────────────────────────────── */}
        <Section title="Where?">
          <Input
            label="Venue address"
            placeholder="e.g. Serena Hotel, Islamabad"
            value={address}
            onChangeText={setAddress}
            error={errors.address}
            icon="location-outline"
            multiline
          />
          <Input
            label="City"
            placeholder="Islamabad"
            value={city}
            onChangeText={setCity}
            error={errors.city}
            icon="business-outline"
          />
        </Section>

        {/* ─── Details ─────────────────────────────────────────────────── */}
        <Section title="Anything else?">
          <Input
            label="Expected guests (optional)"
            placeholder="120"
            value={guests}
            onChangeText={(v) => setGuests(v.replace(/[^0-9]/g, ''))}
            keyboardType="number-pad"
            icon="people-outline"
          />
          <Input
            label="Notes for the photographer (optional)"
            placeholder="Nikah at 4pm, reception at 8pm. Drone shots if possible."
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={3}
          />
        </Section>

        {/* ─── Estimate ────────────────────────────────────────────────── */}
        {estimate ? (
          <View style={styles.summary}>
            <Text style={styles.summaryTitle}>Estimate</Text>
            {estimate.lines.map((line) => (
              <View key={line.label} style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>{line.label}</Text>
                <Text style={styles.summaryValue}>{line.amount}</Text>
              </View>
            ))}
            <View style={[styles.summaryRow, styles.summaryTotal]}>
              <Text style={styles.summaryTotalLabel}>Total</Text>
              <Text style={styles.summaryTotalValue}>{estimate.total}</Text>
            </View>
            <Text style={styles.summaryNote}>
              Confirmed by the photographer before any payment. Nothing is charged now.
            </Text>
          </View>
        ) : null}
      </ScrollView>

      <View style={styles.footer}>
        <Button
          label="Send request"
          onPress={submit}
          loading={createBooking.isPending}
          disabled={!service || !date || !time}
        />
        <Text style={styles.footerNote}>
          The photographer has 48 hours to reply.
        </Text>
      </View>
    </SafeAreaView>
  );
}

function Section({
  title,
  error,
  children,
}: {
  title: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

function ServiceOption({
  service,
  selected,
  onPress,
}: {
  service: Service;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      style={[styles.option, selected && styles.optionSelected]}
    >
      <View style={styles.optionRadio}>
        {selected ? <View style={styles.optionRadioDot} /> : null}
      </View>
      <View style={styles.optionBody}>
        <Text style={styles.optionTitle} numberOfLines={1}>
          {service.title}
        </Text>
        <Text style={styles.optionMeta}>
          {service.duration_hours}h · {service.edited_photos_count} edited photos
        </Text>
      </View>
      <Text style={styles.optionPrice}>{formatPKR(service.price)}</Text>
    </Pressable>
  );
}

/**
 * Mirror of `services._price_snapshot` on the server.
 *
 * Kept deliberately simple and clearly labelled an estimate — the number that
 * counts is the one the API returns on the created booking.
 */
function estimateTotal(service: Service, hours: number) {
  const unit = parseFloat(service.price);
  const quantity = service.pricing_unit === 'PER_HOUR' ? hours : 1;
  return {
    lines: [
      {
        label:
          quantity > 1 ? `${service.title} × ${quantity}h` : service.title,
        amount: formatPKR(unit * quantity),
      },
    ],
    total: formatPKR(unit * quantity),
  };
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
  photographer: { ...typography.caption, color: colors.sub, marginBottom: spacing.xl },
  photographerName: { color: colors.gold, fontWeight: '600' },
  section: { marginBottom: spacing.xxl },
  sectionTitle: {
    ...typography.h3,
    color: colors.text,
    marginBottom: spacing.md,
  },
  hint: { ...typography.caption, color: colors.sub },
  error: { ...typography.caption, color: colors.red, marginTop: spacing.sm },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
    marginBottom: spacing.sm,
  },
  optionSelected: { borderColor: colors.gold, backgroundColor: colors.cardHover },
  optionRadio: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: colors.borderMid,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionRadioDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.gold,
  },
  optionBody: { flex: 1 },
  optionTitle: { ...typography.bodyBold, color: colors.text },
  optionMeta: { ...typography.caption, color: colors.sub },
  optionPrice: { ...typography.bodyBold, color: colors.gold },
  summary: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
  summaryTitle: { ...typography.caption, color: colors.sub, marginBottom: spacing.md },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  summaryLabel: { ...typography.caption, color: colors.sub, flex: 1 },
  summaryValue: { ...typography.caption, color: colors.text },
  summaryTotal: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
    marginTop: spacing.xs,
  },
  summaryTotalLabel: { ...typography.bodyBold, color: colors.text },
  summaryTotalValue: { ...typography.bodyBold, color: colors.gold },
  summaryNote: {
    ...typography.tiny,
    color: colors.dim,
    marginTop: spacing.md,
    lineHeight: 16,
  },
  footer: {
    padding: spacing.xl,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  footerNote: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
});
