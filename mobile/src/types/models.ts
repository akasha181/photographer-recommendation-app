/**
 * Domain types mirroring the Django serializers.
 *
 * These are hand-written rather than generated, but they are kept in exact
 * sync with the OpenAPI schema at /api/v1/schema/. When an endpoint changes,
 * this file changes in the same commit — a mismatch here surfaces as a
 * runtime `undefined` deep inside a screen, which is the most expensive kind
 * of bug to track down.
 */

export type UserRole = 'BUYER' | 'PHOTOGRAPHER' | 'ADMIN';

export type BookingStatus =
  | 'PENDING'
  | 'ACCEPTED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'COMPLETED'
  | 'EXPIRED';

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone: string;
  role: UserRole;
  avatar_url: string | null;
  city: string;
  latitude: string | null;
  longitude: string | null;
  is_email_verified: boolean;
  is_phone_verified: boolean;
  is_approved: boolean;
  date_joined: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface AuthResponse {
  user: User;
  tokens: AuthTokens;
}

/**
 * The lean category shape embedded inside photographer payloads
 * (CategoryMiniSerializer). It deliberately omits counts and description —
 * a 20-row list would otherwise carry 20 copies of data no card renders.
 */
export interface CategoryMini {
  id: number;
  name: string;
  slug: string;
  icon: string;
}

/** The full shape from GET /catalog/categories/ (CategorySerializer). */
export interface Category extends CategoryMini {
  description: string;
  image_url: string | null;
  photographer_count: number;
  booking_count: number;
}

/**
 * Mirrors apps/profiles/serializers.py PhotographerListSerializer exactly.
 * When that serializer's `fields` tuple changes, this changes in the same
 * commit — a drift here surfaces as an undefined deep inside a screen.
 */
export interface PhotographerSummary {
  /** Profile id — what booking and portfolio endpoints take. */
  id: number;
  /** Account id — what chat takes. The two are different. */
  user_id: number;
  display_name: string;
  business_name: string;
  tagline: string;
  avatar_url: string | null;
  cover_image_url: string | null;
  city: string;
  /** Money is a string, not a number — Decimal precision must survive JSON. */
  base_price: string;
  avg_rating: string;
  bayesian_rating: string;
  reviews_count: number;
  years_experience: number;
  completed_bookings: number;
  is_verified: boolean;
  is_featured: boolean;
  is_accepting_bookings: boolean;
  categories: CategoryMini[];
  service_count: number;
  /** Only present when the request supplied lat/lng. */
  distance_km?: number | null;
  is_wishlisted?: boolean;
}

export interface PortfolioPreview {
  id: number;
  caption: string;
  is_featured: boolean;
  image_url: string | null;
  thumbnail_url: string | null;
}

/** The inline review shape returned by the photographer detail endpoint. */
export interface PhotographerReview {
  id: number;
  rating: number;
  title: string;
  comment: string;
  created_at: string;
  buyer_name: string;
  buyer_avatar: string | null;
  reply: { comment: string; created_at: string } | null;
  helpful_count: number;
}

/** Star histogram: keys "1".."5" → count. */
export type RatingBreakdown = Record<'1' | '2' | '3' | '4' | '5', number>;

/** Mirrors PhotographerDetailSerializer. */
export interface PhotographerDetail extends PhotographerSummary {
  bio: string;
  equipment: string;
  languages: string;
  travel_available: boolean;
  service_radius_km: number;
  website: string;
  instagram: string;
  facebook: string;
  success_rate: string;
  avg_response_time_hours: string;
  /** "Replies within an hour" — hours are engineering data, this is for users. */
  response_time_label: string;
  portfolio_score: number;
  profile_views: number;
  total_bookings: number;
  specializations: { id: number; name: string; slug: string }[];
  services: Service[];
  portfolio: PortfolioPreview[];
  recent_reviews: PhotographerReview[];
  rating_breakdown: RatingBreakdown;
}

/** Mirrors catalog ServiceSerializer. */
export interface Service {
  id: number;
  title: string;
  description: string;
  price: string;
  pricing_unit: 'FIXED' | 'PER_HOUR' | 'PER_DAY' | 'PER_EVENT';
  duration_hours: number;
  edited_photos_count: number;
  raw_photos_included: boolean;
  delivery_days: number;
  includes: string[];
  advance_payment_percent: number;
  category: CategoryMini;
  // The serializer sends a resolved URL, not the storage path. This said
  // `cover_image` until a type diff against the live API caught it — the
  // field was simply always undefined wherever it was read.
  cover_image_url: string | null;
  packages: ServicePackage[];
  booking_count: number;
}

