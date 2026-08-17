/**
 * React Query hooks for reviews — Module 9.
 *
 * WHAT POSTING A REVIEW INVALIDATES
 * ---------------------------------
 * Five things the user can see at once change: the pending prompt (that shoot
 * is done), their own review list, the photographer's public list and summary,
 * the photographer's card everywhere (`avg_rating` moved), and the booking
 * itself (`is_reviewable` is now false, and `available_actions` no longer
 * offers "review"). Invalidating only the review list leaves a "Leave a review"
 * button on a booking that will refuse it.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { qk } from '../../../api/queryKeys';
import {
  reviewsApi,
  type CreateReviewPayload,
} from '../../../api/services/reviews.api';
import type { FlagReason, ReviewSort } from '../../../types/models';

// ═══════════════════════════════════════════════════════════════════════════
// PUBLIC READS
// ═══════════════════════════════════════════════════════════════════════════
export function usePhotographerReviews(
  photographerId: number | string | null,
  options: { sort?: ReviewSort; rating?: number; photos?: boolean } = {},
) {
  const sort = options.sort ?? 'recent';
  return useQuery({
    queryKey: qk.reviews.forPhotographer(photographerId ?? '', sort, options.rating),
    queryFn: () => reviewsApi.forPhotographer(photographerId!, { ...options, sort }),
    enabled: Boolean(photographerId),
    staleTime: 2 * 60_000,
  });
}

export function useReviewSummary(photographerId: number | string | null) {
  return useQuery({
    queryKey: qk.reviews.summary(photographerId ?? ''),
    queryFn: () => reviewsApi.summary(photographerId!),
    enabled: Boolean(photographerId),
    staleTime: 5 * 60_000,
  });
}

export function useProductReviews(productId: number | string | null) {
  return useQuery({
    queryKey: qk.reviews.forProduct(productId ?? ''),
    queryFn: () => reviewsApi.forProduct(productId!),
    enabled: Boolean(productId),
    staleTime: 5 * 60_000,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// BUYER
// ═══════════════════════════════════════════════════════════════════════════
export function usePendingReviews() {
  return useQuery({
    queryKey: qk.reviews.pending,
    queryFn: () => reviewsApi.pending(),
    staleTime: 60_000,
  });
}

export function useMyReviews() {
  return useQuery({
    queryKey: qk.reviews.mine,
    queryFn: () => reviewsApi.mine(),
    staleTime: 60_000,
  });
}

/** Everything a new or edited review makes stale. See the module docstring. */
function useReviewInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: qk.reviews.all });
    queryClient.invalidateQueries({ queryKey: qk.bookings.all });
    queryClient.invalidateQueries({ queryKey: qk.photographers.all });
    queryClient.invalidateQueries({ queryKey: qk.shop.all });
  };
}

export function useCreateReview() {
  const invalidate = useReviewInvalidation();
  return useMutation({
    mutationFn: (payload: CreateReviewPayload) => reviewsApi.create(payload),
    onSuccess: invalidate,
    // No retry: a review is not idempotent and the server would refuse the
    // second attempt citing the buyer's own review, which reads as a bug.
    retry: false,
  });
}

export function useUpdateReview() {
  const invalidate = useReviewInvalidation();
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: number } & Partial<CreateReviewPayload>) =>
      reviewsApi.update(id, payload),
    onSuccess: invalidate,
    retry: false,
  });
}

export function useDeleteReview() {
  const invalidate = useReviewInvalidation();
  return useMutation({
    mutationFn: (id: number) => reviewsApi.remove(id),
    onSuccess: invalidate,
    retry: false,
  });
}

export function useCreateProductReview() {
  const invalidate = useReviewInvalidation();
  return useMutation({
    mutationFn: (payload: {
      order_item: number;
      rating: number;
      title?: string;
      comment?: string;
    }) => reviewsApi.createProductReview(payload),
    onSuccess: invalidate,
    retry: false,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// ENGAGEMENT
// ═══════════════════════════════════════════════════════════════════════════
export function useToggleHelpful() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => reviewsApi.toggleHelpful(id),
    // The response carries the state the server left behind, so the list is
    // refetched rather than patched — one authoritative answer beats two
    // half-updated caches.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.reviews.all }),
    retry: false,
  });
}

export function useFlagReview() {
  return useMutation({
    mutationFn: ({
      id,
      reason,
      detail,
    }: {
      id: number;
      reason: FlagReason;
      detail?: string;
    }) => reviewsApi.flag(id, reason, detail),
    retry: false,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// PHOTOGRAPHER
// ═══════════════════════════════════════════════════════════════════════════
export function useReceivedReviews(unansweredOnly = false) {
  return useQuery({
    queryKey: qk.reviews.received(unansweredOnly),
    queryFn: () => reviewsApi.received(unansweredOnly),
    staleTime: 60_000,
  });
}

export function useReplyToReview() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      comment,
      editing,
    }: {
      id: number;
      comment: string;
      editing?: boolean;
    }) => (editing ? reviewsApi.editReply(id, comment) : reviewsApi.reply(id, comment)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.reviews.all }),
    retry: false,
  });
}
