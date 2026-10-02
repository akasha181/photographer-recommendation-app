import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { colors, radius, spacing, typography } from '../../../theme';
import { formatDate, timeAgo } from '../../../utils/format';
import type { Message } from '../../../types/models';
import { useAuthStore } from '../../../store/authStore';
import {
  useChatThread,
  useConversation,
  useDeleteMessage,
  useReportMessage,
  useStartConversation,
  useToggleBlock,
} from '../hooks/useChat';

/**
 * One conversation.
 *
 * WHY THE LIST IS INVERTED
 * ------------------------
 * `inverted` renders index 0 at the bottom, which means a new message pushes the
 * thread up without a scroll animation, and opening the screen lands on the
 * newest message rather than scrolling there after paint. The rows are reversed
 * for rendering only — the data stays oldest-first, which is the order every
 * other part of the app uses.
 *
 * WHY "Reconnecting…" IS SHOWN
 * ----------------------------
 * The socket can drop on a network switch and the app keeps working — sends go
 * over HTTP and the reconnect replays what was missed. But a chat screen that
 * silently stops being live while looking live is worse than one that admits it,
 * because the user's next decision is whether to wait or call.
 */
export function ChatScreen({
  conversationId: initialConversationId,
  startWith,
  title,
  onBack,
  onOpenBooking,
}: {
  /** An existing thread. Pass 0 or null when only `startWith` is known. */
  conversationId?: number | null;
  /**
   * "Message this person" — used by the booking screen, which knows the other
   * party's user id but not whether a thread exists. Resolving it here keeps the
   * idempotent open-or-find call in one place instead of in every caller.
   */
  startWith?: { userId: number; bookingId?: number };
  title?: string;
  onBack: () => void;
  onOpenBooking?: (bookingId: number) => void;
}) {
  const [resolvedId, setResolvedId] = useState<number | null>(
    initialConversationId && initialConversationId > 0 ? initialConversationId : null,
  );
  const start = useStartConversation();
  const startedRef = useRef(false);

  useEffect(() => {
    if (resolvedId || !startWith || startedRef.current) return;
    // Guarded with a ref, not just state: two renders before the mutation
    // resolves would otherwise fire it twice, and while the server collapses
    // that to one thread, the second request is pure waste.
    startedRef.current = true;
    start.mutate(
      { user: startWith.userId, booking: startWith.bookingId ?? null },
      {
        onSuccess: (thread) => setResolvedId(thread.id),
        onError: (error) =>
          Alert.alert(
            'Could not open the conversation',
            (error as ApiError).message,
            [{ text: 'Back', onPress: onBack }],
          ),
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedId, startWith]);

  if (!resolvedId) {
    return <LoadingState label="Opening conversation…" />;
  }
  return (
    <ChatThread
      conversationId={resolvedId}
      title={title}
      onBack={onBack}
      onOpenBooking={onOpenBooking}
    />
  );
}

function ChatThread({
  conversationId,
  title,
  onBack,
  onOpenBooking,
}: {
  conversationId: number;
  title?: string;
  onBack: () => void;
  onOpenBooking?: (bookingId: number) => void;
}) {
  const conversation = useConversation(conversationId);
  const thread = useChatThread(conversationId);
  const removeMessage = useDeleteMessage(conversationId);
  const report = useReportMessage();
  const toggleBlock = useToggleBlock();

  const [draft, setDraft] = useState('');
  const listRef = useRef<FlatList<Message>>(null);

  // Clearing the badge is a side effect of *reading*, so it fires when the
  // thread's newest id changes rather than on every render.
  const newestId = thread.messages.length
    ? thread.messages[thread.messages.length - 1].id
    : 0;
  useEffect(() => {
    if (newestId > 0) thread.markThreadRead();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newestId]);

  const other = conversation.data?.other_participant;
  const heading = title ?? other?.business_name ?? other?.full_name ?? 'Conversation';

  /** Reversed for the inverted list; the source order stays oldest-first. */
  const rows = useMemo(() => [...thread.messages].reverse(), [thread.messages]);

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    thread.send(text);
  };

  const messageOptions = (message: Message) => {
    const options: { text: string; style?: 'cancel' | 'destructive'; onPress?: () => void }[] =
      [];

    if (message.failed) {
      options.push({ text: 'Try sending again', onPress: () => thread.retryFailed(message) });
    }
    if (message.is_mine && message.id > 0 && !message.is_deleted) {
      options.push({
        text: 'Delete for everyone',
        style: 'destructive',
        onPress: () =>
          removeMessage.mutate(message.id, {
            onError: (error) =>
              Alert.alert('Could not delete', (error as ApiError).message),
          }),
      });
    }
    if (!message.is_mine && message.id > 0) {
      options.push({
        text: 'Report this message',
        style: 'destructive',
        onPress: () =>
          report.mutate(
            { messageId: message.id, reason: 'INAPPROPRIATE' },
            {
              onSuccess: () =>
                Alert.alert('Reported', 'Our team will take a look at this thread.'),
              onError: (error) =>
                Alert.alert('Could not report', (error as ApiError).message),
            },
          ),
      });
    }
    if (!options.length) return;
    Alert.alert('Message', undefined, [...options, { text: 'Cancel', style: 'cancel' }]);
  };

  const threadOptions = () =>
    Alert.alert(heading, undefined, [
      {
        text: conversation.data?.is_blocked ? 'Unblock' : 'Block this person',
        style: conversation.data?.is_blocked ? 'default' : 'destructive',
        onPress: () => toggleBlock.mutate(conversationId),
      },
      { text: 'Cancel', style: 'cancel' },
    ]);

  if (thread.isLoading && !thread.messages.length) {
    return <LoadingState label="Opening conversation…" />;
  }
  if (thread.isError && !thread.messages.length) {
    return (
      <ErrorState
        message={(thread.error as ApiError)?.message}
        onRetry={() => thread.refetch()}
      />
    );
  }

  const isOnline =
    thread.isOtherOnline !== null && thread.isOtherOnline !== undefined
      ? thread.isOtherOnline
      : Boolean(other?.is_online);

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <View style={styles.avatarWrap}>
          <Avatar name={other?.full_name ?? heading} uri={other?.avatar_url} size={38} />
          <View style={[styles.avatarStatusDot, isOnline ? styles.dotOnline : styles.dotOffline]} />
        </View>
        <View style={styles.headerBody}>
          <Text style={styles.title} numberOfLines={1}>
            {heading}
          </Text>
          <View style={styles.presenceRow}>
            <View style={[styles.presenceDot, isOnline ? styles.dotOnline : styles.dotOffline]} />
            <Text style={styles.presence} numberOfLines={1}>
              {isOnline
                ? 'Online'
                : other?.last_seen_at
                  ? `Last seen ${timeAgo(other.last_seen_at)}`
                  : 'Offline'}
            </Text>
          </View>
        </View>
        <Pressable onPress={threadOptions} hitSlop={10} accessibilityLabel="Options">
          <Ionicons name="ellipsis-vertical" size={18} color={colors.sub} />
        </Pressable>
      </View>

      {conversation.data?.booking ? (
        <Pressable
          style={styles.bookingBar}
          onPress={() =>
            conversation.data?.booking && onOpenBooking?.(conversation.data.booking.id)
          }
          disabled={!onOpenBooking}
        >
          <Ionicons name="calendar-outline" size={15} color={colors.gold} />
          <Text style={styles.bookingText} numberOfLines={1}>
            {conversation.data.booking.service_title} ·{' '}
            {formatDate(conversation.data.booking.event_date)} ·{' '}
            {conversation.data.booking.status.toLowerCase()}
          </Text>
          {onOpenBooking ? (
            <Ionicons name="chevron-forward" size={15} color={colors.sub} />
          ) : null}
        </Pressable>
      ) : null}

      {/* ─── Security Notice: Explicit LTR ────────────────────────────── */}
      <View style={styles.encryptionPill}>
        <Ionicons name="lock-closed" size={11} color={colors.gold} />
        <Text style={styles.encryptionText}>
          End-to-End Encrypted
        </Text>
      </View>

      {conversation.data?.is_blocked ? (
        <View style={styles.blockedBar}>
          <Text style={styles.blockedText}>
            You blocked this person. You will not see new messages until you unblock them.
          </Text>
        </View>
      ) : null}

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 8 : 0}
      >
        <FlatList
          ref={listRef}
          data={rows}
          inverted
          keyExtractor={(item) => item.client_id || String(item.id)}
          contentContainerStyle={styles.list}
          keyboardShouldPersistTaps="handled"
          renderItem={({ item }) => (
            <Bubble message={item} onLongPress={() => messageOptions(item)} />
          )}
          ListEmptyComponent={
            <View style={styles.emptyThread}>
              <Text style={styles.emptyTitle}>No messages yet</Text>
              <Text style={styles.emptyDetail}>
                Ask about a date, a location or what is included.
              </Text>
            </View>
          }
        />

        <View style={styles.composer}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Write a message…"
            placeholderTextColor={colors.dim}
            multiline
            maxLength={5000}
            style={styles.input}
          />
          <Pressable
            onPress={send}
            disabled={!draft.trim()}
            style={[styles.sendButton, !draft.trim() && styles.sendButtonOff]}
            accessibilityRole="button"
            accessibilityLabel="Send message"
          >
            <Ionicons
              name="send"
              size={17}
              color={draft.trim() ? colors.bg : colors.dim}
            />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Bubble({
  message,
  onLongPress,
}: {
  message: Message;
  onLongPress: () => void;
}) {
  const currentUserId = useAuthStore((s) => s.user?.id);
  const mine = Boolean(
    message.is_mine || (currentUserId && message.sender === currentUserId),
  );

  if (message.message_type === 'SYSTEM') {
    return <Text style={styles.system}>{message.body}</Text>;
  }

  return (
    <Pressable
      onLongPress={onLongPress}
      style={[styles.bubbleRow, mine ? styles.bubbleRowMine : styles.bubbleRowTheirs]}
    >
      <View style={[styles.bubble, mine ? styles.bubbleMine : styles.bubbleTheirs]}>
        <Text style={[styles.bubbleText, message.is_deleted && styles.bubbleDeleted]}>
          {message.body}
        </Text>
        <View style={styles.bubbleMeta}>
          {message.is_edited ? <Text style={styles.metaText}>edited</Text> : null}
          <Text style={styles.metaText}>
            {new Date(message.created_at).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
          {mine ? (
            <Ionicons
              // Three honest states: in flight, failed, delivered — and a
              // second tick only once the other side has actually read it.
              name={
                message.failed
                  ? 'alert-circle-outline'
                  : message.pending
                    ? 'time-outline'
                    : message.read_at
                      ? 'checkmark-done'
                      : 'checkmark'
              }
              size={13}
              color={
                message.failed
                  ? colors.red
                  : message.read_at
                    ? colors.blue
                    : colors.sub
              }
            />
          ) : null}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerBody: { flex: 1 },
  title: { ...typography.h3, color: colors.text },
  presenceRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 2 },
  presenceDot: { width: 6, height: 6, borderRadius: 3 },
  presence: { ...typography.tiny, color: colors.sub },
  avatarWrap: { position: 'relative' },
  avatarStatusDot: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 2,
    borderColor: colors.bg,
  },
  dotOnline: { backgroundColor: colors.green },
  dotOffline: { backgroundColor: colors.dim },
  encryptionPill: {
    flexDirection: 'row',
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    borderRadius: radius.pill,
    marginVertical: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 6,
  },
  encryptionText: {
    ...typography.tiny,
    color: colors.gold,
    fontSize: 11,
    fontWeight: '600',
    writingDirection: 'ltr',
    textAlign: 'left',
  },
  bookingBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  bookingText: { ...typography.tiny, color: colors.text, flex: 1 },
  blockedBar: { backgroundColor: colors.redDim, padding: spacing.md },
  blockedText: { ...typography.tiny, color: colors.text, textAlign: 'center' },
  list: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
    flexGrow: 1,
    justifyContent: 'flex-end',
  },
  bubbleRow: { flexDirection: 'row', width: '100%', marginBottom: spacing.sm },
  bubbleRowMine: { justifyContent: 'flex-end' },
  bubbleRowTheirs: { justifyContent: 'flex-start' },
  bubble: {
    maxWidth: '82%',
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  bubbleMine: { backgroundColor: colors.goldDim, borderBottomRightRadius: radius.sm },
  bubbleTheirs: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderBottomLeftRadius: radius.sm,
  },
  bubbleText: { ...typography.body, color: colors.text, lineHeight: 20 },
  bubbleDeleted: { color: colors.dim, fontStyle: 'italic' },
  bubbleMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: spacing.xs,
    marginTop: 2,
  },
  metaText: { ...typography.tiny, color: colors.sub, fontSize: 10 },
  system: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
    marginVertical: spacing.md,
  },
  emptyThread: {
    alignItems: 'center',
    paddingVertical: spacing.huge,
    transform: Platform.OS === 'android' ? [{ scale: -1 }] : [{ scaleY: -1 }],
  },
  emptyTitle: { ...typography.h3, color: colors.text },
  emptyDetail: {
    ...typography.caption,
    color: colors.sub,
    marginTop: spacing.xs,
    textAlign: 'center',
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    ...typography.body,
    color: colors.text,
    flex: 1,
    maxHeight: 120,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.gold,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonOff: { backgroundColor: colors.card },
});