export interface ServicePackage {
  id: number;
  name: string;
  price: string;
  description: string;
  features: string[];
  duration_hours: number;
  edited_photos_count: number;
  is_popular: boolean;
}

/**
 * The other side of a booking.
 *
 * Both parties ride on every row so one list endpoint serves the buyer's
 * Bookings tab and the photographer's Requests tab — each screen draws
 * whichever party it is not.
 */
export interface BookingParty {
  /** Profile id on the photographer side, account id on the buyer side. */
  id: number;
  /**
   * The ACCOUNT id, present on both sides.
   *
   * Chat addresses people by user id, and for a photographer that is NOT `id`
   * — that one is the profile. Opening a thread from a booking needs this.
   */
  user_id: number;
  name: string;
  avatar_url: string | null;
  city: string;
}

/** Mirrors BookingListSerializer — the card payload. */
export interface BookingSummary {
  id: number;
  uuid: string;
  /** "SNP-000042" — what a buyer quotes to support. */
  reference: string;
  status: BookingStatus;
  status_label: string;
  event_date: string;
  start_time: string;
  end_time: string | null;
  duration_hours: number;
  location_city: string;
  location_address: string;
  service_title: string;
  category_name: string;
  cover_image_url: string | null;
  /** Money is a string — Decimal precision must survive JSON. */
  total_price: string;
  photographer: BookingParty;
  buyer: BookingParty;
  days_until_event: number;
  is_reviewable: boolean;
  has_review: boolean;
  created_at: string;
}

/** One step of the append-only audit trail. */
export interface BookingTimelineEntry {
  id: number;
  from_status: BookingStatus | '';
  to_status: BookingStatus;
  label: string;
  actor_role: string;
  changed_by_name: string;
  note: string;
  created_at: string;
}

/**
 * What the caller may do to this booking right now.
 *
 * Computed server-side from the same state machine that enforces the rules,
 * so a button can never appear that the API would then reject.
 */
export type BookingAction = 'accept' | 'reject' | 'cancel' | 'complete' | 'review';

/** Mirrors BookingDetailSerializer. */
export interface BookingDetail extends BookingSummary {
  package: number | null;
  guest_count: number | null;
  notes: string;
  special_requirements: string;
  location_latitude: string | null;
  location_longitude: string | null;
  unit_price: string;
  quantity: number;
  travel_fee: string;
  discount: string;
  commission_percent: string;
  commission_amount: string;
  photographer_payout: string;
  price_breakdown: { label: string; amount: string }[];
  expires_at: string;
  responded_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  cancelled_at: string | null;
  completed_at: string | null;
  rejection_reason: string;
  cancellation_reason: string;
  cancellation_note: string;
  buyer_confirmed_completion: boolean;
  photographer_marked_complete: boolean;
  timeline: BookingTimelineEntry[];
  payment: BookingPayment | null;
  available_actions: BookingAction[];
  /** Released only once the booking is ACCEPTED — null before that. */
  contact: { buyer_phone: string; photographer_phone: string } | null;
}

export interface BookingPayment {
  method: string;
  status: 'UNPAID' | 'ADVANCE_PAID' | 'FULLY_PAID' | 'REFUNDED';
  advance_amount: string;
  paid_amount: string;
  outstanding: string;
  transaction_reference: string;
  is_verified: boolean;
  verified_at: string | null;
  note: string;
}

/** Badge counts for the status tabs. */
export interface BookingCounts {
  pending: number;
  upcoming: number;
  completed: number;
  cancelled: number;
  total: number;
}

/** The tabs the app shows, matching selectors.STATUS_GROUPS on the server. */
export type BookingGroup = 'pending' | 'upcoming' | 'completed' | 'cancelled';

/**
 * Why a date cannot be booked.
 *
 * The app branches on these to decide whether to suggest a different time or
 * a different photographer, so they are part of the API contract.
 */
export type UnavailableReason =
  | 'PAST'
  | 'TOO_SOON'
  | 'WEEKLY_OFF'
  | 'BLACKOUT'
  | 'FULLY_BOOKED'
  | 'NOT_ACCEPTING'
  | '';

export interface AvailabilityDay {
  date: string;
  is_available: boolean;
  reason: UnavailableReason;
  message: string;
  booked_times: string[];
  remaining_slots: number;
  start_time: string | null;
  end_time: string | null;
}

