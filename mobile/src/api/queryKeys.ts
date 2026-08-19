/**
 * React Query key factory.
 *
 * Keys are built here rather than inline at call sites so that invalidation
 * is reliable. `queryClient.invalidateQueries({ queryKey: qk.photographers.all })`
 * clears every photographer query — list, detail, featured — because they all
 * share that prefix. Hand-written keys drift, and a typo produces a cache that
 * silently never invalidates.
 */

import type { PhotographerFilters } from './services/photographers.api';

export const qk = {
  auth: {
    me: ['auth', 'me'] as const,
  },

  categories: ['categories'] as const,

  photographers: {
    all: ['photographers'] as const,
    list: (filters: PhotographerFilters) => ['photographers', 'list', filters] as const,
    detail: (id: number | string) => ['photographers', 'detail', String(id)] as const,
    featured: ['photographers', 'featured'] as const,
    trending: (city?: string) => ['photographers', 'trending', city ?? 'all'] as const,
    filterOptions: ['photographers', 'filter-options'] as const,
  },

  recommendations: {
    all: ['recommendations'] as const,
    feed: (params: Record<string, unknown>) => ['recommendations', params] as const,
  },

  wishlist: ['wishlist'] as const,

  shop: {
    all: ['shop'] as const,
    list: (filters: object) => ['shop', 'list', filters] as const,
    detail: (slug: string) => ['shop', 'detail', slug] as const,
    filterOptions: ['shop', 'filter-options'] as const,
    featured: ['shop', 'featured'] as const,
    cart: ['shop', 'cart'] as const,
    orders: ['shop', 'orders'] as const,
    purchases: ['shop', 'purchases'] as const,
    sellerProducts: ['shop', 'seller', 'products'] as const,
    sellerSummary: ['shop', 'seller', 'summary'] as const,
  },

  /** The photographer's own listings, calendar and portfolio. */
  studio: {
    all: ['studio'] as const,
    services: ['studio', 'services'] as const,
    calendar: ['studio', 'calendar'] as const,
    portfolio: ['studio', 'portfolio'] as const,
    portfolioSummary: ['studio', 'portfolio', 'summary'] as const,
    albums: ['studio', 'albums'] as const,
    dashboard: (days: number, months: number) =>
      ['studio', 'dashboard', days, months] as const,
  },

  profile: {
    all: ['profile'] as const,
    me: ['profile', 'me'] as const,
    wallet: ['profile', 'wallet'] as const,
    transactions: ['profile', 'transactions'] as const,
    topups: ['profile', 'topups'] as const,
  },

  bookings: {
    all: ['bookings'] as const,
    list: (group?: string) => ['bookings', 'list', group ?? 'all'] as const,
    detail: (id: number | string) => ['bookings', 'detail', String(id)] as const,
    counts: ['bookings', 'counts'] as const,
    upcoming: ['bookings', 'upcoming'] as const,
  },

  reviews: {
    all: ['reviews'] as const,
    forPhotographer: (photographerId: number | string, sort: string, rating?: number) =>
      ['reviews', 'photographer', String(photographerId), sort, rating ?? 'all'] as const,
    summary: (photographerId: number | string) =>
      ['reviews', 'summary', String(photographerId)] as const,
    forProduct: (productId: number | string) =>
      ['reviews', 'product', String(productId)] as const,
    mine: ['reviews', 'mine'] as const,
    pending: ['reviews', 'pending'] as const,
    received: (unansweredOnly: boolean) =>
      ['reviews', 'received', unansweredOnly] as const,
  },

  notifications: {
    all: ['notifications'] as const,
    list: (category?: string, unreadOnly?: boolean) =>
      ['notifications', 'list', category ?? 'all', Boolean(unreadOnly)] as const,
    badges: ['notifications', 'badges'] as const,
    preferences: ['notifications', 'preferences'] as const,
    devices: ['notifications', 'devices'] as const,
  },

  chat: {
    all: ['chat'] as const,
    conversations: (archived: boolean) => ['chat', 'conversations', archived] as const,
    conversation: (id: number | string) => ['chat', 'conversation', String(id)] as const,
    messages: (id: number | string) => ['chat', 'messages', String(id)] as const,
    unread: ['chat', 'unread'] as const,
    contacts: (term: string) => ['chat', 'contacts', term] as const,
  },

  availability: {
    all: ['availability'] as const,
    calendar: (photographerId: number | string, days: number) =>
      ['availability', 'calendar', String(photographerId), days] as const,
    day: (photographerId: number | string, date: string, duration: number) =>
      ['availability', 'day', String(photographerId), date, duration] as const,
  },

  portfolio: {
    all: ['portfolio'] as const,
    albums: (page: number) => ['portfolio', 'albums', page] as const,
    images: (albumId?: number, page: number = 1) =>
      ['portfolio', 'images', albumId ?? 'all', page] as const,
  },
} as const;
