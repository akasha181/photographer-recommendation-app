import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useCurrentUser } from '../../store/authStore';
import { colors, radius, spacing, typography } from '../../theme';
import { Screen } from './Screen';

interface Props {
  title: string;
  module: string;
  detail: string;
}

/**
 * Scaffold for screens whose module has not been built yet.
 *
 * Deliberately explicit about what is missing and which module delivers it,
 * so the app is navigable end-to-end from day one and it is never ambiguous
 * whether a blank screen is unfinished work or a bug.
 */
export function PlaceholderScreen({ title, module, detail }: Props) {
  const user = useCurrentUser();

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={styles.title}>{title}</Text>
        {user ? (
          <Text style={styles.greeting}>
            Signed in as {user.full_name} · {user.role.toLowerCase()}
          </Text>
        ) : null}
      </View>

      <View style={styles.card}>
        <Ionicons name="construct-outline" size={30} color={colors.gold} />
        <Text style={styles.moduleTag}>{module}</Text>
        <Text style={styles.detail}>{detail}</Text>
      </View>

      <View style={styles.statusRow}>
        <View style={styles.dot} />
        <Text style={styles.statusText}>
          Backend API and database are live — this screen is awaiting its UI.
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { marginTop: spacing.xl, marginBottom: spacing.xxxl },
  title: { ...typography.h1, color: colors.text },
  greeting: { ...typography.caption, color: colors.sub, marginTop: spacing.xs },
  card: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.xxl,
    alignItems: 'center',
  },
  moduleTag: {
    ...typography.bodyBold,
    color: colors.gold,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  detail: {
    ...typography.caption,
    color: colors.sub,
    textAlign: 'center',
    lineHeight: 19,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.xxl,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: radius.pill,
    backgroundColor: colors.green,
  },
  statusText: { ...typography.tiny, color: colors.dim, flex: 1 },
});