export interface AvailabilityCalendar {
  photographer_id: number;
  start_date: string;
  end_date: string;
  earliest_bookable_date: string;
  is_accepting_bookings: boolean;
  days: AvailabilityDay[];
}

export interface AvailabilityDayDetail extends AvailabilityDay {
  available_start_times: string[];
}

// ═══════════════════════════════════════════════════════════════════════════
// MODULE 9 — reviews & ratings
//
// These mirror `apps/reviews/serializers.py` field for field. The names here
// were checked against live responses rather than read off the serializer by
// eye — the last time that shortcut was taken, `Service.cover_image` silently
// read `undefined` everywhere because the API sends `cover_image_url`.
// ═══════════════════════════════════════════════════════════════════════════

export type SentimentLabel = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | '';

export interface ReviewImage {
  id: number;
  caption: string;
  image_url: string | null;
  thumbnail_url: string | null;
}

export interface ReviewReply {
  id: number;
  comment: string;
  is_edited: boolean;
  photographer_name: string;
  created_at: string;
  updated_at: string;
}

export interface SubRatings {
  quality: number | null;
  professionalism: number | null;
  communication: number | null;
  value: number | null;
  punctuality: number | null;
}

export interface Review {
  id: number;
  rating: number;
  title: string;
  comment: string;
  buyer_name: string;
  buyer_avatar: string | null;
  photographer_id: number;
  photographer_name: string;
  /** What was actually shot — a 5★ reads differently under a full-day wedding. */
  service_name: string;
  sub_ratings: SubRatings;
  images: ReviewImage[];
  reply: ReviewReply | null;
  helpful_count: number;
  /** Per-caller: whether *you* marked it helpful. */
  marked_helpful: boolean;
  /** Server-computed, like `available_actions` — the 24h window plus "no reply yet". */
  can_edit: boolean;
  is_hidden: boolean;
  hidden_reason: string;
  created_at: string;
}

/**
 * A review as the photographer who received it sees it.
 *
 * Adds the model's sentiment label, which is deliberately absent from the
 * public shape: a machine label on somebody else's words is not evidence.
 */
export interface OwnedReview extends Review {
  sentiment: SentimentLabel;
  sentiment_score: string | null;
}

export interface ReviewSummary {
  average_rating: number;
  total_reviews: number;
  with_comment: number;
  with_photos: number;
  recommend_percent: number;
  breakdown: RatingBreakdown;
  sub_ratings: SubRatings;
  sentiment: Record<'POSITIVE' | 'NEUTRAL' | 'NEGATIVE', number>;
}

export interface ProductReview {
  id: number;
  rating: number;
  title: string;
  comment: string;
  helpful_count: number;
  buyer_name: string;
  buyer_avatar: string | null;
  product_title: string;
  product_slug: string;
  created_at: string;
}

/** A completed shoot still awaiting its review. */
export interface PendingBookingReview {
  booking_id: number;
  photographer_id: number;
  photographer_name: string;
  photographer_avatar: string | null;
  service_name: string;
  event_date: string;
}

export interface PendingProductReview {
  order_item_id: number;
  product_title: string;
  product_slug: string;
  thumbnail_url: string | null;
  purchased_at: string;
}

export interface PendingReviews {
  bookings: PendingBookingReview[];
  order_items: PendingProductReview[];
}

export type FlagReason =
  | 'INAPPROPRIATE'
  | 'COPYRIGHT'
  | 'SPAM'
  | 'FAKE'
  | 'HARASSMENT'
  | 'OFF_PLATFORM'
  | 'OTHER';

export type ReviewSort = 'recent' | 'oldest' | 'helpful' | 'highest' | 'lowest';

/** Mirrors marketplace SellerMiniSerializer. */
export interface ProductSeller {
  id: number;
  display_name: string;
  avatar_url: string | null;
  is_verified: boolean;
}

/**
 * The manifest a buyer sees before paying — names and sizes only.
 *
 * There is deliberately no URL here. Product bytes live on private storage
 * and are reachable only by redeeming a single-use DownloadToken; a `url`
 * field would undo that on the server side.
 */
export interface ProductFile {
  id: number;
  name: string;
  file_size_mb: string;
  display_order: number;
}

