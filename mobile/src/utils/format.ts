/**
 * Display formatting.
 *
 * MONEY ARRIVES AS A STRING, ON PURPOSE
 * -------------------------------------
 * The backend serialises DECIMAL as a string ("85000.00"), because JavaScript
 * numbers are IEEE-754 doubles and cannot represent every decimal exactly.
 * These helpers accept the string and only convert to a number for display,
 * never for arithmetic on money.
 */

/** Rs 85,000 — the format used on every price in the app. */
export function formatPKR(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'Rs 0';
  const amount = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(amount)) return 'Rs 0';
  return `Rs ${Math.round(amount).toLocaleString('en-PK')}`;
}

/** Rs 85K / Rs 1.2L — compact form for dense cards. */
export function formatPKRShort(value: string | number | null | undefined): string {
  const amount = typeof value === 'string' ? parseFloat(value ?? '0') : (value ?? 0);
  if (Number.isNaN(amount) || amount === 0) return 'Rs 0';
  if (amount >= 100_000) return `Rs ${(amount / 100_000).toFixed(1)}L`;
  if (amount >= 1_000) return `Rs ${Math.round(amount / 1_000)}K`;
  return `Rs ${Math.round(amount)}`;
}

/** 4.9 — one decimal, the convention every rating in the app uses. */
export function formatRating(value: string | number | null | undefined): string {
  const rating = typeof value === 'string' ? parseFloat(value) : (value ?? 0);
  return Number.isNaN(rating) ? '0.0' : rating.toFixed(1);
}

/** 1.2k — review counts get long. */
export function formatCount(value: number | null | undefined): string {
  const n = value ?? 0;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** "3 days ago" — relative time for reviews and notifications. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';

  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';

  const units: [number, string][] = [
    [60, 'minute'],
    [3600, 'hour'],
    [86400, 'day'],
    [604800, 'week'],
    [2592000, 'month'],
    [31536000, 'year'],
  ];

  let value = seconds;
  let label = 'second';
  for (let i = units.length - 1; i >= 0; i -= 1) {
    const [divisor, name] = units[i];
    if (seconds >= divisor) {
      value = Math.floor(seconds / divisor);
      label = name;
      break;
    }
  }
  return `${value} ${label}${value === 1 ? '' : 's'} ago`;
}

/** "14 Aug 2026" — dates are shown in Asia/Karachi, matching the market. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Karachi',
  });
}

/** "ZM" — initials for the avatar placeholder. */
export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Deterministic accent colour derived from a name.
 *
 * Photographers without an uploaded avatar still get a stable, distinct
 * colour rather than a wall of identical grey circles — and it stays the same
 * across sessions because it is derived, not random.
 */
const AVATAR_COLORS = [
  '#8B4E2A', '#2A5E8B', '#2A8B5E', '#5E2A8B',
  '#8B2A5E', '#5E7A2A', '#8B6B2A', '#2A6B8B',
];

export function avatarColor(name: string | null | undefined): string {
  if (!name) return AVATAR_COLORS[0];
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash << 5) - hash + name.charCodeAt(i);
    hash |= 0;
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

/** "2.4 km away" */
export function formatDistance(km: number | null | undefined): string | null {
  if (km === null || km === undefined) return null;
  if (km < 1) return `${Math.round(km * 1000)} m away`;
  return `${km.toFixed(1)} km away`;
}
