/**
 * HTTP client.
 *
 * THE HARD PART THIS FILE SOLVES: CONCURRENT TOKEN REFRESH
 * --------------------------------------------------------
 * Access tokens live 30 minutes. When one expires, a screen that fires five
 * parallel requests gets five 401s at once. The naive interceptor refreshes
 * five times — four of which use an already-rotated (and therefore
 * blacklisted) refresh token, and the backend's reuse-detection revokes the
 * whole token family and logs the user out.
 *
 * The fix below is a single-flight queue: the first 401 starts one refresh,
 * every other 401 waits on that same promise, and all of them retry once it
 * resolves. One refresh, one rotation, no spurious logout.
 */

import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
} from 'axios';
import * as SecureStore from 'expo-secure-store';

import { API_BASE_URL } from './config';

const ACCESS_TOKEN_KEY = 'snapsphere.access';
const REFRESH_TOKEN_KEY = 'snapsphere.refresh';

/** Backend envelope — every response has this shape. See docs/01 §6.1. */
export interface ApiEnvelope<T> {
  success: boolean;
  message: string;
  data: T;
  meta?: {
    request_id?: string;
    pagination?: {
      page: number;
      page_size: number;
      total_pages: number;
      total_items: number;
      has_next: boolean;
      has_previous: boolean;
    };
  };
}

export interface ApiErrorShape {
  success: false;
  message: string;
  error: { code: string; details: Record<string, string[] | string> };
  meta?: { request_id?: string };
}

/** Thrown for every non-2xx response so callers handle one error type. */
export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
    public details: Record<string, string[] | string> = {},
    public requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** Field errors, flattened for react-hook-form's setError. */
  get fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [field, value] of Object.entries(this.details)) {
      if (field === 'detail') continue;
      out[field] = Array.isArray(value) ? value[0] : String(value);
    }
    return out;
  }

  get isAuthError(): boolean {
    return ['TOKEN_EXPIRED', 'TOKEN_INVALID', 'AUTHENTICATION_FAILED'].includes(
      this.code,
    );
  }
}

// ─── Token storage (Keychain / Keystore, never AsyncStorage) ────────────────
export const tokenStorage = {
  async getAccess() {
    return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
  },
  async getRefresh() {
    return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
  },
  async set(access: string, refresh: string) {
    await Promise.all([
      SecureStore.setItemAsync(ACCESS_TOKEN_KEY, access),
      SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refresh),
    ]);
  },
  async clear() {
    await Promise.all([
      SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
      SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
    ]);
  },
};

// ─── Single-flight refresh state ────────────────────────────────────────────
let refreshPromise: Promise<string> | null = null;

/** Called when refresh fails — wired to the auth store in App.tsx. */
let onSessionExpired: () => void = () => {};
export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler;
}

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Request: attach the bearer token ───────────────────────────────────────
api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const token = await tokenStorage.getAccess();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ─── Response: unwrap the envelope, refresh on 401 ──────────────────────────
api.interceptors.response.use(
  (response) => response,

  async (error: AxiosError<ApiErrorShape>) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retried?: boolean;
    };
    const status = error.response?.status;
    const payload = error.response?.data;
    const code = payload?.error?.code ?? 'NETWORK_ERROR';

    // Network failure — no response at all.
    if (!error.response) {
      throw new ApiError(
        'No internet connection. Please check your network and try again.',
        'NETWORK_ERROR',
        0,
      );
    }

    const shouldRefresh =
      status === 401 &&
      code === 'TOKEN_EXPIRED' &&
      !original?._retried &&
      !original?.url?.includes('/auth/refresh/') &&
      !original?.url?.includes('/auth/login/');

    if (shouldRefresh) {
      original._retried = true;
      try {
        const newAccess = await refreshAccessToken();
        if (original.headers) {
          original.headers.Authorization = `Bearer ${newAccess}`;
        }
        return api(original);
      } catch {
        await tokenStorage.clear();
        onSessionExpired();
        throw new ApiError(
          'Your session has expired. Please log in again.',
          'TOKEN_INVALID',
          401,
        );
      }
    }

    // TOKEN_INVALID means the token was blacklisted or the user was blocked —
    // refreshing cannot help, so log out immediately.
    if (status === 401 && code === 'TOKEN_INVALID') {
      await tokenStorage.clear();
      onSessionExpired();
    }

    throw new ApiError(
      payload?.message ?? 'Something went wrong.',
      code,
      status ?? 0,
      payload?.error?.details ?? {},
      payload?.meta?.request_id,
    );
  },
);

/**
 * Refresh the access token — at most one in flight at any moment.
 *
 * Every concurrent caller awaits the same promise, so the rotating refresh
 * token is spent exactly once.
 */
async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refresh = await tokenStorage.getRefresh();
    if (!refresh) throw new Error('No refresh token stored');

    // Bare axios, not `api` — using the instance would re-enter this
    // interceptor and recurse forever on a failing refresh.
    const { data } = await axios.post<ApiEnvelope<{ access: string; refresh?: string }>>(
      `${API_BASE_URL}/auth/refresh/`,
      { refresh },
      { headers: { 'Content-Type': 'application/json' }, timeout: 15_000 },
    );

    const access = data.data.access;
    // ROTATE_REFRESH_TOKENS is on, so the server returns a new refresh token
    // and blacklists the old one. Storing it is mandatory.
    await tokenStorage.set(access, data.data.refresh ?? refresh);
    return access;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

/** Unwrap `data` from the envelope so callers get the payload directly. */
export async function unwrap<T>(promise: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const response = await promise;
  return response.data.data;
}

/** Keep the envelope when pagination metadata is needed. */
export async function unwrapFull<T>(
  promise: Promise<{ data: ApiEnvelope<T> }>,
): Promise<ApiEnvelope<T>> {
  const response = await promise;
  return response.data;
}
