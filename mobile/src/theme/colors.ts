/**
 * SnapSphere colour tokens.
 *
 * Lifted directly from the `C` object in the original prototype
 * (prototype/snapsphere-prototype.jsx) so the production app keeps the visual
 * identity that was already designed and reviewed — a near-black canvas with
 * a warm gold accent, which reads as "premium photography" rather than
 * "generic marketplace blue".
 *
 * RULE: no component may hard-code a hex value. Everything comes from here,
 * so a theme change is one file rather than a hundred.
 */

export const colors = {
  // ─── Surfaces (darkest → lightest) ─────────────────────────────────────
  bg: '#080A0E',
  surface: '#0F1116',
  card: '#161A22',
  cardHover: '#1C2130',
  border: '#232836',
  borderMid: '#2E3548',

  // ─── Brand ─────────────────────────────────────────────────────────────
  gold: '#D4A843',
  goldLight: '#EFC96A',
  goldDim: '#7A6128',

  // ─── Text ──────────────────────────────────────────────────────────────
  text: '#EEE9E0',
  sub: '#9A95A0',
  dim: '#4E4A55',

  // ─── Semantic ──────────────────────────────────────────────────────────
  blue: '#4A8FD4',
  blueDim: '#1E3A58',
  green: '#3DB87A',
  greenDim: '#1A3D2E',
  red: '#E05A5A',
  redDim: '#3D1A1A',
  amber: '#E0973A',
  amberDim: '#3D2A10',

  // ─── Utility ───────────────────────────────────────────────────────────
  transparent: 'transparent',
  overlay: 'rgba(8, 10, 14, 0.85)',
  white: '#FFFFFF',
  black: '#000000',
} as const;

/**
 * Booking status → colour.
 *
 * Centralised because the same status appears on at least five screens
 * (list, detail, notification, dashboard, history) and they must never
 * disagree about what "PENDING" looks like.
 */
export const statusColors = {
  PENDING: { fg: colors.amber, bg: colors.amberDim },
  ACCEPTED: { fg: colors.green, bg: colors.greenDim },
  COMPLETED: { fg: colors.blue, bg: colors.blueDim },
  REJECTED: { fg: colors.red, bg: colors.redDim },
  CANCELLED: { fg: colors.red, bg: colors.redDim },
  EXPIRED: { fg: colors.dim, bg: colors.border },
} as const;

export type BookingStatus = keyof typeof statusColors;
