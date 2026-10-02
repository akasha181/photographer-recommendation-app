/**
 * React Query hooks for chat — Module 13.
 *
 * THE SOCKET IS AN ACCELERATOR, NOT THE SOURCE OF TRUTH
 * ----------------------------------------------------
 * `useMessages` owns the thread cache and is filled from HTTP. The socket only
 * appends what it receives and, on reconnect, triggers a `?after=<last id>`
 * fetch that replays whatever it missed. Building the thread FROM socket frames
 * is how chat apps lose messages when a phone switches from Wi-Fi to data.
 *
 * SENDING IS OPTIMISTIC BUT RECONCILED BY `client_id`
 * -------------------------------------------------
 * The bubble appears instantly with a temporary negative id. When the POST
 * returns, the real row replaces it — matched on `client_id`, not on position,
 * because two quick sends can resolve out of order. A failed send leaves the
 * bubble marked `failed` rather than silently vanishing.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { tokenStorage } from '../../../api/client';
import { WS_ROUTES } from '../../../api/config';
import { qk } from '../../../api/queryKeys';
import { chatApi, messageClientId } from '../../../api/services/chat.api';
import { useAuthStore } from '../../../store/authStore';
import type { Message } from '../../../types/models';

// ═══════════════════════════════════════════════════════════════════════════
// THREAD LIST
// ═══════════════════════════════════════════════════════════════════════════
export function useConversations(archived = false) {
  return useQuery({
    queryKey: qk.chat.conversations(archived),
    queryFn: () => chatApi.conversations({ archived }),
    staleTime: 20_000,
    refetchOnWindowFocus: true,
  });
}

export function useConversation(id: number | null) {
  return useQuery({
    queryKey: qk.chat.conversation(id ?? 0),
    queryFn: () => chatApi.detail(id!),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

export function useChatUnreadTotal() {
  return useQuery({
    queryKey: qk.chat.unread,
    queryFn: () => chatApi.unreadTotal(),
    staleTime: 20_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useStartConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { user: number; booking?: number | null; message?: string }) =>
      chatApi.start(payload),
    // Idempotent server-side, so a double-tap is safe — but the list ordering
    // and the badge both moved.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.chat.all }),
    retry: false,
  });
}

export function useChatContacts(term = '') {
  return useQuery({
    queryKey: qk.chat.contacts(term),
    queryFn: () => chatApi.contacts(term),
    staleTime: 60_000,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// PER-THREAD SETTINGS
// ═══════════════════════════════════════════════════════════════════════════
function useThreadToggle<T>(fn: (id: number) => Promise<T>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.chat.all }),
    retry: false,
  });
}

export function useToggleMute() {
  return useThreadToggle((id: number) => chatApi.toggleMute(id));
}

export function useToggleBlock() {
  return useThreadToggle((id: number) => chatApi.toggleBlock(id));
}

export function useToggleArchive() {
  return useThreadToggle((id: number) => chatApi.toggleArchive(id));
}

export function useLeaveConversation() {
  return useThreadToggle((id: number) => chatApi.leave(id));
}

export function useMarkThreadRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, upTo }: { id: number; upTo?: number }) =>
      chatApi.markRead(id, upTo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.chat.conversations(false) });
      queryClient.invalidateQueries({ queryKey: qk.chat.unread });
    },
    retry: false,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// THE THREAD ITSELF
// ═══════════════════════════════════════════════════════════════════════════
export function useMessages(conversationId: number | null) {
  return useQuery({
    queryKey: qk.chat.messages(conversationId ?? 0),
    queryFn: () => chatApi.messages(conversationId!, { limit: 50 }),
    enabled: Boolean(conversationId),
    // The socket keeps this fresh while the screen is open; the fetch is for
    // opening it and for reconnecting.
    staleTime: 10_000,
  });
}

/**
 * The full send/receive loop for one open thread.
 *
 * Returns the message list to render (server rows plus any optimistic bubbles),
 * a `send` function, and the socket's connection state so the header can say
 * "reconnecting…" honestly instead of pretending everything is live.
 */