/** Mirrors ProductListSerializer — the Shop grid card. */
export interface DigitalProduct {
  id: number;
  uuid: string;
  slug: string;
  title: string;
  product_type: string;
  type_label: string;
  license_type: 'PERSONAL' | 'COMMERCIAL' | 'EXTENDED';
  price: string;
  compare_at_price: string | null;
  discount_percent: number;
  thumbnail_url: string | null;
  file_count: number;
  total_size_mb: string;
  sales_count: number;
  avg_rating: string;
  reviews_count: number;
  seller: ProductSeller;
  category: CategoryMini | null;
  is_featured: boolean;
  /** Loaded once per request by the view, not per card. */
  is_owned: boolean;
  is_wishlisted: boolean;
  in_cart: boolean;
}

/** Mirrors ProductDetailSerializer. */
export interface DigitalProductDetail extends DigitalProduct {
  description: string;
  compatible_with: string[];
  tags: string[];
  preview_images: string[];
  preview_image_urls: string[];
  preview_video_url: string;
  files: ProductFile[];
  view_count: number;
  wishlist_count: number;
  published_at: string | null;
}

export interface CartLine {
  id: number;
  product: DigitalProduct;
  /** False when the product was delisted or is already owned. */
  is_available: boolean;
  is_owned: boolean;
  created_at: string;
}

export interface Cart {
  items: CartLine[];
  count: number;
  subtotal: string;
  total: string;
  unavailable_count: number;
  wallet_balance: string;
  can_checkout: boolean;
  /** How much more the buyer needs — what the top-up screen asks for. */
  shortfall: string;
}

export interface OrderItem {
  id: number;
  product: number;
  product_slug: string;
  product_title: string;
  thumbnail_url: string | null;
  seller_name: string;
  price: string;
  download_count: number;
  max_downloads: number;
  downloads_remaining: number;
  has_review: boolean;
  files: ProductFile[];
  created_at: string;
}

export interface Order {
  id: number;
  uuid: string;
  order_number: string;
  status: 'PENDING' | 'PAID' | 'FAILED' | 'REFUNDED' | 'CANCELLED';
  status_label: string;
  subtotal: string;
  discount: string;
  total: string;
  payment_method: string;
  paid_at: string | null;
  created_at: string;
  items: OrderItem[];
  item_count: number;
}

export interface DownloadTicket {
  download_url: string;
  expires_at: string;
  file_name: string;
  downloads_remaining: number;
}

export interface ShopFilterOptions {
  types: { value: string; label: string; count: number }[];
  price_range: { min: number; max: number };
  sort_options: { value: string; label: string }[];
}

/**
 * A seller's own listing — adds the moderation flags the public grid omits,
 * because this list includes unpublished drafts.
 */
export interface SellerProduct extends DigitalProduct {
  is_published: boolean;
  is_approved: boolean;
  published_at: string | null;
  view_count: number;
  wishlist_count: number;
  total_revenue: string;
}

export interface SellerSummary {
  products_total: number;
  products_live: number;
  sales_count: number;
  gross_revenue: string;
  net_earnings: string;
}

// ─── Wallet ─────────────────────────────────────────────────────────────────
export interface WalletTransaction {
  id: number;
  txn_type: 'TOPUP' | 'PURCHASE' | 'REFUND' | 'PAYOUT' | 'EARNING' | 'ADJUSTMENT';
  type_label: string;
  /** "in" or "out" — so the row is coloured without knowing what EARNING means. */
  direction: 'in' | 'out';
  amount: string;
  balance_before: string;
  balance_after: string;
  reference: string;
  description: string;
  created_at: string;
}

export interface Wallet {
  balance: string;
  total_credited: string;
  total_debited: string;
  recent_transactions: WalletTransaction[];
  pending_topups: number;
}

export interface TopUpRequest {
  id: number;
  amount: string;
  method: 'BANK' | 'EASYPAISA' | 'JAZZCASH';
  transaction_reference: string;
  receipt_url: string | null;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  status_label: string;
  admin_note: string;
  reviewed_at: string | null;
  created_at: string;
}

// ─── Profiles ───────────────────────────────────────────────────────────────
export interface BuyerProfile {
  id: number;
  full_name: string;
  email: string;
  city: string;
  preferred_categories: CategoryMini[];
  budget_min: string | null;
  budget_max: string | null;
  total_bookings: number;
  completed_bookings: number;
  cancelled_bookings: number;
  total_spent: string;
  reviews_written: number;
  wallet_balance: string;
}

/** The photographer's own profile — adds what only they may see. */
export interface PhotographerSelfProfile extends PhotographerDetail {
  is_approved: boolean;
  submitted_for_approval_at: string | null;
  rejection_reason: string;
  total_earnings: string;
  wallet_balance: string;
}

