import { Ionicons } from '@expo/vector-icons';
import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { PhotographerFilters } from '../../../api/services/photographers.api';
import { EmptyState, ErrorState, LoadingState } from '../../../components/feedback/States';
import { useDebounce } from '../../../hooks/useDebounce';
import type { PhotographerSummary } from '../../../types/models';
import { colors, radius, spacing, typography } from '../../../theme';
import { FilterSheet } from '../components/FilterSheet';
import { PhotographerCard } from '../components/PhotographerCard';
import { useCategories, usePhotographers } from '../hooks/usePhotographers';

interface Props {
  onOpenPhotographer: (id: number) => void;
  initialCategory?: string;
}

export function ExploreScreen({ onOpenPhotographer, initialCategory }: Props) {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | undefined>(initialCategory);
  const [filters, setFilters] = useState<PhotographerFilters>({});
  const [sheetOpen, setSheetOpen] = useState(false);

  // 400ms: long enough that a normal typing burst produces one request,
  // short enough that the list still feels immediate.
  const debouncedSearch = useDebounce(search, 400);

  const categories = useCategories();

  const activeFilters = useMemo<PhotographerFilters>(
    () => ({
      ...filters,
      q: debouncedSearch || undefined,
      category,
      page_size: 20,
    }),
    [filters, debouncedSearch, category],
  );

  const query = usePhotographers(activeFilters);

  // Flatten the paginated pages into one array for the FlatList, deduplicating by ID.
  const items = useMemo(() => {
    const raw = query.data?.pages.flatMap((page) => page.items) ?? [];
    const seen = new Set<number>();
    return raw.filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }, [query.data]);
  const total = query.data?.pages[0]?.totalItems ?? 0;

  const loadMore = useCallback(() => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      query.fetchNextPage();
    }
  }, [query]);

  const activeFilterCount = useMemo(
    () => Object.values(filters).filter((v) => v !== undefined && v !== '').length,
    [filters],
  );

  const renderItem = useCallback(
    ({ item }: { item: PhotographerSummary }) => (
      <PhotographerCard
        photographer={item}
        onPress={() => onOpenPhotographer(item.id)}
      />
    ),
    [onOpenPhotographer],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* ─── Search bar ─────────────────────────────────────────────────── */}
      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={17} color={colors.dim} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search photographers, cities…"
            placeholderTextColor={colors.dim}
            style={styles.searchInput}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
            accessibilityLabel="Search photographers"
          />
          {search.length > 0 ? (
            <Pressable onPress={() => setSearch('')} hitSlop={8}>
              <Ionicons name="close-circle" size={17} color={colors.dim} />
            </Pressable>
          ) : null}
        </View>

        <Pressable
          onPress={() => setSheetOpen(true)}
          style={styles.filterButton}
          accessibilityLabel="Open filters"
        >
          <Ionicons name="options-outline" size={19} color={colors.text} />
          {activeFilterCount > 0 ? (
            <View style={styles.filterBadge}>
              <Text style={styles.filterBadgeText}>{activeFilterCount}</Text>
            </View>
          ) : null}
        </Pressable>
      </View>

      {/* ─── Category chips ─────────────────────────────────────────────── */}
      <FlatList
        horizontal
        data={[{ slug: undefined, name: 'All' }, ...(categories.data ?? [])]}
        keyExtractor={(item) => item.slug ?? 'all'}
        showsHorizontalScrollIndicator={false}
        style={styles.chipList}
        contentContainerStyle={styles.chipRow}
        renderItem={({ item }) => {
          const active = category === item.slug;
          return (
            <Pressable
              onPress={() => setCategory(item.slug)}
              style={[styles.chip, active && styles.chipActive]}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>
                {item.name}
              </Text>
            </Pressable>
          );
        }}
      />

      {/* ─── Result count ───────────────────────────────────────────────── */}
      {!query.isLoading ? (
        <Text style={styles.resultCount}>
          {total} photographer{total === 1 ? '' : 's'}
          {debouncedSearch ? ` matching "${debouncedSearch}"` : ''}
        </Text>
      ) : null}

      {/* ─── Results ────────────────────────────────────────────────────── */}
      {query.isLoading ? (
        <LoadingState label="Searching…" />
      ) : query.isError ? (
        <ErrorState
          message={(query.error as Error)?.message}
          onRetry={() => query.refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="No photographers found"
          detail="Try widening your budget, choosing another city, or clearing some filters."
          actionLabel={activeFilterCount > 0 ? 'Clear filters' : undefined}
          onAction={activeFilterCount > 0 ? () => setFilters({}) : undefined}
        />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          showsVerticalScrollIndicator={false}
          onEndReached={loadMore}
          // 0.5 rather than 0.1: on a slow connection the next page needs to
          // start loading well before the user hits the bottom, or they see
          // a stall.
          onEndReachedThreshold={0.5}
          ListFooterComponent={
            query.isFetchingNextPage ? (
              <ActivityIndicator color={colors.gold} style={styles.footer} />
            ) : items.length > 0 && !query.hasNextPage ? (
              <Text style={styles.endOfList}>That's everyone matching your search</Text>
            ) : null
          }
        />
      )}

      <FilterSheet
        visible={sheetOpen}
        filters={filters}
        onClose={() => setSheetOpen(false)}
        onApply={(next) => {
          setFilters(next);
          setSheetOpen(false);
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
  },
  searchBox: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    minHeight: 44,
  },
  searchInput: {
    flex: 1,
    ...typography.body,
    color: colors.text,
    paddingVertical: spacing.sm,
  },
  filterButton: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterBadge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 17,
    height: 17,
    borderRadius: 9,
    backgroundColor: colors.gold,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  filterBadgeText: { fontSize: 10, fontWeight: '800', color: colors.bg },
  chipList: { flexGrow: 0, marginTop: spacing.md },
  chipRow: { paddingHorizontal: spacing.xl, gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipText: { ...typography.caption, color: colors.sub, fontWeight: '600' },
  chipTextActive: { color: colors.bg },
  resultCount: {
    ...typography.tiny,
    color: colors.sub,
    paddingHorizontal: spacing.xl,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  list: { paddingHorizontal: spacing.xl, paddingBottom: spacing.huge },
  footer: { marginVertical: spacing.xl },
  endOfList: {
    ...typography.tiny,
    color: colors.dim,
    textAlign: 'center',
    marginVertical: spacing.xxl,
  },
});
