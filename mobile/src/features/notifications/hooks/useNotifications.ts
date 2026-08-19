/**
 * React Query hooks for notifications — Module 12.
 *
 * WHY THE BADGE POLLS AND THE LIST DOES NOT
 * ----------------------------------------
 * The badge is a single integer that has to be right whenever the app is in the
 * foreground, so `useUnreadBadge` refetches on an interval and on window focus.
 * The list is 30 rows; refetching it every 30 seconds would move the screen
 * under the user's thumb. Opening the bell refetches once, which is what the
 * user's own gesture already asked for.
 *
 * The WebSocket stream (`/ws/notifications/`) makes both of those a fallback
 * rather than the mechanism — see `useNotificationSocket`.
 */

import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { tokenStorage } from '../../../api/client';
import { WS_ROUTES } from '../../../api/config';
import { qk } from '../../../api/queryKeys';
import { notificationsApi } from '../../../api/services/notifications.api';
import type { NotificationPreferences } from '../../../types/models';

export function useNotifications(
  options: { category?: string; unreadOnly?: boolean } = {},
) {
  return useQuery({
    queryKey: qk.notifications.list(options.category, options.unreadOnly),
    queryFn: () => notificationsApi.list(options),
    staleTime: 30_000,
  });
}

export function useUnreadBadge() {
  return useQuery({
    queryKey: qk.notifications.badges,
    queryFn: () => notificationsApi.badges(),
    staleTime: 20_000,
    // A fallback for the socket, not the primary path — hence a minute, not
    // five seconds. Polling faster would cost battery for a number that the
    // stream already pushes.
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

function useNotificationInvalidation() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: qk.notifications.all });
}

export function useMarkRead() {
  const invalidate = useNotificationInvalidation();
  return useMutation({
    /** No ids means "all" — see notificationsApi.markRead. */
    mutationFn: (ids?: number[]) => notificationsApi.markRead(ids ?? []),
    onSuccess: invalidate,
    retry: false,
  });
}

export function useMarkUnread() {
  const invalidate = useNotificationInvalidation();
  return useMutation({
    mutationFn: (id: number) => notificationsApi.markUnread(id),
    onSuccess: invalidate,
    retry: false,
  });
}

export function useDeleteNotification() {
  const invalidate = useNotificationInvalidation();
  return useMutation({
    mutationFn: (id: number) => notificationsApi.remove(id),
    onSuccess: invalidate,
    retry: false,
  });
}

export function useClearNotifications() {
  const invalidate = useNotificationInvalidation();
  return useMutation({
    mutationFn: () => notificationsApi.clear(),
    onSuccess: invalidate,
    retry: false,
  });
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: qk.notifications.preferences,
    queryFn: () => notificationsApi.preferences(),
    staleTime: 5 * 60_000,
  });
}

export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<NotificationPreferences>) =>
      notificationsApi.updatePreferences(payload),
    onSuccess: (prefs) => queryClient.setQueryData(qk.notifications.preferences, prefs),
    retry: false,
  });
}

/**
 * Live badge updates over the notification WebSocket.
 *
 * WHY THIS ONLY INVALIDATES AND NEVER RENDERS THE PUSHED PAYLOAD
 * -------------------------------------------------------------
 * The frame carries the whole notification, and it would be tempting to prepend
 * it to the cached list. But the socket can drop and reconnect having missed
 * frames, so a cache built from pushed messages drifts from the table. Treating
 * the frame purely as "something changed, refetch" keeps one source of truth —
 * the same reason the backend writes to MySQL before broadcasting.
 *
 * Every failure path is silent: a bell that stops streaming still updates on
 * poll and on open, so a Redis outage must not surface as an error.
 */
export function useNotificationSocket(enabled: boolean) {
  const queryClient = useQueryClient();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = async () => {
      const token = await tokenStorage.getAccess();
      if (!token || cancelled) return;

      try {
        const socket = new WebSocket(WS_ROUTES.notifications(token));
        socketRef.current = socket;

        socket.onmessage = () => {
          queryClient.invalidateQueries({ queryKey: qk.notifications.all });
        };
        socket.onclose = () => {
          // One unobtrusive reconnect attempt. A tight loop against a server
          // that is down would drain the battery to no purpose.
          if (!cancelled) retry = setTimeout(connect, 15_000);
        };
        socket.onerror = () => socket.close();
      } catch {
        // A missing or blocked socket is not an error the user can act on.
      }
    };

    connect();
    return () => {
      cancelled = true;
      if (retry) clearTimeout(retry);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [enabled, queryClient]);
}
