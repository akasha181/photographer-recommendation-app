import { Ionicons } from '@expo/vector-icons';
import React, { useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ApiError } from '../../../api/client';
import { EmptyState, LoadingState } from '../../../components/feedback/States';
import { Avatar } from '../../../components/ui/Avatar';
import { useDebounce } from '../../../hooks/useDebounce';
import { colors, spacing, typography } from '../../../theme';
import { useChatContacts, useStartConversation } from '../hooks/useChat';

/**
 * The "New message" picker.
 *
 * WHY THE LIST COMES FROM THE SERVER AND NOT FROM A USER SEARCH
 * -----------------------------------------------------------
 * `/chat/conversations/contacts/` returns exactly the people the server would
 * let this user message: approved photographers for a buyer, and buyers they
 * have a booking with for a photographer. A generic user search would offer
 * names the POST then refuses — a picker that lists somebody unreachable is
 * worse than a shorter picker.
 */
export function NewChatScreen({
  onBack,
  onOpenThread,
}: {
  onBack: () => void;
  onOpenThread: (conversationId: number, name: string) => void;
}) {
  const [term, setTerm] = useState('');
  const debounced = useDebounce(term, 350);
  const contacts = useChatContacts(debounced);
  const start = useStartConversation();

  const open = (userId: number, name: string) =>
    start.mutate(
      { user: userId },
      {
        onSuccess: (conversation) => onOpenThread(conversation.id, name),
        onError: (error) =>
          Alert.alert('Could not open a conversation', (error as ApiError).message),
      },
    );

  const rows = contacts.data ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.title}>New message</Text>
      </View>

      <View style={styles.searchWrap}>
        <Ionicons name="search" size={17} color={colors.dim} />
        <TextInput
          value={term}
          onChangeText={setTerm}
          placeholder="Search by name"
          placeholderTextColor={colors.dim}
          style={styles.search}
          autoCorrect={false}
        />
      </View>

      {contacts.isLoading ? (
        <LoadingState label="Loading contacts…" />
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={rows.length ? styles.list : styles.listEmpty}
          renderItem={({ item }) => (
            <Pressable
              style={styles.row}
              onPress={() => open(item.id, item.business_name ?? item.full_name)}
              disabled={start.isPending}
              accessibilityRole="button"
              accessibilityLabel={`Message ${item.business_name ?? item.full_name}`}
            >
              <Avatar name={item.full_name} uri={item.avatar_url} size={42} />
              <View style={styles.rowBody}>
                <Text style={styles.name}>{item.business_name ?? item.full_name}</Text>
                <Text style={styles.meta}>
                  {item.role === 'PHOTOGRAPHER' ? 'Photographer' : 'Buyer'}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={17} color={colors.dim} />
            </Pressable>
          )}
          ListEmptyComponent={
            <EmptyState
              icon="people-outline"
              title={debounced ? 'Nobody matches that' : 'No contacts yet'}
              detail={
                debounced
                  ? 'Try a different name.'
                  : 'Users you can message appear here. Search by name to start a conversation.'
              }
            />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
  },
  title: { ...typography.h2, color: colors.text },
  searchWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.xl,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.md,
    height: 44,
    backgroundColor: colors.card,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
  },
  search: { ...typography.body, color: colors.text, flex: 1 },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl },
  listEmpty: { flexGrow: 1 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowBody: { flex: 1 },
  name: { ...typography.bodyBold, color: colors.text },
  meta: { ...typography.tiny, color: colors.sub, marginTop: 1 },
});
