/**
 * Shop, wallet, profile and wishlist API.
 *
 * TWO THINGS THIS FILE NEVER SENDS
 * -------------------------------
 * 1. A price. `checkout()` posts an empty body — the server totals the cart
 *    itself. A client that could name its own total buys a Rs 12,000 preset
 *    pack for one rupee, and no amount of later validation is as reliable as
 *    simply never reading the number.
 * 2. A file path. Product bytes are fetched by redeeming a single-use ticket
 *    from `requestDownload()`, never from a URL in the product payload.
 */

import { api, unwrap, unwrapFull } from '../client';
import { ENDPOINTS } from '../config';
import type {
  BuyerProfile,
  Cart,
  DigitalProduct,
  DigitalProductDetail,
  DownloadTicket,
  Order,
  OrderItem,
  PhotographerSelfProfile,
  SellerProduct,
  SellerSummary,
  ShopFilterOptions,
  TopUpRequest,
  Wallet,
  WalletTransaction,
  Wishlist,
  WishlistCounts,
} from '../../types/models';

export interface ShopFilters {
  q?: string;
  product_type?: string;
  category?: string;
  license_type?: string;
  min_price?: number;
  max_price?: number;
  on_sale?: boolean;
  affordable?: boolean;
  ordering?: string;
  page?: number;
}

export interface ProductPage {
  items: DigitalProduct[];
  page: number;
  hasNext: boolean;
}

function clean(filters: object): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue;
    out[key] = String(value);
  }
  return out;
}

/** Unique per submit attempt — Hermes has no `crypto.randomUUID`. */
function idempotencyKey(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export const shopApi = {
  async list(filters: ShopFilters = {}): Promise<ProductPage> {
    const envelope = await unwrapFull<DigitalProduct[]>(
      api.get(ENDPOINTS.marketplace.products, { params: clean(filters) }),
    );
    return {
      items: envelope.data,
      page: envelope.meta?.pagination?.page ?? 1,
      hasNext: envelope.meta?.pagination?.has_next ?? false,
    };
  },

  detail(slug: string) {
    return unwrap<DigitalProductDetail>(api.get(ENDPOINTS.marketplace.product(slug)));
  },

  filterOptions() {
    return unwrap<ShopFilterOptions>(api.get(ENDPOINTS.marketplace.productFilters));
  },

  featured() {
    return unwrap<DigitalProduct[]>(api.get(ENDPOINTS.marketplace.featured));
  },

  bestsellers() {
    return unwrap<DigitalProduct[]>(api.get(ENDPOINTS.marketplace.bestsellers));
  },

  // ─── Cart ────────────────────────────────────────────────────────────────
  // Every mutation returns the whole cart, so the screen re-renders from one
  // authoritative payload instead of patching a local copy and hoping the two
  // agree about the total.
  cart() {
    return unwrap<Cart>(api.get(ENDPOINTS.marketplace.cart));
  },

  addToCart(productId: number) {
    return unwrap<Cart>(
      api.post(ENDPOINTS.marketplace.cartAdd, { product: productId }),
    );
  },

  removeFromCart(productId: number) {
    return unwrap<Cart>(api.post(ENDPOINTS.marketplace.cartRemove(productId), {}));
  },

  clearCart() {
    return unwrap<Cart>(api.post(ENDPOINTS.marketplace.cartClear, {}));
  },

  // ─── Orders ──────────────────────────────────────────────────────────────
  checkout(key = idempotencyKey('ord')) {
    return unwrap<Order>(
      api.post(
        ENDPOINTS.marketplace.checkout,
        {},
        { headers: { 'Idempotency-Key': key } },
      ),
    );
  },

  orders() {
    return unwrap<Order[]>(api.get(ENDPOINTS.marketplace.orders));
  },

  order(id: number) {
    return unwrap<Order>(api.get(ENDPOINTS.marketplace.order(id)));
  },

  purchases() {
    return unwrap<OrderItem[]>(api.get(ENDPOINTS.marketplace.purchases));
  },

  /**
   * Mint a single-use download link.
   *
   * The link is spent on redemption and expires in 15 minutes, so it must be
   * requested each time — caching one and reusing it returns 410.
   */
  requestDownload(itemId: number, fileId?: number) {
    return unwrap<DownloadTicket>(
      api.post(ENDPOINTS.marketplace.download(itemId), fileId ? { file: fileId } : {}),
    );
  },

  // ─── Seller (read-only) ──────────────────────────────────────────────────
  /** Includes unpublished drafts, so the payload carries the moderation flags. */
  sellerProducts() {
    return unwrap<SellerProduct[]>(api.get(ENDPOINTS.marketplace.sellerProducts));
  },

  sellerSummary() {
    return unwrap<SellerSummary>(api.get(ENDPOINTS.marketplace.sellerSummary));
  },
};

export const profileApi = {
  /**
   * The caller's role-specific profile.
   *
   * Account fields (name, phone, city, avatar) live at /auth/me/ and are owned
   * by the auth store — this is the buyer's preferences or the photographer's
   * public listing, and the two endpoints deliberately do not overlap.
   */
  me() {
    return unwrap<BuyerProfile | PhotographerSelfProfile>(
      api.get(ENDPOINTS.profiles.me),
    );
  },

  update(payload: Record<string, unknown>) {
    return unwrap<BuyerProfile | PhotographerSelfProfile>(
      api.patch(ENDPOINTS.profiles.update, payload),
    );
  },

  wallet() {
    return unwrap<Wallet>(api.get(ENDPOINTS.profiles.wallet));
  },

  transactions() {
    return unwrap<WalletTransaction[]>(api.get(ENDPOINTS.profiles.transactions));
  },

  topups() {
    return unwrap<TopUpRequest[]>(api.get(ENDPOINTS.profiles.topups));
  },

  /**
   * Submit a transfer receipt. Credits nothing — an admin verifies it first.
   *
   * multipart, because the receipt is an image. Axios must NOT be given an
   * explicit Content-Type here: the boundary is generated with the FormData
   * and setting the header by hand strips it, which makes the server see an
   * empty body.
   */
  requestTopUp(payload: {
    amount: string;
    method: string;
    transaction_reference: string;
    receipt: { uri: string; name: string; type: string };
  }) {
    const form = new FormData();
    form.append('amount', payload.amount);
    form.append('method', payload.method);
    form.append('transaction_reference', payload.transaction_reference);
    form.append('receipt_image', payload.receipt as unknown as Blob);

    return unwrap<TopUpRequest>(
      api.post(ENDPOINTS.profiles.requestTopup, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        transformRequest: (data) => data,
      }),
    );
  },
};

export const wishlistApi = {
  list() {
    return unwrap<Wishlist>(api.get(ENDPOINTS.wishlist.list));
  },

  /** One endpoint for the heart icon — returns the state it left behind. */
  toggle(target: { photographer?: number; product?: number }) {
    return unwrap<{ is_saved: boolean; counts: WishlistCounts }>(
      api.post(ENDPOINTS.wishlist.toggle, target),
    );
  },

  remove(itemId: number) {
    return api.delete(ENDPOINTS.wishlist.remove(itemId));
  },
};
