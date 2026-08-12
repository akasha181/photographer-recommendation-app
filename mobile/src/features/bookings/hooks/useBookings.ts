/**
 * React Query hooks for bookings.
 *
 * WHAT EVERY MUTATION INVALIDATES, AND WHY
 * ----------------------------------------
 * A status change touches four things a user can see at once: the booking
 * itself, the list it appears in, the tab badge counts, and — because an
 * accepted booking consumes a calendar slot — that photographer's
 * availability. Invalidating only the detail query leaves the Bookings tab
 * showing a request as "Pending" after the photographer accepted it, which
 * looks like the app lost the update.
 *
 * `qk.bookings.all` is the shared prefix, so one invalidation clears list,
 * detail, counts and upcoming together.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { qk } from '../../../api/queryKeys';
import {
  availabilityApi,
  bookingsApi,
  type CreateBookingPayload,
} from '../../../api/services/bookings.api';
import type { BookingGroup } from '../../../types/models';

// ═══════════════════════════════════════════════════════════════════════════
// READ
// ═══════════════════════════════════════════════════════════════════════════
export function useBookings(group?: BookingGroup) {
  return useInfiniteQuery({
    queryKey: qk.bookings.list(group),
    queryFn: ({ pageParam }) => bookingsApi.list(group, pageParam as number),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.hasNext ? last.page + 1 : undefined),
    // Bookings change when the other party acts, which the user cannot see
    // happening. A short stale time keeps the list close to the truth without
    // refetching on every render.
    staleTime: 30_000,
  });
}

export function useBookingDetail(id: number | string | null) {
  return useQuery({
    queryKey: qk.bookings.detail(id ?? 0),
    queryFn: () => bookingsApi.detail(id!),
    enabled: id !== null && id !== undefined,
    staleTime: 15_000,
  });
}

export function useBookingCounts() {
  return useQuery({
    queryKey: qk.bookings.counts,
    queryFn: () => bookingsApi.counts(),
    staleTime: 30_000,
  });
}

export function useUpcomingBookings() {
  return useQuery({
    queryKey: qk.bookings.upcoming,
    queryFn: () => bookingsApi.upcoming(),
    staleTime: 60_000,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// AVAILABILITY
// ═══════════════════════════════════════════════════════════════════════════
export function useAvailabilityCalendar(
  photographerId: number | string | null,
  days = 60,
) {
  return useQuery({
    queryKey: qk.availability.calendar(photographerId ?? 0, days),
    queryFn: () => availabilityApi.calendar(photographerId!, days),
    enabled: photographerId !== null && photographerId !== undefined,
    staleTime: 60_000,
  });
}

export function useAvailableTimes(
  photographerId: number | string | null,
  date: string | null,
  durationHours = 4,
) {
  return useQuery({
    queryKey: qk.availability.day(photographerId ?? 0, date ?? '', durationHours),
    queryFn: () => availabilityApi.day(photographerId!, date!, durationHours),
    enabled: Boolean(photographerId) && Boolean(date),
    staleTime: 60_000,
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// WRITE
// ═══════════════════════════════════════════════════════════════════════════
function useBookingInvalidator() {
  const queryClient = useQueryClient();
  return (photographerId?: number) => {
    queryClient.invalidateQueries({ queryKey: qk.bookings.all });
    queryClient.invalidateQueries({ queryKey: qk.availability.all });
    if (photographerId) {
      queryClient.invalidateQueries({
        queryKey: qk.photographers.detail(photographerId),
      });
    }
  };
}

export function useCreateBooking() {
  const invalidate = useBookingInvalidator();
  return useMutation({
    mutationFn: (payload: CreateBookingPayload) => bookingsApi.create(payload),
    onSuccess: (booking) => invalidate(booking.photographer.id),
    // Deliberately no retry: a booking is not safe to replay automatically.
    // The Idempotency-Key makes a *user-initiated* retry safe, which is the
    // right place for that decision.
    retry: false,
  });
}

export function useAcceptBooking() {
  const invalidate = useBookingInvalidator();
  return useMutation({
    mutationFn: ({ id, note }: { id: number; note?: string }) =>
      bookingsApi.accept(id, note),
    onSuccess: (booking) => invalidate(booking.photographer.id),
    retry: false,
  });
}

export function useRejectBooking() {
  const invalidate = useBookingInvalidator();
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      bookingsApi.reject(id, reason),
    onSuccess: (booking) => invalidate(booking.photographer.id),
    retry: false,
  });
}

export function useCancelBooking() {
  const invalidate = useBookingInvalidator();
  return useMutation({
    mutationFn: ({ id, reason, note }: { id: number; reason?: string; note?: string }) =>
      bookingsApi.cancel(id, reason, note),
    onSuccess: (booking) => invalidate(booking.photographer.id),
    retry: false,
  });
}

export function useCompleteBooking() {
  const invalidate = useBookingInvalidator();
  return useMutation({
    mutationFn: ({ id, note }: { id: number; note?: string }) =>
      bookingsApi.complete(id, note),
    onSuccess: (booking) => invalidate(booking.photographer.id),
    retry: false,
  });
}
