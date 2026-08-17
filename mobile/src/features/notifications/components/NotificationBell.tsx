import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing, typography } from '../../../theme';
import { useUnreadBadge } from '../hooks/useNotifications';

/**
 * The bell, with its unread count.
 *
 * WHY THE COUNT COMES FROM ITS OWN QUERY AND NOT FROM A PROP
 * ---------------------------------------------------------
 * The bell appears in several headers. Threading the number down from each
 * screen would mean every one of them fetches it, and two headers could show
 * different numbers at the same time. One shared query key means one number,
 * fetched once, updated everywhere.
 *
 * WHY 9+ RATHER THAN A REAL NUMBER
 * -------------------------------
 * Three digits do not fit in the dot without shrinking the text below legible,
 * and "137" is not a more actionable answer than "lots". The list itself has the
 * exact figure.
 */
export function NotificationBell({
  onPress,
  icon = 'notifications-outline',
  /** Use the chat total instead of the notification total. */
  count,
}: {
  onPress: () => void;
  icon?: keyof typeof Ionicons.glyphMap;
  count?: number;
}) {
  const badge = useUnreadBadge();
  const unread = count ?? badge.data?.total ?? 0;

  return (
    <Pressable
      onPress={onPress}
      hitSlop={10}
      accessibilityRole="button"
      accessibilityLabel={
        unread ? `Notifications, ${unread} unread` : 'Notifications'
      }
      style={styles.wrap}
    >
      <Ionicons name={icon} size={22} color={colors.text} />
      {unread > 0 ? (
        <View style={styles.dot}>
          <Text style={styles.dotText}>{unread > 9 ? '9+' : unread}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  dot: {
    position: 'absolute',
    top: 1,
    right: 0,
    minWidth: 17,
    height: 17,
    borderRadius: 9,
    paddingHorizontal: 4,
    backgroundColor: colors.red,
    borderWidth: 2,
    borderColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotText: {
    ...typography.tiny,
    color: colors.white,
    fontSize: 9,
    lineHeight: 11,
    letterSpacing: 0,
  },
});
