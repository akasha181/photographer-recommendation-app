/**
 * Reviews API — Module 9.
 *
 * WHY A REVIEW WITH PHOTOS IS SENT AS MULTIPART
 * --------------------------------------------
 * Photos are the strongest trust signal on a profile, and `expo-image-picker`
 * hands back a local `file://` URI. That cannot go inside JSON, so a review
 * that carries images is posted as `multipart/form-data` and one without stays
 * JSON — sending every review as multipart would mean the common case pays for
 * the rare one, and Django parses the two differently enough that sub-ratings
 * arrive as strings.
 */

import { api, unwrap, unwrapFull } from '../client';
import { ENDPOINTS } from '../config';
import type {
  OwnedReview,
  PendingReviews,
  ProductReview,
  Review,
  ReviewSort,
  ReviewSummary,
  FlagReason,
} from '../../types/models';

export interface SubRatingInput {
  rating_quality?: number | null;
  rating_professionalism?: number | null;
  rating_communication?: number | null;
  rating_value?: number | null;
  rating_punctuality?: number | null;
}

export interface CreateReviewPayload extends SubRatingInput {
  booking: number;
  rating: number;
  title?: string;
  comment?: string;
  /** Local URIs from the image picker. */
  images?: { uri: string; name?: string; type?: string }[];
}

export interface ReviewPage {
  items: Review[];
  page: number;
  totalPages: number;
  hasNext: boolean;
}

function toFormData(payload: CreateReviewPayload): FormData {
  const form = new FormData();
  form.append('booking', String(payload.booking));
  form.append('rating', String(payload.rating));
  if (payload.title) form.append('title', payload.title);
  if (payload.comment) form.append('comment', payload.comment);

  for (const [key, value] of Object.entries(payload)) {
    if (key.startsWith('rating_') && value != null) {
      form.append(key, String(value));
    }
  }

  (payload.images ?? []).forEach((image, index) => {
    // React Native's FormData wants this exact triple; the cast is unavoidable
    // because the DOM's File type is not what Hermes sends.
    form.append('images', {
      uri: image.uri,
      name: image.name ?? `review-${index}.jpg`,
      type: image.type ?? 'image/jpeg',
    } as unknown as Blob);
  });
  return form;
}

export const reviewsApi = {
  // ─── Public reads ────────────────────────────────────────────────────────
  async forPhotographer(
    photographerId: number | string,
    options: { sort?: ReviewSort; rating?: number; photos?: boolean; page?: number } = {},
  ): Promise<ReviewPage> {
    const envelope = await unwrapFull<Review[]>(
      api.get(ENDPOINTS.reviews.forPhotographer(photographerId), {
        params: {
          sort: options.sort ?? 'recent',
          rating: options.rating,
          photos: options.photos ? 1 : undefined,
          page: options.page ?? 1,
        },
      }),
    );
    const pagination = envelope.meta?.pagination;
    return {
      items: envelope.data,
      page: pagination?.page ?? 1,
      totalPages: pagination?.total_pages ?? 1,
      hasNext: pagination?.has_next ?? false,
    };
  },

  summary(photographerId: number | string) {
    return unwrap<ReviewSummary>(api.get(ENDPOINTS.reviews.summary(photographerId)));
  },

  forProduct(productId: number | string) {
    return unwrap<ProductReview[]>(api.get(ENDPOINTS.reviews.products(productId)));
  },

  // ─── Buyer writes ────────────────────────────────────────────────────────
  create(payload: CreateReviewPayload) {
    if (payload.images?.length) {
      return unwrap<Review>(
        api.post(ENDPOINTS.reviews.create, toFormData(payload), {
          headers: { 'Content-Type': 'multipart/form-data' },
        }),
      );
    }
    const { images, ...json } = payload;
    return unwrap<Review>(api.post(ENDPOINTS.reviews.create, json));
  },

  update(id: number, payload: Partial<CreateReviewPayload>) {
    return unwrap<Review>(api.patch(ENDPOINTS.reviews.detail(id), payload));
  },

  async remove(id: number): Promise<void> {
    await api.delete(ENDPOINTS.reviews.detail(id));
  },

  pending() {
    return unwrap<PendingReviews>(api.get(ENDPOINTS.reviews.pending));
  },

  mine() {
    return unwrap<Review[]>(api.get(ENDPOINTS.reviews.mine));
  },

  // ─── Engagement ──────────────────────────────────────────────────────────
  /** Returns the state it left behind, so a double-tap cannot desync the icon. */
  toggleHelpful(id: number) {
    return unwrap<{ marked_helpful: boolean; helpful_count: number }>(
      api.post(ENDPOINTS.reviews.helpful(id), {}),
    );
  },

  flag(id: number, reason: FlagReason, detail = '') {
    return unwrap<{ flag_id: number; status: string }>(
      api.post(ENDPOINTS.reviews.flag(id), { reason, detail }),
    );
  },

  // ─── Photographer side ───────────────────────────────────────────────────
  received(unansweredOnly = false) {
    return unwrap<OwnedReview[]>(
      api.get(ENDPOINTS.reviews.received, {
        params: { unanswered: unansweredOnly ? 1 : undefined },
      }),
    );
  },

  reply(id: number, comment: string) {
    return unwrap<OwnedReview>(api.post(ENDPOINTS.reviews.reply(id), { comment }));
  },

  editReply(id: number, comment: string) {
    return unwrap<OwnedReview>(api.patch(ENDPOINTS.reviews.reply(id), { comment }));
  },

  // ─── Product reviews ─────────────────────────────────────────────────────
  createProductReview(payload: {
    order_item: number;
    rating: number;
    title?: string;
    comment?: string;
  }) {
    return unwrap<ProductReview>(
      api.post(ENDPOINTS.reviews.createProductReview, payload),
    );
  },

  myProductReviews() {
    return unwrap<ProductReview[]>(api.get(ENDPOINTS.reviews.myProductReviews));
  },
};
