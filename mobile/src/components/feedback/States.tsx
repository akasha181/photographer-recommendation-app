import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Button } from '../ui/Button';
import { colors, radius, spacing, typography } from '../../theme';

/**
 * The four states every screen must handle.
 *
 * Shipping only the success state is the most common React Native mistake:
 * the screen looks perfect in development against a fast local API, then
 * shows a blank white void on a train.
 */

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.gold} size="large" />
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

export function EmptyState({
  icon = 'search-outline',
  title,
  detail,
  actionLabel,
  onAction,
}: {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <View style={styles.center}>
      <View style={styles.iconCircle}>
        <Ionicons name={icon} size={26} color={colors.dim} />
      </View>
      <Text style={styles.title}>{title}</Text>
      {detail ? <Text style={styles.detail}>{detail}</Text> : null}
      {actionLabel && onAction ? (
        <View style={styles.action}>
          <Button label={actionLabel} onPress={onAction} variant="secondary" fullWidth={false} />
        </View>
      ) : null}
    </View>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <View style={styles.center}>
      <View style={[styles.iconCircle, styles.errorCircle]}>
        <Ionicons name="cloud-offline-outline" size={26} color={colors.red} />
      </View>
      <Text style={styles.title}>Something went wrong</Text>
      <Text style={styles.detail}>
        {message ?? 'We could not load this right now.'}
      </Text>
      {onRetry ? (
        <View style={styles.action}>
          <Button label="Try again" onPress={onRetry} variant="secondary" fullWidth={false} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xxxl,
    minHeight: 240,
  },
  iconCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.card,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  errorCircle: { backgroundColor: colors.redDim },
  label: { ...typography.caption, color: colors.sub, marginTop: spacing.lg },
  title: { ...typography.h3, color: colors.text, marginBottom: spacing.sm },
  detail: {
    ...typography.caption,
    color: colors.sub,
    textAlign: 'center',
    lineHeight: 19,
    maxWidth: 280,
  },
  action: { marginTop: spacing.xl },
});