export function useChatThread(conversationId: number | null) {
  const queryClient = useQueryClient();
  const messages = useMessages(conversationId);
  const markRead = useMarkThreadRead();

  const [pending, setPending] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const [otherOnline, setOtherOnline] = useState<boolean | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const key = qk.chat.messages(conversationId ?? 0);

  /** Merge a server row in, replacing its optimistic twin if there is one. */
  const absorb = useCallback(
    (incoming: Message) => {
      queryClient.setQueryData<Message[]>(key, (rows = []) => {
        const existingIndex = rows.findIndex(
          (row) =>
            row.id === incoming.id ||
            Boolean(incoming.client_id && row.client_id && row.client_id === incoming.client_id),
        );
        if (existingIndex !== -1) {
          const updated = [...rows];
          updated[existingIndex] = {
            ...updated[existingIndex],
            ...incoming,
            is_mine: Boolean(updated[existingIndex].is_mine || incoming.is_mine),
          };
          return updated;
        }
        return [...rows, incoming];
      });
      if (incoming.client_id) {
        setPending((rows) => rows.filter((row) => row.client_id !== incoming.client_id));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [conversationId, queryClient],
  );

  // ─── Socket ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!conversationId) return;
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let heartbeat: ReturnType<typeof setInterval> | undefined;

    const connect = async () => {
      const token = await tokenStorage.getAccess();
      if (!token || cancelled) return;

      try {
        const socket = new WebSocket(WS_ROUTES.chat(conversationId, token));
        socketRef.current = socket;

        socket.onopen = () => {
          if (cancelled) return;
          setConnected(true);
          // Periodic heartbeat keeps the connection alive through NAT firewalls
          heartbeat = setInterval(() => {
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: 'heartbeat' }));
            }
          }, 15_000);

          // Replay whatever arrived while the socket was down. This is the
          // whole reason messages are addressed by id rather than by page.
          const rows = queryClient.getQueryData<Message[]>(key) ?? [];
          const lastId = rows.length ? rows[rows.length - 1].id : undefined;
          chatApi
            .messages(conversationId, { after: lastId, limit: 100 })
            .then((missed) => missed.forEach(absorb))
            .catch(() => undefined);
        };

        socket.onmessage = (event) => {
          try {
            const frame = JSON.parse(event.data as string);
            if (frame.type === 'connected') {
              if (frame.other_online !== undefined) {
                setOtherOnline(Boolean(frame.other_online));
              }
            } else if (frame.type === 'message') {
              const currentUserId = useAuthStore.getState().user?.id;
              const isMine =
                frame.is_mine !== undefined
                  ? Boolean(frame.is_mine)
                  : Boolean(currentUserId && frame.sender_id === currentUserId);

              absorb({
                id: frame.id,
                conversation: frame.conversation_id,
                sender: frame.sender_id,
                sender_name: frame.sender_name ?? '',
                sender_avatar: null,
                is_mine: isMine,
                message_type: frame.message_type ?? 'TEXT',
                body: frame.body ?? '',
                client_id: frame.client_id ?? '',
                is_edited: false,
                is_deleted: false,
                attachments: [],
                delivered_at: null,
                read_at: null,
                created_at: frame.created_at,
              });
              queryClient.invalidateQueries({ queryKey: qk.chat.unread });
            } else if (frame.type === 'delete') {
              queryClient.setQueryData<Message[]>(key, (rows = []) =>
                rows.map((row) =>
                  row.id === frame.id
                    ? { ...row, is_deleted: true, body: 'This message was deleted' }
                    : row,
                ),
              );
              queryClient.invalidateQueries({ queryKey: qk.chat.conversations(false) });
            } else if (frame.type === 'presence') {
              setOtherOnline(Boolean(frame.is_online));
            }
          } catch {
            // A malformed frame is not worth breaking the screen over.
          }
        };

        socket.onclose = () => {
          if (heartbeat) clearInterval(heartbeat);
          setConnected(false);
          if (!cancelled) retry = setTimeout(connect, 3_000);
        };
        socket.onerror = () => socket.close();
      } catch {
        setConnected(false);
      }
    };

    connect();
    return () => {
      cancelled = true;
      if (heartbeat) clearInterval(heartbeat);
      if (retry) clearTimeout(retry);
      socketRef.current?.close();
      socketRef.current = null;
      setConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  // ─── Sending ─────────────────────────────────────────────────────────────
  const send = useCallback(
    async (body: string) => {
      const text = body.trim();
      if (!conversationId || !text) return;

      const currentUser = useAuthStore.getState().user;
      const clientId = messageClientId();
      const optimistic: Message = {
        // A negative id can never collide with a server row, which makes
        // "is this bubble real yet?" a check rather than a guess.
        id: -Date.now(),
        conversation: conversationId,
        sender: currentUser?.id ?? -1,
        sender_name: currentUser?.full_name ?? '',
        sender_avatar: null,
        is_mine: true,
        message_type: 'TEXT',
        body: text,
        client_id: clientId,
        is_edited: false,
        is_deleted: false,
        attachments: [],
        delivered_at: null,
        read_at: null,
        created_at: new Date().toISOString(),
        pending: true,
      };
      setPending((rows) => [...rows, optimistic]);

      try {
        const saved = await chatApi.send(conversationId, text, clientId);
        absorb(saved);
        queryClient.invalidateQueries({ queryKey: qk.chat.conversations(false) });
      } catch {
        // Kept on screen and marked failed. Dropping it silently would look
        // like the message was sent.
        setPending((rows) =>
          rows.map((row) =>
            row.client_id === clientId ? { ...row, pending: false, failed: true } : row,
          ),
        );
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [conversationId, absorb, queryClient],
  );

  const retryFailed = useCallback(
    (message: Message) => {
      setPending((rows) => rows.filter((row) => row.client_id !== message.client_id));
      send(message.body);
    },
    [send],
  );

  const markThreadRead = useCallback(() => {
    if (!conversationId) return;
    const rows = queryClient.getQueryData<Message[]>(key) ?? [];
    const lastId = rows.length ? rows[rows.length - 1].id : undefined;
    if (lastId && lastId > 0) markRead.mutate({ id: conversationId, upTo: lastId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, queryClient]);

  const serverRows = messages.data ?? [];
  const pendingRows = pending.filter(
    (row) => !serverRows.some((saved) => saved.client_id && saved.client_id === row.client_id),
  );

  return {
    messages: [...serverRows, ...pendingRows],
    isLoading: messages.isLoading,
    isError: messages.isError,
    error: messages.error,
    refetch: messages.refetch,
    connected,
    isOtherOnline: otherOnline,
    send,
    retryFailed,
    markThreadRead,
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// SINGLE MESSAGE ACTIONS
// ═══════════════════════════════════════════════════════════════════════════
export function useDeleteMessage(conversationId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: number) => chatApi.remove(messageId),
    onSuccess: (_data, messageId) => {
      if (conversationId) {
        queryClient.setQueryData<Message[]>(qk.chat.messages(conversationId), (rows = []) =>
          rows.map((row) =>
            row.id === messageId
              ? { ...row, is_deleted: true, body: 'This message was deleted' }
              : row,
          ),
        );
      }
      queryClient.invalidateQueries({ queryKey: qk.chat.messages(conversationId ?? 0) });
      queryClient.invalidateQueries({ queryKey: qk.chat.conversations(false) });
    },
    retry: false,
  });
}

export function useReportMessage() {
  return useMutation({
    mutationFn: ({
      messageId,
      reason,
      detail,
    }: {
      messageId: number;
      reason: string;
      detail?: string;
    }) => chatApi.report(messageId, reason, detail),
    retry: false,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// GLOBAL PRESENCE TRACKER
// ═══════════════════════════════════════════════════════════════════════════
/**
 * Global presence socket hook.
 * Connects to /ws/presence/ while the user is logged in and sends regular heartbeats.
 * Ensures the photographer shows online to buyers and vice versa throughout the app.
 */
export function usePresenceTracker(enabled: boolean) {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let socket: WebSocket | null = null;
    let heartbeat: ReturnType<typeof setInterval> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const stopHeartbeat = () => {
      if (heartbeat) {
        clearInterval(heartbeat);
        heartbeat = undefined;
      }
    };

    const stopRetry = () => {
      if (retry) {
        clearTimeout(retry);
        retry = undefined;
      }
    };

    const disconnectSocket = (sendOffline = true) => {
      stopHeartbeat();
      stopRetry();
      if (socket) {
        if (sendOffline && socket.readyState === WebSocket.OPEN) {
          try {
            socket.send(JSON.stringify({ type: 'offline' }));
          } catch {}
        }
        try {
          socket.close();
        } catch {}
        socket = null;
      }
    };

    const connect = async () => {
      if (cancelled || AppState.currentState !== 'active') return;
      const token = await tokenStorage.getAccess();
      if (!token || cancelled || AppState.currentState !== 'active') return;

      disconnectSocket(false);

      try {
        const ws = new WebSocket(WS_ROUTES.presence(token));
        socket = ws;

        ws.onopen = () => {
          if (cancelled || AppState.currentState !== 'active') {
            disconnectSocket(true);
            return;
          }
          stopHeartbeat();
          heartbeat = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'heartbeat' }));
            }
          }, 15_000);
        };

        ws.onmessage = (event) => {
          try {
            const frame = JSON.parse(event.data as string);
            if (frame.type === 'presence' && typeof frame.user_id === 'number') {
              // Instantly update cached conversation list with new status
              queryClient.setQueriesData<any[]>(
                { queryKey: ['chat'] },
                (old) => {
                  if (!Array.isArray(old)) return old;
                  return old.map((conv) => {
                    if (conv?.other_participant?.id === frame.user_id) {
                      return {
                        ...conv,
                        other_participant: {
                          ...conv.other_participant,
                          is_online: Boolean(frame.is_online),
                        },
                      };
                    }
                    return conv;
                  });
                }
              );
              queryClient.invalidateQueries({ queryKey: qk.chat.all });
            }
          } catch {}
        };

        ws.onclose = () => {
          stopHeartbeat();
          if (!cancelled && AppState.currentState === 'active') {
            stopRetry();
            retry = setTimeout(connect, 4_000);
          }
        };

        ws.onerror = () => {
          try {
            ws.close();
          } catch {}
        };
      } catch {
        if (!cancelled && AppState.currentState === 'active') {
          stopRetry();
          retry = setTimeout(connect, 5_000);
        }
      }
    };

    connect();

    const handleAppStateChange = (nextState: AppStateStatus) => {
      if (nextState === 'active') {
        connect();
      } else {
        disconnectSocket(true);
      }
    };

    const appStateSub = AppState.addEventListener('change', handleAppStateChange);

    return () => {
      cancelled = true;
      appStateSub.remove();
      disconnectSocket(true);
    };
  }, [enabled, queryClient]);
}

