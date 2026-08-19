import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { colors, radius, spacing, typography } from '../../../theme';
import { timeAgo } from '../../../utils/format';
import type { Conversation } from '../../../types/models';
import {
  useConversations,
  useToggleArchive,
  useToggleMute,
} from '../hooks/useChat';

/**
 * The Messages list.
 *
 * WHY EVERY ROW RENDERS WITHOUT A PER-ROW QUERY
 * --------------------------------------------
 * `last_message_text`, `last_message_at` and `unread_count` are denormalised on
 * the server and written in the same transaction as each message. Twenty threads
 * is one request — the alternative is twenty "latest message" lookups, which is
 * the single most common performance bug in a chat list.
 *
 * WHY A THREAD WITH NO MESSAGES STILL APPEARS
 * ------------------------------------------
 * A buyer who taps "Message" and then puts their phone down has a real thread
 * with `last_message_at = null`. Ordering it to the bottom would hide it exactly
 * where they will look for it next.
 */
export function ConversationsScreen({
  onBack,
  onOpenThread,
  onNewMessage,
}: {
  onBack?: () => void;
  onOpenThread: (conversationId: number, name: string) => void;
  onNewMessage: () => void;
}) {
  const [archived, setArchived] = useState(false);
  const conversations = useConversations(archived);
  const toggleMute = useToggleMute();
  const toggleArchive = useToggleArchive();

  const rows = conversations.data?.items ?? [];

  const showOptions = (row: Conversation) =>
    Alert.alert(
      row.other_participant?.full_name ?? 'Conversation',
      undefined,
      [
        {
          text: row.is_muted ? 'Unmute' : 'Mute this thread',
          onPress: () => toggleMute.mutate(row.id),
        },
        {
          text: row.is_archived ? 'Unarchive' : 'Archive',
          onPress: () => toggleArchive.mutate(row.id),
        },
        { text: 'Cancel', style: 'cancel' },
      ],
    );

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        {onBack ? (
          <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
            <Ionicons name="chevron-back" size={24} color={colors.text} />
          </Pressable>
        ) : null}
        <View style={styles.headerBody}>
          <Text style={styles.title}>{archived ? 'Archived' : 'Messages'}</Text>
          <Text style={styles.subtitle}>
            {conversations.data?.unreadTotal
              ? `${conversations.data.unreadTotal} unread`
              : 'Talk to the people you work with'}
          </Text>
        </View>
        <Pressable
          onPress={() => setArchived((on) => !on)}
          hitSlop={10}
          accessibilityLabel={archived ? 'Show inbox' : 'Show archived threads'}
        >
          <Ionicons
            name={archived ? 'chatbubbles-outline' : 'archive-outline'}
            size={21}
            color={colors.sub}
          />
        </Pressable>
        <Pressable onPress={onNewMessage} hitSlop={10} accessibilityLabel="New message">
          <Ionicons name="create-outline" size={22} color={colors.gold} />
        </Pressable>
      </View>

      {conversations.isLoading ? (
        <LoadingState label="Loading messages…" />
      ) : conversations.isError ? (
        <ErrorState
          message={(conversations.error as ApiError)?.message}
          onRetry={() => conversations.refetch()}
        />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <ConversationRow
              row={item}
              onPress={() =>
                onOpenThread(
                  item.id,
                  item.other_participant?.business_name ??
                    item.other_participant?.full_name ??
                    'Conversation',
                )
              }
              onLongPress={() => showOptions(item)}
            />
          )}
          ListEmptyComponent={
            <EmptyState
              icon="chatbubbles-outline"
              title={archived ? 'Nothing archived' : 'No messages yet'}
              detail={
                archived
                  ? 'Threads you archive appear here.'
                  : 'Ask a photographer about a date before you book — the conversation stays attached to the booking afterwards.'
              }
              actionLabel={archived ? undefined : 'Start a conversation'}
              onAction={archived ? undefined : onNewMessage}
            />
          }
          refreshControl={
            <RefreshControl
              refreshing={conversations.isRefetching}
              onRefresh={() => conversations.refetch()}
              tintColor={colors.gold}
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

function ConversationRow({
  row,
  onPress,
  onLongPress,
}: {
  row: Conversation;
  onPress: () => void;
  onLongPress: () => void;
}) {
  const other = row.other_participant;
  const name = other?.business_name ?? other?.full_name ?? 'Unknown';
  const unread = row.unread_count > 0;

  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      style={styles.row}
      accessibilityRole="button"
      accessibilityLabel={`Conversation with ${name}${unread ? `, ${row.unread_count} unread` : ''}`}
    >
      <View>
        <Avatar name={other?.full_name ?? name} uri={other?.avatar_url} size={46} />
        {other?.is_online ? <View style={styles.online} /> : null}
      </View>

      <View style={styles.rowBody}>
        <View style={styles.rowTop}>
          <Text style={[styles.name, unread && styles.nameUnread]} numberOfLines={1}>
            {name}
          </Text>
          <Text style={styles.time}>{timeAgo(row.last_message_at)}</Text>
        </View>

        <View style={styles.rowBottom}>
          <Text style={[styles.preview, unread && styles.previewUnread]} numberOfLines={1}>
            {row.last_message_text || 'No messages yet — say hello.'}
          </Text>
          {row.is_muted ? (
            <Ionicons name="notifications-off-outline" size={13} color={colors.dim} />
          ) : null}
          {unread ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>
                {row.unread_count > 9 ? '9+' : row.unread_count}
              </Text>
            </View>
          ) : null}
        </View>

        {row.booking ? (
          <View style={styles.bookingChip}>
            <Ionicons name="calendar-outline" size={11} color={colors.sub} />
            <Text style={styles.bookingText} numberOfLines={1}>
              {row.booking.service_title} · {row.booking.status.toLowerCase()}
            </Text>
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
  },
  headerBody: { flex: 1 },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.sub },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl },
  listEmpty: { flexGrow: 1 },
  row: {
    flexDirection: 'row',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  online: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.green,
    borderWidth: 2,
    borderColor: colors.bg,
  },
  rowBody: { flex: 1, justifyContent: 'center' },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  name: { ...typography.body, color: colors.sub, flex: 1 },
  nameUnread: { ...typography.bodyBold, color: colors.text },
  time: { ...typography.tiny, color: colors.dim },
  rowBottom: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: 2,
  },
  preview: { ...typography.caption, color: colors.dim, flex: 1 },
  previewUnread: { color: colors.text },
  badge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    paddingHorizontal: 5,
    backgroundColor: colors.gold,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { ...typography.tiny, color: colors.bg, fontSize: 10 },
  bookingChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.xs,
    alignSelf: 'flex-start',
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  bookingText: { ...typography.tiny, color: colors.sub, maxWidth: 200 },
});
