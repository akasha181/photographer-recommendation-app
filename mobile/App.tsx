import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { StyleSheet } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ApiError } from './src/api/client';
import { RootNavigator } from './src/navigation/RootNavigator';

/**
 * React Query configuration.
 *
 * The retry policy is the important part. Retrying a 401 or a 403 is pure
 * waste — the answer will not change — and retrying a 400 hides a real bug
 * behind three attempts. Only genuine transient failures (network drops and
 * 5xx) are worth a second try.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 2;
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    },
    mutations: {
      // Mutations are never retried automatically: a retried booking POST
      // could create a second booking. Deliberate retries are made safe by
      // the Idempotency-Key header, but automatic ones are not worth the risk.
      retry: false,
    },
  },
});

export default function App() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <RootNavigator />
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
});
