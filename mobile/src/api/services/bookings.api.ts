/**
 * Booking and availability API.
 *
 * THE IDEMPOTENCY KEY IS NOT OPTIONAL HERE
 * ----------------------------------------
 * On a patchy mobile connection a POST can succeed on the server and still
 * time out on the phone. Axios retries or the user taps again, and without a
 * key the buyer ends up with two requests to the same photographer — and the
 * second one fails with "that slot is already booked", naming their own
 * booking. `create()` generates a key per attempt so the server can recognise
 * the retry and hand back the booking it already made.
 */

import { api, unwrap, unwrapFull } from '../client';
import { ENDPOINTS } from '../config';
import type {
  AvailabilityCalendar,
  AvailabilityDayDetail,
  BookingCounts,
  BookingDetail,
  BookingGroup,
  BookingSummary,
} from '../../types/models';

export interface CreateBookingPayload {
  service: number;
  package?: number | null;
  event_date: string;
  start_time: string;
  duration_hours?: number;
  location_address: string;
  location_city: string;
  location_latitude?: string | null;
  location_longitude?: string | null;
  guest_count?: number | null;
  notes?: string;
  special_requirements?: string;
}

export interface BookingPage {
  items: BookingSummary[];
  page: number;
  totalPages: number;
  hasNext: boolean;
}

/**
 * A unique key per submit attempt.
 *
 * `crypto.randomUUID` is not available in the Hermes runtime, so this builds
 * one from the clock plus randomness — collision-safe enough for a value
 * scoped to one user for 24 hours.
 */
function idempotencyKey(): string {
  return `bk-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export const bookingsApi = {
  async list(group?: BookingGroup, page = 1): Promise<BookingPage> {
    const envelope = await unwrapFull<BookingSummary[]>(
      api.get(ENDPOINTS.bookings.list, { params: { group, page } }),
    );
    const pagination = envelope.meta?.pagination;
    return {
      items: envelope.data,
      page: pagination?.page ?? 1,
      totalPages: pagination?.total_pages ?? 1,
      hasNext: pagination?.has_next ?? false,
    };
  },

  detail(id: number | string) {
    return unwrap<BookingDetail>(api.get(ENDPOINTS.bookings.detail(id)));
  },

  counts() {
    return unwrap<BookingCounts>(api.get(ENDPOINTS.bookings.counts));
  },

  upcoming() {
    return unwrap<BookingSummary[]>(api.get(ENDPOINTS.bookings.upcoming));
  },

  create(payload: CreateBookingPayload, key = idempotencyKey()) {
    return unwrap<BookingDetail>(
      api.post(ENDPOINTS.bookings.list, payload, {
        headers: { 'Idempotency-Key': key },
      }),
    );
  },

  // ─── Transitions ─────────────────────────────────────────────────────────
  // Each returns the whole booking, so the screen re-renders from one
  // authoritative payload — including the refreshed `available_actions` —
  // instead of patching its local copy and hoping the two agree.
  accept(id: number | string, note = '') {
    return unwrap<BookingDetail>(api.post(ENDPOINTS.bookings.accept(id), { note }));
  },

  reject(id: number | string, reason: string) {
    return unwrap<BookingDetail>(api.post(ENDPOINTS.bookings.reject(id), { reason }));
  },

  cancel(id: number | string, reason?: string, note = '') {
    return unwrap<BookingDetail>(
      api.post(ENDPOINTS.bookings.cancel(id), { reason, note }),
    );
  },

  complete(id: number | string, note = '') {
    return unwrap<BookingDetail>(api.post(ENDPOINTS.bookings.complete(id), { note }));
  },
};

export const availabilityApi = {
  /** Which dates are bookable in the next `days`, and why not, if not. */
  calendar(photographerId: number | string, days = 60) {
    return unwrap<AvailabilityCalendar>(
      api.get(ENDPOINTS.availability.calendar(photographerId), { params: { days } }),
    );
  },

  /** One date, plus the start times that still fit a shoot of this length. */
  day(photographerId: number | string, date: string, durationHours = 4) {
    return unwrap<AvailabilityDayDetail>(
      api.get(ENDPOINTS.availability.day(photographerId), {
        params: { date, duration_hours: durationHours },
      }),
    );
  },
};