// ─── Wishlist ───────────────────────────────────────────────────────────────
export interface SavedPhotographer {
  id: number;
  photographer: PhotographerSummary;
  note: string;
  created_at: string;
}

export interface SavedProduct {
  id: number;
  product: DigitalProduct;
  note: string;
  created_at: string;
}

export interface WishlistCounts {
  photographers: number;
  products: number;
}

export interface Wishlist {
  photographers: SavedPhotographer[];
  products: SavedProduct[];
  counts: WishlistCounts;
}

export interface Recommendation extends PhotographerSummary {
  score: number;
  /** Human-readable justification — never show a bare score to a user. */
  reason: string;
  strategy: 'HYBRID' | 'CONTENT' | 'COLLABORATIVE' | 'POPULARITY' | 'EXPLORATION';
}

// ═══════════════════════════════════════════════════════════════════════════
// MODULE 12 — notifications
// ═══════════════════════════════════════════════════════════════════════════

/** The filter chips the bell offers. Derived server-side from the type prefix. */
export type NotificationCategory =
  | 'bookings'
  | 'messages'
  | 'reviews'
  | 'marketplace'
  | 'account'
  | 'platform';

export interface Notification {
  id: number;
  notification_type: string;
  category: NotificationCategory;
  title: string;
  body: string;
  image_url: string;
  /** Deep-link target, sent as data so the app never parses meaning out of text. */
  action_screen: string;
  action_id: string;
  payload: Record<string, unknown>;
  is_read: boolean;
  read_at: string | null;
  actor_name: string | null;
  actor_avatar: string | null;
  created_at: string;
}

export interface NotificationBadges {
  total: number;
  bookings: number;
  messages: number;
  reviews: number;
  marketplace: number;
}

