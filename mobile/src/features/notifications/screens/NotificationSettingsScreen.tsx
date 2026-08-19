import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import {
  Alert,
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
import { colors, radius, spacing, typography } from '../../../theme';
import type { NotificationPreferences } from '../../../types/models';
import {
  useNotificationPreferences,
  useUpdateNotificationPreferences,
} from '../hooks/useNotifications';

type Key = keyof NotificationPreferences;

const CHANNELS: { key: Key; label: string; detail: string }[] = [
  { key: 'push_enabled', label: 'Push notifications', detail: 'Alerts on this device' },
  { key: 'email_enabled', label: 'Email', detail: 'A copy in your inbox' },
  { key: 'sms_enabled', label: 'SMS', detail: 'Text messages for urgent updates' },
];

const CATEGORIES: { key: Key; label: string; detail: string }[] = [
  {
    key: 'booking_updates',
    label: 'Booking updates',
    detail: 'Requests, acceptances and reminders',
  },
  { key: 'chat_messages', label: 'Messages', detail: 'New chat messages' },
  {
    key: 'review_activity',
    label: 'Review activity',
    detail: 'New reviews and replies',
  },
  {
    key: 'marketplace_activity',
    label: 'Shop activity',
    detail: 'Purchases and sales',
  },
  { key: 'promotions', label: 'Promotions', detail: 'Offers and platform news' },
];

/**
 * Notification settings.
 *
 * WHAT THIS SCREEN SAYS OUT LOUD
 * ------------------------------
 * Some notifications ignore every switch here: a cancelled booking, a blocked
 * account, a wallet credit. That is deliberate on the server (`CRITICAL_TYPES`
 * in `notifications/services.py`) and stating it is the honest thing to do —
 * a settings screen that silently disobeys its own switches is worse than one
 * that explains the exception.
 *
 * Each toggle saves immediately rather than behind a Save button. There is no
 * multi-field validity to check, and a settings screen that can be left in an
 * unsaved state is a settings screen people think they changed.
 */
export function NotificationSettingsScreen({ onBack }: { onBack: () => void }) {
  const preferences = useNotificationPreferences();
  const update = useUpdateNotificationPreferences();

  const toggle = (key: Key, value: boolean) =>
    update.mutate(
      { [key]: value } as Partial<NotificationPreferences>,
      {
        onError: (error) =>
          Alert.alert('Could not save that', (error as ApiError).message),
      },
    );

  if (preferences.isLoading) return <LoadingState label="Loading settings…" />;
  if (preferences.isError || !preferences.data) {
    return (
      <ErrorState
        message={(preferences.error as ApiError)?.message}
        onRetry={() => preferences.refetch()}
      />
    );
  }

  const prefs = preferences.data;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <View>
          <Text style={styles.title}>Notification settings</Text>
          <Text style={styles.subtitle}>Choose what reaches you, and how</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
        <Text style={styles.section}>Channels</Text>
        <View style={styles.card}>
          {CHANNELS.map((row, index) => (
            <Row
              key={row.key}
              label={row.label}
              detail={row.detail}
              value={Boolean(prefs[row.key])}
              onChange={(value) => toggle(row.key, value)}
              last={index === CHANNELS.length - 1}
            />
          ))}
        </View>

        <Text style={styles.section}>What to send</Text>
        <View style={styles.card}>
          {CATEGORIES.map((row, index) => (
            <Row
              key={row.key}
              label={row.label}
              detail={row.detail}
              value={Boolean(prefs[row.key])}
              onChange={(value) => toggle(row.key, value)}
              last={index === CATEGORIES.length - 1}
            />
          ))}
        </View>

        <Text style={styles.section}>Quiet hours</Text>
        <View style={styles.card}>
          <Row
            label="Hold push at night"
            detail={`No buzzing between ${prefs.quiet_hours_start.slice(0, 5)} and ${prefs.quiet_hours_end.slice(0, 5)}`}
            value={prefs.quiet_hours_enabled}
            onChange={(value) => toggle('quiet_hours_enabled', value)}
            last
          />
        </View>
        <Text style={styles.note}>
          Notifications still arrive in the app during quiet hours — only the push is held
          back.
        </Text>

        <View style={styles.callout}>
          <Ionicons name="information-circle-outline" size={16} color={colors.blue} />
          <Text style={styles.calloutText}>
            A cancelled booking, a wallet credit or a decision about your account always
            reaches you, whatever is set here.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({
  label,
  detail,
  value,
  onChange,
  last,
}: {
  label: string;
  detail: string;
  value: boolean;
  onChange: (value: boolean) => void;
  last?: boolean;
}) {
  return (
    <View style={[styles.row, !last && styles.rowDivider]}>
      <View style={styles.rowBody}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowDetail}>{detail}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: colors.border, true: colors.goldDim }}
        thumbColor={value ? colors.gold : colors.sub}
      />
    </View>
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
  title: { ...typography.h2, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  body: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  section: {
    ...typography.tiny,
    color: colors.sub,
    textTransform: 'uppercase',
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.lg,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  rowDivider: { borderBottomWidth: 1, borderBottomColor: colors.border },
  rowBody: { flex: 1 },
  rowLabel: { ...typography.body, color: colors.text },
  rowDetail: { ...typography.tiny, color: colors.sub, marginTop: 1 },
  note: { ...typography.tiny, color: colors.dim, marginTop: spacing.sm, lineHeight: 16 },
  callout: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.blueDim,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  calloutText: { ...typography.tiny, color: colors.text, flex: 1, lineHeight: 16 },
});
