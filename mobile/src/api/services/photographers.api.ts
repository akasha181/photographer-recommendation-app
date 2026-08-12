/**
 * Photographer discovery API.
 *
 * Every function returns plain data. React Query owns caching, retries and
 * background refetching — see hooks/usePhotographers.ts. Keeping the two
 * separate means these functions stay trivially testable.
 */

import { api, unwrap, unwrapFull, type ApiEnvelope } from '../client';
import { ENDPOINTS } from '../config';
import type {
  Category,
  PhotographerDetail,
  PhotographerSummary,
  Recommendation,
} from '../../types/models';

export interface PhotographerFilters {
  q?: string;
  category?: string;
  city?: string;
  min_price?: number;
  max_price?: number;
  min_rating?: number;
  min_experience?: number;
  available?: boolean;
  verified?: boolean;
  available_on?: string;
  ordering?: string;
  lat?: number;
  lng?: number;
  radius_km?: number;
  page?: number;
  page_size?: number;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  totalPages: number;
  totalItems: number;
  hasNext: boolean;
}

/** Strip undefined/empty values so they never reach the querystring. */
function clean(filters: PhotographerFilters): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue;
    out[key] = String(value);
  }
  return out;
}

export const photographersApi = {
  async list(filters: PhotographerFilters = {}): Promise<Paginated<PhotographerSummary>> {
    const envelope = await unwrapFull<PhotographerSummary[]>(
      api.get(ENDPOINTS.photographers.list, { params: clean(filters) }),
    );
    const pagination = envelope.meta?.pagination;
    return {
      items: envelope.data,
      page: pagination?.page ?? 1,
      totalPages: pagination?.total_pages ?? 1,
      totalItems: pagination?.total_items ?? envelope.data.length,
      hasNext: pagination?.has_next ?? false,
    };
  },

  detail(id: number | string) {
    return unwrap<PhotographerDetail>(api.get(ENDPOINTS.photographers.detail(id)));
  },

  featured() {
    return unwrap<PhotographerSummary[]>(
      api.get(`${ENDPOINTS.photographers.list}featured/`),
    );
  },

  trending(city?: string) {
    return unwrap<PhotographerSummary[]>(
      api.get(`${ENDPOINTS.photographers.list}trending/`, {
        params: city ? { city } : undefined,
      }),
    );
  },

  /** Real cities and the true price range, for the filter sheet. */
  filterOptions() {
    return unwrap<{
      categories: { slug: string; name: string; count: number }[];
      cities: { name: string; count: number }[];
      price_range: { min: number; max: number };
      sort_options: { value: string; label: string }[];
    }>(api.get(`${ENDPOINTS.photographers.list}filters/`));
  },
};

export const catalogApi = {
  categories() {
    return unwrap<Category[]>(api.get(ENDPOINTS.catalog.categories));
  },
};

export interface RecommendationResult {
  items: Recommendation[];
  strategy: string;
  personalised: boolean;
  modelMode: string;
  /** Non-null when the filters matched nobody and were widened. */
  relaxed: string | null;
}

export const recommendationsApi = {
  async get(params: {
    category?: string;
    city?: string;
    max_price?: number;
    limit?: number;
  } = {}): Promise<RecommendationResult> {
    const response = await api.get<
      ApiEnvelope<Recommendation[]> & {
        meta?: {
          strategy?: string;
          personalised?: boolean;
          model_mode?: string;
          relaxed?: string | null;
        };
      }
    >(ENDPOINTS.recommendations, { params: clean(params as PhotographerFilters) });

    const envelope = response.data;
    return {
      items: envelope.data,
      strategy: envelope.meta?.strategy ?? 'POPULARITY',
      personalised: envelope.meta?.personalised ?? false,
      modelMode: envelope.meta?.model_mode ?? 'none',
      relaxed: envelope.meta?.relaxed ?? null,
    };
  },

  /**
   * Report that a recommendation was tapped.
   *
   * Fire-and-forget: this is analytics, and a failure here must never block
   * the navigation the user actually asked for.
   */
  click(photographerId: number) {
    return api
      .post(`${ENDPOINTS.recommendations}click/`, { photographer_id: photographerId })
      .catch(() => undefined);
  },
};
