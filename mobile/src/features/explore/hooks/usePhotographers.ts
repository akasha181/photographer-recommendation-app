/**
 * React Query hooks for photographer discovery.
 */

import {
  useInfiniteQuery,
  useQuery,
  type UseQueryOptions,
} from '@tanstack/react-query';

import { qk } from '../../../api/queryKeys';
import {
  catalogApi,
  photographersApi,
  recommendationsApi,
  type PhotographerFilters,
} from '../../../api/services/photographers.api';

/**
 * Paginated photographer list with infinite scroll.
 *
 * `getNextPageParam` returns undefined at the end, which is what tells
 * React Query to stop — returning the last page number instead makes the
 * list re-fetch the final page forever on every scroll to the bottom.
 */
export function usePhotographers(filters: PhotographerFilters = {}) {
  return useInfiniteQuery({
    queryKey: qk.photographers.list(filters),
    queryFn: ({ pageParam }) =>
      photographersApi.list({ ...filters, page: pageParam as number }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.hasNext ? lastPage.page + 1 : undefined,
    staleTime: 2 * 60_000,
  });
}

export function usePhotographerDetail(id: number | string | null) {
  return useQuery({
    queryKey: qk.photographers.detail(id ?? 0),
    queryFn: () => photographersApi.detail(id!),
    // Guard against the brief moment during navigation when the id is null.
    enabled: id !== null && id !== undefined,
    staleTime: 5 * 60_000,
  });
}

export function useFeaturedPhotographers() {
  return useQuery({
    queryKey: qk.photographers.featured,
    queryFn: () => photographersApi.featured(),
    staleTime: 10 * 60_000,
  });
}

export function useTrendingPhotographers(city?: string) {
  return useQuery({
    queryKey: qk.photographers.trending(city),
    queryFn: () => photographersApi.trending(city),
    staleTime: 10 * 60_000,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: qk.categories,
    queryFn: () => catalogApi.categories(),
    // Categories are the five fixed event types — they effectively never
    // change, so there is no reason to refetch them during a session.
    staleTime: Infinity,
  });
}

export function useFilterOptions() {
  return useQuery({
    queryKey: qk.photographers.filterOptions,
    queryFn: () => photographersApi.filterOptions(),
    staleTime: 30 * 60_000,
  });
}

export function useRecommendations(params: {
  category?: string;
  city?: string;
  max_price?: number;
  limit?: number;
} = {}) {
  return useQuery({
    queryKey: qk.recommendations.feed(params),
    queryFn: () => recommendationsApi.get(params),
    // Matches REC_CACHE_TTL_SECONDS on the server, so the client is not
    // asking for data the backend would only serve from its own cache anyway.
    staleTime: 30 * 60_000,
  });
}
