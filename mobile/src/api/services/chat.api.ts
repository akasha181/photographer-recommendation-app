/**
 * Chat API — Module 13.
 *
 * THE `client_id` IS WHAT MAKES SENDING SAFE
 * -----------------------------------------
 * The app draws the bubble the instant the user hits send, then posts with a
 * `client_id`. `(conversation, client_id)` is uniquely constrained server-side,
 * so a retry after a dropped response returns the SAME message rather than
 * posting a second one — and the id in the reply is how the optimistic bubble
 * gets reconciled with the real row.
 *
 * PAGING IS BY MESSAGE ID, NOT PAGE NUMBER
 * ---------------------------------------
 * New rows arrive constantly at the end of a thread, so "page 2" means
 * something different by the time it is fetched. `after` replays what a
 * reconnecting client missed; `before` is scroll-back.
 */

import { api, unwrap, unwrapFull } from '../client';
import { ENDPOINTS } from '../config';
import type {
  ChatContact,
  Conversation,
  ConversationDetail,
  Message,
} from '../../types/models';

/** A unique key per send attempt. `crypto.randomUUID` is absent in Hermes. */
export function messageClientId(): string {
  return `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export const chatApi = {
  // ─── Threads ─────────────────────────────────────────────────────────────
  async conversations(
    options: { archived?: boolean; unreadOnly?: boolean } = {},
  ): Promise<{ items: Conversation[]; unreadTotal: number }> {
    const envelope = await unwrapFull<Conversation[]>(
      api.get(ENDPOINTS.chat.conversations, {
        params: {
          archived: options.archived ? 1 : undefined,
          unread: options.unreadOnly ? 1 : undefined,
        },
      }),
    );
    return {
      items: envelope.data,
      unreadTotal:
        (envelope.meta as { unread_total?: number } | undefined)?.unread_total ?? 0,
    };
  },

  detail(id: number | string) {
    return unwrap<ConversationDetail>(api.get(ENDPOINTS.chat.conversation(id)));
  },

  /**
   * Open a thread with someone, or get the existing one.
   *
   * Idempotent by design: 201 means it was created, 200 means it already
   * existed. Either way the caller gets the thread it asked for.
   */
  start(payload: { user: number; booking?: number | null; message?: string }) {
    return unwrap<ConversationDetail>(api.post(ENDPOINTS.chat.conversations, payload));
  },

  // ─── Messages ────────────────────────────────────────────────────────────
  messages(
    conversationId: number | string,
    options: { after?: number; before?: number; limit?: number } = {},
  ) {
    return unwrap<Message[]>(
      api.get(ENDPOINTS.chat.messages(conversationId), {
        params: { after: options.after, before: options.before, limit: options.limit },
      }),
    );
  },

  send(
    conversationId: number | string,
    body: string,
    clientId = messageClientId(),
  ) {
    return unwrap<Message>(
      api.post(ENDPOINTS.chat.messages(conversationId), {
        body,
        client_id: clientId,
      }),
    );
  },

  sendAttachment(
    conversationId: number | string,
    file: { uri: string; name?: string; type?: string },
    body = '',
    clientId = messageClientId(),
  ) {
    const form = new FormData();
    if (body) form.append('body', body);
    form.append('client_id', clientId);
    form.append('message_type', file.type?.startsWith('image/') ? 'IMAGE' : 'FILE');
    form.append('attachments', {
      uri: file.uri,
      name: file.name ?? 'attachment.jpg',
      type: file.type ?? 'image/jpeg',
    } as unknown as Blob);

    return unwrap<Message>(
      api.post(ENDPOINTS.chat.messages(conversationId), form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }),
    );
  },

  edit(messageId: number, body: string) {
    return unwrap<Message>(api.patch(ENDPOINTS.chat.message(messageId), { body }));
  },

  async remove(messageId: number): Promise<void> {
    await api.delete(ENDPOINTS.chat.message(messageId));
  },

  report(messageId: number, reason: string, detail = '') {
    return unwrap<{ flag_id: number; status: string }>(
      api.post(ENDPOINTS.chat.reportMessage(messageId), { reason, detail }),
    );
  },

  // ─── Read state & settings ───────────────────────────────────────────────
  markRead(conversationId: number | string, upTo?: number) {
    return unwrap<{ unread_count: number }>(
      api.post(ENDPOINTS.chat.read(conversationId), { up_to: upTo ?? null }),
    );
  },

  toggleMute(conversationId: number | string) {
    return unwrap<{ is_muted: boolean }>(api.post(ENDPOINTS.chat.mute(conversationId), {}));
  },

  toggleBlock(conversationId: number | string) {
    return unwrap<{ is_blocked: boolean }>(
      api.post(ENDPOINTS.chat.block(conversationId), {}),
    );
  },

  toggleArchive(conversationId: number | string) {
    return unwrap<{ is_archived: boolean }>(
      api.post(ENDPOINTS.chat.archive(conversationId), {}),
    );
  },

  leave(conversationId: number | string) {
    return unwrap<{ left: boolean }>(api.post(ENDPOINTS.chat.leave(conversationId), {}));
  },

  unreadTotal() {
    return unwrap<{ unread_total: number }>(api.get(ENDPOINTS.chat.unreadCount));
  },

  /** Who this user may start a thread with — mirrors the server's own rule. */
  contacts(term = '') {
    return unwrap<ChatContact[]>(
      api.get(ENDPOINTS.chat.contacts, { params: { q: term || undefined } }),
    );
  },
};
