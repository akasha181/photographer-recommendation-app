/**
 * API endpoint configuration.
 *
 * WHY localhost DOES NOT WORK ON A PHONE
 * --------------------------------------
 * Expo Go runs on a physical device. `127.0.0.1` there means the phone
 * itself, not your Mac — so the app silently fails to reach Django. The LAN
 * IP of the development machine is required.
 *
 * Find it with:   ipconfig getifaddr en0        (macOS Wi-Fi)
 * Then set EXPO_PUBLIC_API_URL in mobile/.env, or edit DEV_LAN_IP below.
 *
 * The Android emulator is a special case: 10.0.2.2 is its alias for the
 * host machine's loopback.
 */

import { Platform } from 'react-native';
import Constants from 'expo-constants';

/** Set this to your Mac's LAN IP to test on a real phone. */
const DEV_LAN_IP = '192.168.1.100';

const PORT = 8000;

function resolveBaseUrl(): string {
  // 1. Explicit override always wins.
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv) return fromEnv;

  // 2. Expo tells us the host it served the bundle from — that is the dev
  //    machine, so it is almost always the right answer on a real device.
  const hostUri =
    Constants.expoConfig?.hostUri ?? Constants.expoGoConfig?.debuggerHost;
  if (hostUri) {
    const host = hostUri.split(':')[0];
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      return `http://${host}:${PORT}/api/v1`;
    }
  }

  // 3. Platform fallbacks.
  if (Platform.OS === 'android') return `http://10.0.2.2:${PORT}/api/v1`;
  if (Platform.OS === 'ios') return `http://127.0.0.1:${PORT}/api/v1`;
  return `http://${DEV_LAN_IP}:${PORT}/api/v1`;
}

export const API_BASE_URL = resolveBaseUrl();

export const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws').replace(
  '/api/v1',
  '',
);

export const ENDPOINTS = {
  auth: {
    register: '/auth/register/',
    login: '/auth/login/',
    refresh: '/auth/refresh/',
    logout: '/auth/logout/',
    me: '/auth/me/',
    verifyEmail: '/auth/verify-email/',
    resendOtp: '/auth/resend-otp/',
    changePassword: '/auth/change-password/',
    passwordReset: '/auth/password-reset/',
    passwordResetConfirm: '/auth/password-reset/confirm/',
    devices: '/auth/devices/',
    deleteAccount: '/auth/me/delete/',
  },
  catalog: {
    categories: '/catalog/categories/',
    services: '/catalog/services/',
  },
  photographers: {
    list: '/profiles/photographers/',
    detail: (id: number | string) => `/profiles/photographers/${id}/`,
    portfolio: (id: number | string) => `/portfolio/${id}/images/`,
    reviews: (id: number | string) => `/reviews/photographers/${id}/`,
  },
  availability: {
    /** Whole window: which dates are bookable and why not, if not. */
    calendar: (id: number | string) => `/availability/photographers/${id}/`,
    /** One date, plus the start times the form may offer for it. */
    day: (id: number | string) => `/availability/photographers/${id}/day/`,
    rules: (id: number | string) => `/availability/photographers/${id}/rules/`,
  },
  bookings: {
    list: '/bookings/',
    counts: '/bookings/counts/',
    upcoming: '/bookings/upcoming/',
    detail: (id: number | string) => `/bookings/${id}/`,
    accept: (id: number | string) => `/bookings/${id}/accept/`,
    reject: (id: number | string) => `/bookings/${id}/reject/`,
    cancel: (id: number | string) => `/bookings/${id}/cancel/`,
    complete: (id: number | string) => `/bookings/${id}/complete/`,
  },
  marketplace: {
    products: '/marketplace/products/',
    product: (slug: string) => `/marketplace/products/${slug}/`,
    productFilters: '/marketplace/products/filters/',
    featured: '/marketplace/products/featured/',
    bestsellers: '/marketplace/products/bestsellers/',
    cart: '/marketplace/cart/',
    cartAdd: '/marketplace/cart/add/',
    cartRemove: (productId: number) => `/marketplace/cart/remove/${productId}/`,
    cartClear: '/marketplace/cart/clear/',
    checkout: '/marketplace/orders/checkout/',
    orders: '/marketplace/orders/',
    order: (id: number | string) => `/marketplace/orders/${id}/`,
    purchases: '/marketplace/orders/purchases/',
    download: (itemId: number | string) => `/marketplace/orders/items/${itemId}/download/`,
    sellerProducts: '/marketplace/seller/products/',
    sellerSummary: '/marketplace/seller/products/summary/',
  },
  profiles: {
    me: '/profiles/me/',
    update: '/profiles/me/update/',
    wallet: '/profiles/me/wallet/',
    transactions: '/profiles/me/wallet/transactions/',
    topups: '/profiles/me/wallet/topups/',
    requestTopup: '/profiles/me/wallet/topups/request/',
  },
  reviews: {
    create: '/reviews/',
    reply: (id: number | string) => `/reviews/${id}/reply/`,
  },
  wishlist: {
    list: '/wishlist/',
    toggle: '/wishlist/toggle/',
    photographers: '/wishlist/photographers/',
    products: '/wishlist/products/',
    remove: (id: number) => `/wishlist/${id}/`,
  },
  chat: {
    conversations: '/chat/conversations/',
    messages: (id: number | string) => `/chat/conversations/${id}/messages/`,
  },
  notifications: {
    list: '/notifications/',
    markRead: '/notifications/mark-read/',
  },
  recommendations: '/recommendations/',
  search: '/profiles/photographers/search/',
} as const;

export const WS_ROUTES = {
  chat: (conversationId: number, token: string) =>
    `${WS_BASE_URL}/ws/chat/${conversationId}/?token=${token}`,
  notifications: (token: string) => `${WS_BASE_URL}/ws/notifications/?token=${token}`,
  presence: (token: string) => `${WS_BASE_URL}/ws/presence/?token=${token}`,
} as const;
