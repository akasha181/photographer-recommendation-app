import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import React, { useEffect } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { setSessionExpiredHandler } from '../api/client';
import { usePresenceTracker } from '../features/chat/hooks/useChat';
import { useNotificationSocket } from '../features/notifications/hooks/useNotifications';
import { useAuthStore } from '../store/authStore';
import { colors, spacing, typography } from '../theme';
import { AuthNavigator } from './AuthNavigator';
import { BuyerNavigator } from './BuyerNavigator';
import { PhotographerNavigator } from './PhotographerNavigator';

/**
 * Navigation theme — React Navigation paints its own background during
 * transitions, and leaving it white produces a white flash between dark
 * screens on every push.
 */
const navTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    background: colors.bg,
    card: colors.surface,
    text: colors.text,
    border: colors.border,
    primary: colors.gold,
    notification: colors.red,
  },
};

export function RootNavigator() {
  const { isBootstrapping, isAuthenticated, user, bootstrap, clearSession } =
    useAuthStore();

  /**
   * One notification socket for the whole signed-in app.
   */
  useNotificationSocket(isAuthenticated && Boolean(user));

  /**
   * Global presence tracker so user shows online/offline correctly to others.
   */
  usePresenceTracker(isAuthenticated && Boolean(user));

  useEffect(() => {
    // Wire the axios interceptor's "refresh failed" callback into the store,
    // so an expired session drops the user back to Login from anywhere in the
    // app without any screen needing to know about it.
    setSessionExpiredHandler(clearSession);
    bootstrap();
  }, [bootstrap, clearSession]);

  if (isBootstrapping) {
    return (
      <View style={styles.splash}>
        <Text style={styles.brand}>SnapSphere</Text>
        <ActivityIndicator color={colors.gold} style={styles.spinner} />
      </View>
    );
  }

  return (
    <NavigationContainer theme={navTheme}>
      {/*
        Swapping the ENTIRE navigator on auth state is deliberate. The
        alternative — one navigator with conditional screens — leaves signed-in
        screens mounted in the background after logout, where their React Query
        hooks keep firing authenticated requests that 401 in a loop.
      */}
      {!isAuthenticated || !user ? (
        <AuthNavigator />
      ) : user.role === 'PHOTOGRAPHER' ? (
        <PhotographerNavigator />
      ) : (
        <BuyerNavigator />
      )}
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  brand: { ...typography.display, color: colors.gold, letterSpacing: 1 },
  spinner: { marginTop: spacing.xxl },
});
