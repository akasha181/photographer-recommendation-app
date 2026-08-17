/**
 * Notifications API — Module 12.
 *
 * WHY `markRead([])` MEANS "ALL"
 * -----------------------------
 * The server treats an empty id list as "everything", which is what the
 * "Mark all read" button sends. Enumerating 200 ids to clear a badge would make
 * the request size depend on how long the user ignored it.
 */

import { api, unwrap, unwrapFull } from '../client';
import { ENDPOINTS } from '../config';
import type {
  Notification,
  NotificationBadges,
  NotificationPreferences,
} from '../../types/models';

export interface NotificationPage {
  items: Notification[];
  page: number;
  totalPages: number;
  hasNext: boolean;
  /** The badge that belongs with this page — sent in the same response. */
  unreadCount: number;
}

export const notificationsApi = {
  async list(
    options: { category?: string; unreadOnly?: boolean; page?: number } = {},
  ): Promise<NotificationPage> {
    const envelope = await unwrapFull<Notification[]>(
      api.get(ENDPOINTS.notifications.list, {
        params: {
          category: options.category,
          unread: options.unreadOnly ? 1 : undefined,
          page: options.page ?? 1,
        },
      }),
    );
    const pagination = envelope.meta?.pagination;
    return {
      items: envelope.data,
      page: pagination?.page ?? 1,
      totalPages: pagination?.total_pages ?? 1,
      hasNext: pagination?.has_next ?? false,
      unreadCount:
        (envelope.meta as { unread_count?: number } | undefined)?.unread_count ?? 0,
    };
  },

  badges() {
    return unwrap<NotificationBadges>(api.get(ENDPOINTS.notifications.unreadCount));
  },

  /** Pass no ids — or an empty array — to clear everything. */
  markRead(ids: number[] = []) {
    return unwrap<{ updated: number; unread_count: number }>(
      api.post(ENDPOINTS.notifications.markRead, { ids }),
    );
  },

  markUnread(id: number) {
    return unwrap<{ updated: number; unread_count: number }>(
      api.post(ENDPOINTS.notifications.markUnread(id), {}),
    );
  },

  async remove(id: number): Promise<void> {
    await api.delete(ENDPOINTS.notifications.remove(id));
  },

  /** Removes only what has already been read — an unread cancellation stays. */
  clear() {
    return unwrap<{ removed: number; unread_count: number }>(
      api.post(ENDPOINTS.notifications.clear, {}),
    );
  },

  preferences() {
    return unwrap<NotificationPreferences>(
      api.get(ENDPOINTS.notifications.preferences),
    );
  },

  updatePreferences(payload: Partial<NotificationPreferences>) {
    return unwrap<NotificationPreferences>(
      api.patch(ENDPOINTS.notifications.preferences, payload),
    );
  },

  /**
   * Register this install for push. Safe to call on every launch — the server
   * upserts on (user, token) and deactivates the device's previous token.
   */
  registerDevice(payload: {
    token: string;
    platform: 'IOS' | 'ANDROID' | 'WEB';
    device_id?: string;
  }) {
    return unwrap<{ id: number; token: string }>(
      api.post(ENDPOINTS.notifications.devices, payload),
    );
  },

  unregisterDevice(token: string) {
    return unwrap<{ removed: boolean }>(
      api.post(ENDPOINTS.notifications.removeDevice, { token }),
    );
  },
};
