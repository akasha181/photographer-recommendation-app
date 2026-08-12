/**
 * Shared bottom-tab styling.
 *
 * WHY THIS IS A HOOK AND NOT A CONSTANT
 * -------------------------------------
 * A fixed tab-bar height is wrong on any modern phone. On devices with a
 * gesture home indicator (iPhone X and later, most recent Android), the OS
 * draws that indicator over the bottom ~34pt of the screen. A 62pt tab bar
 * puts its labels underneath it, so "Bookings" ends up with a white bar
 * struck through it.
 *
 * `useSafeAreaInsets()` reports the real inset for the actual device, so the
 * bar grows to sit above the indicator instead of behind it. On older phones
 * with no indicator the inset is 0 and nothing changes.
 *
 * Both navigators use this, so buyer and photographer tab bars can never
 * drift apart.
 */

import type { BottomTabNavigationOptions } from '@react-navigation/bottom-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, typography } from '../theme';

/** Bar height excluding the safe-area inset. */
const BAR_HEIGHT = 58;

export function useTabBarOptions(): Pick<
  BottomTabNavigationOptions,
  'tabBarActiveTintColor' | 'tabBarInactiveTintColor' | 'tabBarStyle' | 'tabBarLabelStyle' | 'tabBarItemStyle'
> {
  const insets = useSafeAreaInsets();

  return {
    tabBarActiveTintColor: colors.gold,
    tabBarInactiveTintColor: colors.dim,
    tabBarStyle: {
      backgroundColor: colors.surface,
      borderTopColor: colors.border,
      borderTopWidth: 1,
      height: BAR_HEIGHT + insets.bottom,
      paddingBottom: insets.bottom,
      paddingTop: 8,
    },
    tabBarLabelStyle: {
      ...typography.tiny,
      marginTop: 2,
    },
    tabBarItemStyle: {
      paddingVertical: 2,
    },
  };
}