export interface NotificationPreferences {
  push_enabled: boolean;
  email_enabled: boolean;
  sms_enabled: boolean;
  booking_updates: boolean;
  chat_messages: boolean;
  review_activity: boolean;
  marketplace_activity: boolean;
  promotions: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  updated_at: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// MODULE 13 — chat
// ═══════════════════════════════════════════════════════════════════════════

export interface ChatParticipant {
  id: number;
  full_name: string;
  role: UserRole;
  avatar_url: string | null;
  business_name: string | null;
  is_online: boolean;
  last_seen_at: string | null;
}

export interface ConversationBookingRef {
  id: number;
  status: BookingStatus;
  event_date: string;
  service_title: string;
}

export interface Conversation {
  id: number;
  other_participant: ChatParticipant | null;
  last_message_text: string;
  last_message_at: string | null;
  message_count: number;
  unread_count: number;
  is_muted: boolean;
  is_blocked: boolean;
  is_archived: boolean;
  booking: ConversationBookingRef | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  /** Where to draw the "unread from here" divider. */
  last_read_message_id: number;
}

export interface MessageAttachment {
  id: number;
  file_name: string;
  file_size_kb: number;
  mime_type: string;
  width: number;
  height: number;
  file_url: string | null;
  thumbnail_url: string | null;
}

export type MessageType = 'TEXT' | 'IMAGE' | 'FILE' | 'BOOKING_REF' | 'SYSTEM';

export interface Message {
  id: number;
  conversation: number;
  sender: number;
  sender_name: string;
  sender_avatar: string | null;
  /** Which side to draw the bubble on. Server-computed so the REST row and the
   *  WebSocket frame are the same shape. */
  is_mine: boolean;
  message_type: MessageType;
  body: string;
  client_id: string;
  is_edited: boolean;
  is_deleted: boolean;
  attachments: MessageAttachment[];
  delivered_at: string | null;
  read_at: string | null;
  created_at: string;
  /** Client-side only: an optimistic bubble the server has not acknowledged. */
  pending?: boolean;
  /** Client-side only: the optimistic send failed and can be retried. */
  failed?: boolean;
}

export interface ChatContact {
  id: number;
  full_name: string;
  role: UserRole;
  avatar_url: string | null;
  business_name: string | null;
}

// ═══════════════════════════════════════════════════════════════════════════
// MODULE 5 — the photographer managing their own listings and calendar
// ═══════════════════════════════════════════════════════════════════════════

/** A service as its owner sees it — adds live/archived and the delete guard. */
export interface OwnService extends Service {
  is_active: boolean;
  display_order: number;
  min_hours: number;
  max_travel_km: number;
  view_count: number;
  /** False once it has bookings — the UI then offers Archive instead. */
  can_delete: boolean;
}

export interface ServiceWritePayload {
  title: string;
  description?: string;
  category: number;
  price: string;
  pricing_unit?: Service['pricing_unit'];
  min_hours?: number;
  duration_hours?: number;
  edited_photos_count?: number;
  raw_photos_included?: boolean;
  delivery_days?: number;
  includes?: string[];
  advance_payment_percent?: number;
  max_travel_km?: number;
}

export interface ServicePackagePayload {
  name: string;
  price: string;
  description?: string;
  features?: string[];
  duration_hours?: number;
  edited_photos_count?: number;
  is_popular?: boolean;
}

export interface AvailabilityRule {
  weekday: number;
  weekday_label: string;
  is_available: boolean;
  start_time: string;
  end_time: string;
  max_bookings: number;
}

export interface Blackout {
  id: number;
  start_date: string;
  end_date: string;
  days: number;
  reason: string;
  is_full_day: boolean;
  start_time: string | null;
  end_time: string | null;
  created_at: string;
}

export interface MyCalendar {
  is_accepting_bookings: boolean;
  rules: AvailabilityRule[];
  blackouts: Blackout[];
}

/**
 * The result of blocking a range.
 *
 * `conflicting_bookings` is how many commitments fall inside it. Blocking
 * cancels nothing — the count exists so the photographer can cancel those
 * deliberately, with a reason the buyer sees.
 */
export interface BlackoutResult {
  blackout: Blackout;
  conflicting_bookings: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// MODULE 6 — portfolio
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Three sizes, generated at upload.
 *
 * The grid loads `thumbnail_url` (~20 KB); the full-screen viewer loads
 * `image_large_url` only when tapped. Using one size everywhere is the
 * biggest cause of slow portfolio screens on 3G.
 */
export interface PortfolioImage {
  id: number;
  caption: string;
  alt_text: string;
  image_url: string | null;
  thumbnail_url: string | null;
  image_large_url: string | null;
  width: number;
  height: number;
  aspect_ratio: number;
  is_featured: boolean;
  display_order: number;
  album: number | null;
  album_title: string | null;
  category: CategoryMini | null;
  like_count: number;
  view_count: number;
  is_liked: boolean;
  created_at: string;
}

export interface PortfolioAlbum {
  id: number;
  title: string;
  description: string;
  cover_image_url: string | null;
  category: CategoryMini | null;
  shoot_date: string | null;
  location: string;
  client_name: string;
  is_public: boolean;
  is_featured: boolean;
  display_order: number;
  image_count: number;
  view_count: number;
  created_at: string;
}

export interface PortfolioSummary {
  images: number;
  featured: number;
  albums: number;
  videos: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// MODULE 15 — the photographer's analytics dashboard
// ═══════════════════════════════════════════════════════════════════════════

export interface DashboardOverview {
  pending_requests: number;
  upcoming_shoots: number;
  completed_shoots: number;
  bookings_this_month: number;
  earnings_this_month: string;
  lifetime_earnings: string;
  avg_rating: string;
  reviews_count: number;
  success_rate: string;
  response_time_hours: string;
  profile_views: number;
  is_accepting_bookings: boolean;
}

export interface RevenuePoint {
  year: number;
  month: number;
  /** "Aug" — pre-formatted so the chart does no date maths. */
  label: string;
  bookings_completed: number;
  gross_revenue: string;
  net_earnings: string;
  growth_percent: number;
}

export interface DailyPoint {
  date: string;
  profile_views: number;
  bookings_created: number;
  bookings_completed: number;
  revenue: string;
}

/**
 * Seen → clicked → enquired → booked.
 *
 * Where it narrows is the actionable part: plenty of views and no bookings is
 * a pricing or portfolio problem; no views is a visibility problem.
 */
export interface Funnel {
  days: number;
  impressions: number;
  profile_views: number;
  clicks: number;
  inquiries: number;
  bookings: number;
  completed: number;
  /** Pre-computed — a client that divides shows NaN when views are 0. */
  view_to_booking_rate: number;
}

export interface TopService {
  service_id: number;
  title: string;
  bookings: number;
  completed: number;
  revenue: string;
}

export interface CategorySplit {
  category: string;
  bookings: number;
  revenue: string;
}

export interface Dashboard {
  overview: DashboardOverview;
  revenue_series: RevenuePoint[];
  daily_series: DailyPoint[];
  funnel: Funnel;
  top_services: TopService[];
  category_split: CategorySplit[];
  upcoming: BookingSummary[];
}
