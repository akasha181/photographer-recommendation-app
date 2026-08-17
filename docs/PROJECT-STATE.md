# SnapSphere — Project State

**Last updated:** 17 August 2026
**Next task:** Nothing is stubbed. Every module in §3 is complete. Remaining work
is polish and hardening — see §17.

Read this first when resuming. It records what exists, what was decided and
why, and exactly where to pick up.

---

## 1. How to start working

```bash
cd /Users/mac/Desktop/akasha
./start.sh          # MySQL + Redis + Django on :8000  (idempotent)
./test.sh           # 150-check API smoke test — should be ALL PASSED
cd mobile && npx expo start

# Unit tests (584, ~75s). --create-db after any migration.

# Analytics rollups. Needed once after a fresh seed, or charts are empty.
cd backend && .venv/bin/python manage.py backfill_analytics --days 400

# Demo data for the review flow. seed_data reviews almost every completed
# booking, so buyer1 has 216 of them and nothing left to review — the one screen
# Module 9 exists for opens empty on the documented test account.
cd backend && .venv/bin/python manage.py free_reviews --buyer buyer1@snapsphere.pk --count 3
cd backend && .venv/bin/pytest apps/
cd backend && .venv/bin/pytest apps/ --cov=apps.marketplace --cov-report=term-missing
cd mobile && npx tsc --noEmit
```

| | |
|---|---|
| Swagger UI | http://127.0.0.1:8000/api/v1/docs/ |
| Django admin | http://127.0.0.1:8000/django-admin/ (`admin@snapsphere.pk` / `admin12345`) |
| Phone access | `http://<LAN-IP>:8000/api/v1/` — `start.sh` prints it |

**Test accounts** — buyer `buyer1@snapsphere.pk` / `buyer12345`,
photographer `photographer1@snapsphere.pk` / `photographer123`.

---

## 2. Current size

| Area | Files | Lines |
|---|---|---|
| Backend (Django) | 250 | 34,034 |
| ML pipelines | 9 | 1,449 |
| Mobile (TypeScript) | 77 | 19,190 |
| Backend tests | 21 files | 584 tests |
| API smoke test | `./test.sh` | 150 checks |

**Database:** 77 tables · 445 users · 200 photographers · 52,199 bookings ·
51,822 reviews · 124 products · 362 product files · 496 generated cover
images · 40 funded wallets · 29,343 daily analytics rows · 6,765 monthly
revenue snapshots.

---

## 3. Module status

| # | Module | State |
|---|---|---|
| 1 | System architecture | ✅ Documented — `docs/01-system-architecture.md` |
| 2 | Database design | ✅ 46 domain tables, migrated, seeded |
| 3 | Authentication | ✅ Complete, verified end-to-end |
| 4 | **Buyer module** | ✅ **Complete — profile, wallet, top-ups, wishlist, purchases** |
| 5 | **Photographer module** | ✅ **Complete — services & pricing, availability editing, profile editing** |
| 6 | **Portfolio** | ✅ **Complete — upload with EXIF stripping, 3 renditions, albums, featuring** |
| 7 | **Booking** | ✅ **Complete — state machine, API, calendar, screens** |
| 8 | **Digital marketplace** | ✅ **Buyer-side complete — browse, cart, wallet checkout, secure downloads** |
| 9 | **Reviews & ratings** | ✅ **Complete — write API, replies, helpful votes, sentiment, moderation, screens** |
| 10 | AI recommendation | ✅ Pipelines, 3 models, live engine, explanations |
| 11 | Search & filters | ✅ 12 filters, 6 sorts, distance |
| 12 | **Notifications** | ✅ **Complete — REST API, badges, preferences, quiet hours, devices, live bell** |
| 13 | **Chat** | ✅ **Complete — REST + WebSocket, read watermark, mute/block, screens** |
| 14 | **Admin** | ✅ **Complete — approvals, moderation, users, wallets, settings, broadcasts, audit log** |
| 15 | **Analytics** | ✅ **Photographer dashboard — rollups, revenue chart, funnel, top services** |
| 16 | API docs | ✅ Auto-generated at `/api/v1/docs/` |
| 17 | RN screens | ✅ **All 10 tabs live — no placeholder screens left** |
| 18 | Deployment | ✅ Documented in `docs/01` §12 |
| 19 | Availability calendar | ✅ Read API — computed, 3 queries per window |
| 20 | Wishlist | ✅ Toggle + split lists, reusing each feature's own card |

---

## 4. What works right now

**Auth** — register, login, JWT refresh with rotation, logout, `/me`,
password reset, OTP, device registration. `token_version` kill switch and
blocked-account checks enforced on **every** request.

**Discovery** —
```
GET /catalog/categories/
GET /profiles/photographers/          12 filters, 6 sorts, distance
GET /profiles/photographers/{id}/     services + portfolio + reviews + histogram
GET /profiles/photographers/filters/  real cities + true price range
GET /recommendations/                 ranked, with human-readable reasons
GET /recommendations/status/          which model is live + its metrics
```

**Bookings** —
```
GET  /bookings/                       role-scoped; ?group=pending|upcoming|completed|cancelled
GET  /bookings/counts/                tab badges, one aggregate query
GET  /bookings/upcoming/              next confirmed shoots
POST /bookings/                       Idempotency-Key honoured for 24h
GET  /bookings/{id}/                  + timeline, price breakdown, available_actions
POST /bookings/{id}/accept|reject|cancel|complete/
```

**Availability** —
```
GET /availability/photographers/{id}/         calendar window; ?start=&days=
GET /availability/photographers/{id}/day/     ?date=&duration_hours= → free start times
GET /availability/photographers/{id}/rules/   weekly working pattern
```

**Shop** —
```
GET  /marketplace/products/           search, 6 filters, 5 sorts, ?affordable=
GET  /marketplace/products/{slug}/    + file manifest (names/sizes, never bytes)
GET  /marketplace/products/filters/   real types + true price range
GET/POST /marketplace/cart/ · /cart/add/ · /cart/remove/{id}/ · /cart/clear/
POST /marketplace/orders/checkout/    wallet debit, Idempotency-Key honoured
GET  /marketplace/orders/purchases/   the buyer's library
POST /marketplace/orders/items/{id}/download/   mints a single-use ticket
GET  /marketplace/download/{token}/   redeems it, streams once
GET  /marketplace/seller/products/    own catalogue incl. drafts + summary
```

**Photographer studio (Modules 5 & 6)** —
```
GET/POST/PATCH/DELETE /catalog/my-services/       own catalogue incl. archived
POST /catalog/my-services/{id}/archive|restore/   hide without losing history
POST /catalog/my-services/{id}/packages/          tiers (Silver/Gold/Platinum)
GET  /availability/me/                            weekly pattern + blocked periods
PUT  /availability/me/schedule/                   the whole week in ONE request
POST /availability/me/blackouts/add/              reports clashes, cancels nothing
GET/POST/PATCH/DELETE /portfolio/me/              upload strips EXIF, 3 renditions
POST /portfolio/me/{id}/feature/                  capped at 12
GET  /portfolio/photographers/{id}/images/        the public grid
```

**Analytics (Module 15)** —
```
GET /analytics/me/            the whole Dashboard in one response; ?days=&months=
GET /analytics/me/revenue/    monthly earnings series
GET /analytics/me/funnel/     seen → clicked → enquired → booked
python manage.py backfill_analytics --days 400   rebuild rollups (idempotent)
```

**Reviews (Module 9)** —
```
GET    /reviews/photographers/{id}/          public list; ?rating=&sort=&photos=
GET    /reviews/photographers/{id}/summary/  histogram, sub-averages, recommend %
GET    /reviews/products/{id}/               product reviews  (+ /summary/)
POST   /reviews/                             one per completed booking, DB-enforced
GET    /reviews/pending/                     what this buyer may review, both domains
GET    /reviews/mine/                        what they have written
PATCH  /reviews/{id}/                        24h window, and only before a reply
DELETE /reviews/{id}/                        withdraw; the entitlement stays spent
POST   /reviews/{id}/helpful/                toggle, returns the state it left
POST   /reviews/{id}/flag/                   into the one moderation queue
POST/PATCH /reviews/{id}/reply/              the photographer's single public answer
GET    /reviews/received/                    their inbox; ?unanswered=1
POST   /reviews/products/                    review a purchase
```

**Notifications (Module 12)** —
```
GET    /notifications/                  the bell; ?unread=1&category=
GET    /notifications/unread-count/     total + per-category, ONE query
POST   /notifications/mark-read/        some ids, or all when the list is empty
POST   /notifications/{id}/unread/      undo
DELETE /notifications/{id}/  ·  POST /notifications/clear/
GET/PATCH /notifications/preferences/   channels, categories, quiet hours
GET/POST  /notifications/devices/       idempotent push-token registration
POST   /notifications/devices/remove/   on logout
```

**Chat (Module 13)** —
```
GET  /chat/conversations/                    the Messages tab; ?archived=&unread=
POST /chat/conversations/                    open or find — idempotent per pair
GET  /chat/conversations/{id}/messages/      ?after= replays, ?before= scrolls back
POST /chat/conversations/{id}/messages/      client_id makes a retry safe
POST /chat/conversations/{id}/read/          moves the watermark, never backwards
POST /chat/conversations/{id}/mute|block|archive|leave/
GET  /chat/conversations/unread-count/       the tab badge
GET  /chat/conversations/contacts/           exactly who the server would allow
PATCH/DELETE /chat/messages/{id}/            edit or withdraw your own
POST /chat/messages/{id}/report/             into the same moderation queue
ws://…/ws/chat/{id}/  ·  /ws/notifications/  ·  /ws/presence/
```

**Administration (Module 14)** — every route `IsAdmin`, every write audited
```
GET  /admin/dashboard/                  queue depths (live) + totals + trend (rollups)
GET  /admin/approvals/                  oldest first; ?status=
POST /admin/approvals/{id}/approve|reject|more-info/
GET  /admin/flags/                      one queue for every content type
POST /admin/flags/{id}/claim|resolve/    ACTIONED also takes the content down
GET  /admin/users/  ·  /admin/users/{id}/    + cross-app stats
POST /admin/users/{id}/block|unblock|adjust-wallet/
GET  /admin/topups/  ·  POST /admin/topups/{id}/approve|reject/
GET  /admin/products/  ·  POST /admin/products/{id}/approve|remove/
POST /admin/bookings/{id}/force-cancel/  through the state machine, never an UPDATE
GET  /admin/audit/                      append-only; no write route exists
GET  /admin/settings/  ·  PATCH /admin/settings/{key}/   declared keys only
GET  /admin/settings/public/            the ONE AllowAny route
POST /admin/broadcasts/                 fanned out by a task
```

**Profile & wallet** —
```
GET/PATCH /profiles/me/ · /profiles/me/update/    buyer prefs or photographer listing
GET  /profiles/me/wallet/             balance + last 10 ledger rows
GET  /profiles/me/wallet/transactions/
POST /profiles/me/wallet/topups/request/   receipt upload; credits NOTHING
GET  /wishlist/ · POST /wishlist/toggle/   one endpoint for the heart icon
```

**Mobile** — all five buyer tabs are live. Login / Register / Forgot password,
Home (recommendations, categories, trending, featured), Explore (debounced
search, filter sheet, infinite scroll), Photographer detail.
**Booking flow**: request form with a real availability calendar, Bookings tab
with four status tabs and badge counts, booking detail with timeline and
server-driven action buttons, photographer Requests tab with one-tap accept and
reason-required decline.
**Shop flow**: product grid with search / type chips / "what I can afford",
product page with the file manifest, cart with per-line availability and a
server-computed shortfall, wallet checkout, and a Purchases library that opens
each single-use download link in the OS.
**Profile flow**: role-aware profile with stats, wallet card, availability
toggle for photographers, wallet screen with the ledger and receipt-upload
top-up sheet, Saved screen with photographer/product tabs, and the seller's
catalogue + earnings behind the photographer's Profile tab.
**Dashboard**: live headline counters (pending requests, upcoming shoots),
lifetime earnings, a six-month earnings bar chart with a growth badge, the
discovery funnel, best-selling services and where the work comes from — all
drawn with plain Views, no chart library.
**Reviews**: a star-and-words form reached from the booking's own `review`
action and from the Purchases library, with optional sub-ratings and up to five
photos; a "Reviews" screen listing what the buyer still owes before what they
have written; the photographer's inbox with a one-shot public reply; and the
full public list with a tappable star histogram, filters and "most helpful"
first.
**Notifications**: a bell with an unread dot in the Home and Dashboard headers,
a filterable list that deep-links from `action_screen` + `action_id`, and a
settings screen that states out loud which notifications ignore its switches.
**Chat**: a Messages list that renders from denormalised previews, a thread with
optimistic bubbles reconciled by `client_id`, an honest "Reconnecting…" when the
socket is down, tick / double-tick receipts, and a contact picker that offers
only people the server would accept. Reachable from a photographer's profile and
from either side of a booking.
**Photographer studio**: services screen with an editor sheet and
archive-vs-delete surfaced from `can_delete`, availability screen with a
seven-row week that saves as one unit plus date blocking, portfolio tab with
multi-select upload and a full-screen viewer that fetches the large rendition
only on tap, and an edit-profile form that names what it deliberately cannot
change.

---

## 5. Decisions that must not be re-litigated

| Decision | Why |
|---|---|
| **Expo SDK 54** — not 55/56/57 | Play Store Expo Go on the target device only supports 54. See `mobile/AGENTS.md`. Do NOT run `expo install expo@latest`. |
| **Modular monolith**, not microservices | ADR-001 in `docs/01` |
| **Ranker ships in "prior" mode** | The training data has no learnable signal (§6). This is deliberate and documented, not an unfinished model. |
| **Sentiment trains on `yelp.csv`, displays generated prose** | Yelp is the right training corpus; its restaurant text is wrong for display. See `apps/core/review_text.py`. |
| **Money is `DECIMAL`, serialized as a string** | JS floats cannot represent currency exactly |
| **PKR is the platform currency** | Dataset prices ×100, rounded to nearest 500 |
| **Wallet + admin-verified top-up**, no payment gateway | Proposal excludes online payments; wallet keeps downloads instant while staying in scope |
| **Product files are never URL-addressable** | A digital product is worthless the moment its file URL leaks. `core/storage.py` makes `.url` raise; the only path to bytes is a redeemed `DownloadToken`. |
| **Seller product upload is out of scope** | Needs private-file upload plus an admin moderation gate (Module 14). Sellers can still see their catalogue and earnings. |
| **Services are archived, not deleted, once booked** | `Booking.service` is PROTECT and the price is snapshotted. Deleting would break history; `can_delete` tells the UI which verb to offer. |
| **Narrowing the calendar never cancels a booking** | A commitment already made stays made. Blocking a range reports how many bookings fall inside so the photographer cancels them deliberately, with a reason the buyer sees. |
| **Portfolio upload strips EXIF** | Phone photos embed GPS. A newborn shoot would otherwise publish somebody's home address. Not an optimisation — a privacy requirement. |
| **Dashboard mixes live counters with rolled-up charts** | A dashboard stale in its headline is untrustworthy; one that recomputes 12 months of revenue on every load is slow. Counters are indexed live queries, charts read the nightly rollup. |
| **No chart library on mobile** | The project is pinned to Expo SDK 54 (`mobile/AGENTS.md`). A bar is a View with a height — a charting dependency buys nothing here and risks the native-module compatibility the pin protects. |
| **One review per booking, enforced by a OneToOne** | The serializer and the service both check it, but only the database cannot be reached around. To post N fake reviews an attacker must complete N real, paid bookings. |
| **A 1★ or 2★ review must carry a comment** | A bare low rating moves an average with no information attached, and it is the one case where the platform must be able to answer "on what grounds?" if it is disputed. |
| **Reviews are hidden, never deleted, by moderation** | A deleted review cannot be appealed. Hiding takes it out of the public average with a stored reason, and the row survives as evidence. |
| **The sentiment label is never shown to buyers** | A machine label on somebody else's words is not evidence. The photographer sees it on their own inbox; the public list omits the field entirely. |
| **Only a buyer may start a cold chat thread** | Otherwise the chat is a cold-outreach channel aimed at everyone who viewed a profile. A photographer may open one with a buyer they already have a booking with. |
| **Blocking is one-sided and silent** | The blocked party gets a normal success response. Telling them is what makes people create a second account. |
| **Chat pages by message id, not page number** | Rows arrive constantly at the end of a thread, so "page 2" means something different by the time it is fetched. `?after=` is what a reconnecting client replays with. |
| **Quiet hours suppress push only** | The in-app record is written either way, so nothing is lost — it just does not buzz at 03:00. Critical types ignore the window. |
| **Notifications are never created by a request** | Every one is a consequence of a domain event, written by the app that caused it. A client-postable notification is a spam vector with a platform logo on it. |
| **Every privileged admin action audits inside its own transaction** | A log claiming a user was blocked when the block rolled back is worse than no log. |
| **Admins cannot edit the audit log or move money outside the ledger** | There is no service function for either, and Django's admin registers `AuditLog` read-only. |
| **Platform settings are declared, not created ad hoc** | A settings table that accepts arbitrary keys becomes a junk drawer where a typo silently creates a second setting nothing reads. |
| **The admin surface is this API plus Django admin, not a React SPA** | A second frontend with its own auth, build and deploy story, for an audience of one. None of the rules live in the UI — they are all enforced server-side. |

---

## 6. Data-quality findings (verified statistically, not assumed)

Reproduce with `backend/.venv/bin/python -m ml.pipelines.ingest --audit`.

**`reviews_feedback.csv` — labels are random.** 5 distinct sentences across
300 rows, each carrying all three sentiment labels. Unusable. Sentiment model
trains on `yelp.csv` instead → **78.9% accuracy, 0.68 macro-F1**.

**`buyer_interactions.csv` — booking outcomes are random.** No photographer
attribute predicts booking: rating r=−0.006 (p=0.90), response time r=−0.000
(p=0.998), χ²(category, status) p=0.95. Booking rate by rating quartile:
32.3 / 32.5 / 32.8 / 31.2 — flat.

**Consequence:** `ml/pipelines/train_ranker.py` runs a **signal test before
training**. Finding none, it ships a transparent weighted scorer rather than a
model that would be confidently wrong (a fitted regressor scores R² = −0.03,
worse than the mean). The nightly retrain re-runs the same test against real
outcomes in `recommendation_events` and switches to the learned model
automatically once signal appears.

**Honest held-out metrics:**

| Model | Result |
|---|---|
| Sentiment | accuracy 0.789, macro-F1 0.681 |
| Ranker | transparent scorer — no learnable signal in source data |
| Collaborative filter | HitRate@10 0.094 (1.75× random) at 1.1% density |

The CF number was 0.97 before I fixed a leak — the similarity matrix had been
built from data including the held-out interaction. It now recomputes
similarity per trial.

---

## 7. Traps already hit — do not rediscover these

**MySQL silently drops conditional unique constraints.** Django's
`UniqueConstraint(condition=...)` becomes a partial index on PostgreSQL and
**nothing** on MySQL, with only a `models.W036` warning. Six integrity rules —
including the double-booking guard — were absent from the database.

Restored with MySQL's generated-column idiom in
`apps/*/migrations/000*_partial_unique_*.py`. **Any new conditional unique
constraint needs the same treatment.** Verified working:
```
Duplicate entry '280|2026-09-25|16:00:00' for key 'bookings.uniq_active_booking_slot'
```

**`bulk_create` overrides `auto_now_add`.** Django's `pre_save` always wins,
so back-dated rows land with `created_at = now`. Fix with a follow-up
`.update()` — see `_seed_review_history`.

**Soft delete breaks naive flushes.** `.delete()` on most models only flips
`is_deleted`. Use `all_objects.all().hard_delete()`, leaf-first past PROTECT
foreign keys.

**Custom JWT auth must be imported lazily.** `apps/core/exceptions` imports
`rest_framework.views`, which is still initialising when DRF resolves
`DEFAULT_AUTHENTICATION_CLASSES` — a module-level import crashes at startup.

**`upload_to` must be a `@deconstructible` class**, not a closure, or
`makemigrations` cannot serialise it.

**`IntegrityError` must be translated outside its `atomic()` block.** Catching
it inside leaves the transaction marked for rollback. See `create_booking`.

**drf-spectacular calls `get_queryset()` with an `AnonymousUser`.** Any
queryset reading `request.user.role` breaks schema generation and silently
degrades path parameters to untyped strings. Guard with
`if getattr(self, "swagger_fake_view", False): return Model.objects.none()`.
A plain `GenericViewSet` with no queryset at all warns for the same reason —
give it `queryset = Model.objects.none()`.

**No image was ever seeded.** All 124 products had a blank `thumbnail`, all
445 users no avatar, zero portfolio images. The Shop grid rendered a grey icon
on every card and read as broken rather than empty — the API was correct, the
data was absent. `_seed_product_images` now generates deterministic gradient
cover art (a colour swatch IS what a preset listing shows, so it is honest
rather than a stand-in for photography the platform does not have). Avatars
still have none, but `Avatar`'s initials fallback makes that look designed.

**A declared setting is not a used setting.** `PRIVATE_MEDIA_ROOT` existed for
weeks while every paid product file sat in MEDIA_ROOT at a public URL. If a
setting names a security property, grep for it before trusting the docstring
that describes it.

**Django caches reverse one-to-ones on the instance.** `user.wallet` is
populated the moment it is touched (creating `Wallet(user=user)` is enough),
so any code that credits or debits and then reads `user.wallet.balance` in the
same request sees the pre-transaction value. Read balances through
`profiles.selectors.wallet_balance()`.

**Timestamps to the second are not unique.** `Order.order_number` and — before
it was fixed — `DigitalProduct.slug` both collided when two rows were created
in the same second. Add a random suffix.

**Tests that depend on the time of day are flaky, not passing.** A fixed date
two days out sits either side of a 48-hour window depending on when the suite
runs. Pin the *interval*, not the date.

**A list screen must not open on an empty tab.** Defaulting the Bookings tab
to "pending" showed an empty screen to a photographer with 410 completed
shoots. An empty default reads as "no data for me", not "all caught up" —
land on the first group that has rows.

**`THUMBNAIL_SIZES` keys are `thumb`/`medium`/`large`.** The `ProductFile`
model field is called `thumbnail`; passing the field name as the size key
raises `KeyError` on every upload.

**Bash brace-expands `{a,b}` inside a double-quoted string.** A Python set
literal passed to `test.sh`'s `jget` helper — `set(d) == {'a','b'}` — is
mangled before Python ever sees it. Use `sorted([...])`.

**The default allow-list for CORS headers does not include your own headers.**
`Idempotency-Key` was missing, so `POST /bookings/` and the marketplace checkout
would be refused at the *preflight* from any browser origin — while working
perfectly from Expo Go, because native requests never preflight. The worst shape
a bug can have: invisible on the device it was tested on. Now declared in
`CORS_ALLOW_HEADERS` in base settings, because the header is part of the API
contract in every environment.

**`CSRF_TRUSTED_ORIGINS` cannot wildcard IP octets.** Django 4+ needs the origin
listed for any non-localhost form POST (the browsable API, `/django-admin/` from
a phone), and `http://192.168.*.*:8000` is not a thing it accepts. `dev.py`
derives the machine's LAN address instead — a stale hard-coded entry fails with
"CSRF verification failed", which reads as a code problem rather than a config
one.

**Seeding a review for every completed booking makes the review flow
undemonstrable.** It is the right default — a photographer with 410 delivered
shoots and 3 reviews looks broken — but it left `buyer1@snapsphere.pk` with
nothing to review. `manage.py free_reviews` un-reviews the N most recent and
recomputes the affected ratings; it lives in a management command rather than a
service because clearing `has_review` is a data fixture, not a business
operation the application should ever perform.

**A trained model with nothing labelled looks like an unimplemented feature.**
All 51,819 seeded reviews predate `core/sentiment.py`, so the photographer's
sentiment breakdown read 0/0/0 and the review card's tone chip never rendered.
The nightly `recompute_review_sentiment` task drains 500 per run by design; for a
demo, batch-predicting the whole table and `bulk_update`-ing it takes **29
seconds** — one `predict()` over 2,000 strings costs a fraction of 2,000 calls.

**Run `backfill_analytics` after any fresh seed.** The seeded
`DailyPhotographerStat` rows from the CSVs stop at January 2024, so every
dashboard window is empty until the rollup is rebuilt from the real bookings
table.

**Django caches reverse one-to-ones on the instance — and it is not only
`user.wallet`.** `notifications.services._is_muted` read
`user.notification_preference`, which registration populates. The settings screen
saved a *different* instance, so a notification fired later in the same request
still used the pre-save preferences and a mute silently did nothing. Same trap,
same fix: read the database. The chat equivalent was
`message.conversation.last_message_at` — `Message.objects.create(conversation=…)`
caches the instance that was passed in, whose denormalised columns predate the
write, so "was this the last message?" was always false and a deleted message
never had its preview corrected. Compare ids instead.

**Mixing a `Count` over a joined relation with an `Avg` in one `aggregate()`
corrupts the average.** `Count("id", filter=Q(images__isnull=False))` beside
`Avg("rating")` adds a LEFT JOIN to `review_images`, which duplicates a review
row per image — so a review with three photos weighed three times in the
headline rating. The photo count is a separate query, deliberately.

**A profile id is not a user id.** `PhotographerProfile.id` is what booking,
portfolio and review endpoints take; chat addresses people by account id. Opening
a thread from a booking needed a number the payload did not carry, so both
`BookingPartySerializer` and `PhotographerListSerializer` now send an explicit
`user_id` alongside `id`.

**A smoke test that reuses an intentionally-broken token proves nothing.** The
chat scoping check reused the access token from §1, which §5 blocks on purpose
while testing the kill switch — so it got 403 ACCOUNT_BLOCKED and would have
passed a laxer assertion while never touching conversation scoping. It registers
its own account now.

**A validation error and a race error are different status codes for the same
rule.** A second review is 400 from the serializer (friendly, field-attributed)
and 409 from the service (the concurrent path). Both paths are real; a test has
to know which one it is exercising.

**`bash` scripts must not name a variable `UID`.** zsh treats it as read-only and
the assignment fails with "operation not permitted", which reads as a
permissions problem rather than a naming one.

**Diff the mobile types against live responses, not against the serializer by
eye.** `Service.cover_image` had been wrong since the type was written — the
API sends `cover_image_url`, so the field silently read `undefined`
everywhere. A 30-line script comparing interface keys to real payloads found
it in seconds.

---

## 8. Module 7 — Booking (complete, 31 July 2026)

### How it is built

`apps/bookings/services.py` is the only place a booking is created or moved.
Views never touch `Booking.status`, which is what makes these true of the
whole system rather than of one endpoint:

1. **No double booking.** The availability check and the INSERT run inside one
   `transaction.atomic()` with the photographer's row held by
   `select_for_update()`. Two buyers racing serialize behind that lock, so the
   loser sees "that slot was just taken" instead of a raw integrity error.
   `uniq_active_booking_slot` remains underneath as a backstop, not as the
   mechanism.
2. **Price is snapshotted** from the service (or chosen package) at creation
   and never re-read. `test_price_survives_the_service_changing` pins this.
3. **Every transition is legal and attributed.** `can_transition()` is the only
   authority; each accepted change appends a `BookingStatusHistory` row naming
   the actor. Append-only.
4. **Notifications never lie.** `notify()` defers to `transaction.on_commit`,
   so a rolled-back transaction cannot announce a booking that does not exist.

`apps/availability/selectors.py` computes bookability rather than storing it:
**three queries for any window length** (rules, overlapping blackouts,
blocking bookings), then arithmetic. A 180-day calendar costs what a one-day
check costs.

### Decisions made here

| Decision | Why |
|---|---|
| **`available_actions` computed server-side** | The app renders its buttons from it. Reimplementing the state machine in TypeScript guarantees drift, and a button that always errors is worse than no button. |
| **Phone numbers withheld until ACCEPTED** | Releasing them on "request" turns the platform into a free lead list and invites the next job off-platform. |
| **Capacity is checked before the exact slot** | `max_bookings` defaults to 1, so "Fully booked on this date" is the message a buyer usually needs; the exact-slot 409 only fires when capacity allows a second shoot. |
| **Rejection requires a reason, buyer cancellation does not** | "Declined" gives the buyer nothing to act on; demanding a reason to withdraw an unanswered request just makes people abandon the screen. |
| **Completion refused before the event date** | Otherwise a photographer can close a job early to unlock the review prompt. |
| **Accept still allowed after `expires_at`, before the sweep runs** | The booking is still PENDING and the slot still held; punishing a photographer for a 15-minute cron interval helps nobody. |
| **Idempotency via `cache.add` (set-if-absent)** | A dropped response makes the app retry the POST. Without a key the buyer gets two requests, and the second fails citing their own booking. |
| **Mobile date picker is the server calendar, not a native picker** | A stock picker happily offers Sundays the photographer never works. Also avoids a new dependency on SDK 54. |

### Tests

161 tests, ~14s. `constants.py` (the transition table) **100%**,
`services.py` 99%, `selectors.py` 100%.

```
apps/bookings/tests/test_state_machine.py    every legal + illegal edge, per actor
apps/bookings/tests/test_create_booking.py   guards, price snapshot, idempotency
apps/bookings/tests/test_concurrency.py      real threads; app lock AND db constraint
apps/bookings/tests/test_lifecycle_tasks.py  expiry, auto-complete, reminders
apps/bookings/tests/test_selectors.py        scoping — no selector leaks another user
apps/bookings/tests/test_api.py              authorisation, envelope, available_actions
apps/availability/tests/test_selectors.py    reason priority, capacity, start times
```

Two uncovered lines in `services.py` are deliberate: the non-slot
`IntegrityError` re-raise, and the self-booking guard, which is unreachable
while `_assert_buyer` runs first and is kept only so reordering cannot quietly
allow it.

`./test.sh` grew from 23 to 36 checks — section 7 drives a real booking
through the API and cleans up after itself.

### Traps found while building this

**MySQL `max_bookings` shadows the slot check.** The seeded calendar allows one
shoot per day, so a second booking on the same date is refused as
`FULLY_BOOKED` before the exact-start-time guard is ever reached. Tests that
mean to exercise the slot conflict must raise `AvailabilityRule.max_bookings`
first — otherwise they pass while testing the wrong thing.

**`IntegrityError` must be translated outside the atomic block.** Catching it
inside leaves the transaction marked for rollback. `create_booking` wraps
`_create_booking_locked` and translates after the block exits.

**drf-spectacular introspects `get_queryset()` with an `AnonymousUser`.** Any
queryset that reads `request.user.role` raises during schema generation and
silently degrades the path parameter to an untyped string. Guard with
`if getattr(self, "swagger_fake_view", False)`.

---

## 9. Modules 8 & 4 — Shop and Profile (complete, 31 July 2026)

### What checkout guarantees

`marketplace/services.checkout()` puts the wallet debit, the order, every item
and every seller credit inside ONE `transaction.atomic()`. There is no window
in which a buyer has been charged but owns nothing, or owns something nobody
was paid for. `test_insufficient_balance_leaves_nothing_behind` is the test
that pins it: the order row is created *before* the debit precisely so the
rollback has something to prove.

- **The wallet cannot go negative** — `debit_wallet` locks the row with
  `select_for_update`, and `ck_wallet_no_overdraft` backs it in the database.
- **Prices are snapshotted** onto `OrderItem`. An order is a receipt, and a
  receipt that changes when the seller edits their listing is not a receipt.
- **One seller, one credit** — earnings are aggregated per seller before
  crediting, so a basket with three of their products moves their balance once
  rather than reading like three sales.
- **Retries are safe** — `Order.idempotency_key` is uniquely constrained per
  buyer, so a double-tap cannot charge twice.

### The download flow

Files never sit at a reachable URL. A buyer asks for a token, gets a
single-use ticket valid 15 minutes, and redeems it once. The counter moves
when the **ticket is issued**, not when the bytes finish — counting on
completion sounds fairer but is unenforceable, and would make `max_downloads`
decorative.

### Decisions made here

| Decision | Why |
|---|---|
| **`private_storage` overrides `url()` to raise** | Passing `base_url=None` is not enough — FileSystemStorage falls back to MEDIA_URL, so `.url` returned `/media/products/…`: a path that 404s but looks valid in a JSON response. A misleading URL is worse than an error, because it ships. |
| **X-Accel gated on its own setting, not `not DEBUG`** | A deployment without a reverse proxy would otherwise return an empty body plus a header nothing acts on — invisible until a real buyer clicks download. |
| **Cart reports availability per line** | A product can be delisted or already owned between adding and checking out. Per-line reporting lets the buyer remove one item instead of facing one opaque error for the basket. |
| **`can_checkout` / `shortfall` are server numbers** | Money is DECIMAL on the server and a string on the wire precisely because JS cannot add currency. Doing `total - balance` in JS is how a cart says "you need Rs 0" and checkout then fails. |
| **Top-up credits nothing** | The manual gate exists so a claimed transfer is never taken on trust. Only `approve_topup` moves a balance. |
| **Wishlist `toggle` returns the state it left behind** | The UI is one heart icon. Separate add/remove endpoints make the client guess which state the server is in, and a double-tap desyncs the icon it just drew. |
| **Seller list uses its own serializer** | It includes unpublished drafts, so it needs `is_published`/`is_approved` — which stay off the public grid, where both are true by definition. |
| **Seed files are labelled text stand-ins** | Shipping fabricated `.xmp` binaries would read as real product data in a demo. Each file names itself for what it is. |
| **Product cover art is generated, not downloaded** | These are colour presets and LUTs, and what such a listing shows IS a swatch — so a gradient is an honest representation. Downloading real photos would put someone else's copyrighted work in the demo, which is what `is_approved` exists to prevent. |
| **Seeded balances go through `credit_wallet`** | A balance with no ledger row breaks the invariant the ledger exists to prove, and the first person to reconcile the two would chase a bug that was never in the application. |

### Tests

268 total, ~20s. `marketplace/services.py` 94%, `views.py` 96%,
`selectors.py` 95%.

```
apps/marketplace/tests/test_checkout.py    atomicity — every failure asserts nothing moved
apps/marketplace/tests/test_downloads.py   private storage, token single-use, both stream paths
apps/marketplace/tests/test_shop_api.py    visibility, flags, cart, orders, seller
apps/wishlist/tests/test_wishlist.py       toggle, counters, suspended-target filtering
apps/profiles/tests/test_wallet_and_profile.py  ledger reconciliation, top-up gate, privilege escalation
```

### Bugs found and fixed while building this

**`PRIVATE_MEDIA_ROOT` was declared but never used.** `ProductFile.file` was a
plain `FileField`, so every paid product landed in MEDIA_ROOT at a guessable
public URL — the download-token flow was guarding a door with no wall beside
it. Fixed with `apps/core/storage.py`; declaring a setting is not the same as
using it.

**`Order.order_number` used a whole-second timestamp.** Two buyers checking
out in the same second collided on the unique index and the second got a 500.
The same class of bug `DigitalProduct.save()` already documents; fixed the
same way, with a random suffix.

**`user.wallet.balance` could be stale.** Django caches a reverse one-to-one
on the instance as soon as it is touched, and `credit_wallet`/`debit_wallet`
update a *different* instance fetched under `select_for_update`. So a cart
summary read after a debit reported the pre-transaction balance.
`profiles.selectors.wallet_balance()` now reads the database and is the only
authority.

**A booking test was time-of-day dependent.** `test_late_cancellation` used a
fixed date two days out, which sits inside the 48-hour free-cancellation
window in the evening and outside it in the morning. Now pinned to exactly 24
hours away, with the mirror case added.

---

## 10. Modules 5 & 6 — the photographer's studio (complete, 31 July 2026)

### Why this was built

Logging in as a photographer showed almost nothing: two of five tabs were
placeholders, and the other two opened on empty lists. One of those was a bug
(below); the rest was simply the module.

### Decisions made here

| Decision | Why |
|---|---|
| **Archive, not delete, once a service has bookings** | `Booking.service` is PROTECT and the price is snapshotted, so removal would break history. The server sends `can_delete` and the row offers the right verb — rather than showing Delete and failing on tap. |
| **`base_price` recomputed on every catalogue write** | It is the "from Rs X" on every search card AND the column search filters on. Without this a photographer adds a cheap service and is still filtered out of a budget search that now matches them. |
| **The weekly schedule saves as ONE request** | The screen is a single seven-row form. Seven PATCHes would leave a half-applied week if the connection dropped, and the calendar would then mix the old pattern with the new. |
| **Blocking dates cancels nothing** | Blocking the week you are getting married is exactly when you need to; refusing over one accepted shoot would leave the rest open. The response reports the clash count so the photographer cancels deliberately, with a reason the buyer sees. |
| **Upload strips EXIF** | Phone photos embed GPS. A newborn shoot would publish somebody's home address. `process_image` re-encodes from raw pixel data, which discards every metadata block. |
| **Three renditions per upload** | Grid loads `thumbnail` (~20 KB); the viewer loads `image_large` only on tap. One size everywhere is the biggest cause of slow portfolio screens on 3G. |
| **Deleting an album keeps its images** | `PortfolioImage.album` is SET_NULL. There is no undo on that screen, and losing an evening's uploads because a folder was tidied away is the wrong default. |
| **Featured images capped at 12** | "Everything is featured" means nothing is, and the public detail endpoint only prefetches twelve anyway. |

### Tests

333 total, ~47s. Catalog 23, availability 37, portfolio 24.

```
apps/catalog/tests/test_my_services.py       archive-vs-delete, base_price, scoping, tiers
apps/availability/tests/test_my_calendar.py  schedule saves atomically, blocks cancel nothing
apps/portfolio/tests/test_portfolio.py       EXIF stripped, 3 sizes, caps, album survival
```

The EXIF test opens the stored file and asserts the metadata dict is empty —
it would fail if `process_image` were ever swapped for a plain save.

### Bugs found and fixed while building this

**The Jobs tab opened empty for established photographers.** `BookingsScreen`
defaulted to the `pending` group for both roles, so a photographer with 410
completed shoots and nothing awaiting a reply saw an empty list — which reads
as "this app has no data for me", not "you're all caught up". It now lands on
the first group that has rows, with pending still winning when non-empty
because it is the only one with a deadline.

**`THUMBNAIL_SIZES` uses the key `"thumb"`, not `"thumbnail"`.** The model
field and the size key differ; passing the field name would have raised
`KeyError` on every single upload.

**The mobile `Service` type had `cover_image` where the API sends
`cover_image_url`**, and was missing four fields including `packages`. A
pre-existing drift, caught by diffing the TS interfaces against live
responses — the field was simply always `undefined` wherever it was read.

---

## 11. Module 15 — Analytics dashboard (complete, 13 Aug 2026)

### Why this was built

It was the last placeholder in the app. Logging in as a photographer landed on
a Dashboard tab that said "Module 15 — Analytics" and nothing else.

### The design: two speeds on purpose

`selectors.overview()` computes the headline counters **live** — pending
requests, upcoming shoots, earnings this month. They are indexed on
`(photographer, status)`, they are a handful of rows, and they must be correct
the second a request arrives. A dashboard stale in its headline is
untrustworthy.

The charts read **pre-aggregated** rollups. A 12-month revenue series over
52,000 bookings is a scan plus a GROUP BY; reading 12 tiny rows is not, and the
cost stays constant as the business grows.

### Decisions made here

| Decision | Why |
|---|---|
| **Every rollup is `update_or_create` keyed on the date** | It runs nightly, gets retried after failures, and gets re-run by backfills. Additive writes would silently corrupt the history the table exists to preserve. |
| **A day with no activity writes no row** | 200 zero rows a day is 73,000 a year saying nothing. The dashboard fills gaps on read instead. |
| **Revenue lands on the day the shoot COMPLETED** | A booking created in June and completed in August is August's revenue — that is the month the photographer was actually paid for it. |
| **Rates are stored, not divided on the client** | A chart that guards against divide-by-zero in three places will show NaN in one of them. |
| **Series arrive gap-filled** | A missing month means "earned nothing", not "no data". Omitting it draws December next to March with no visible break. |
| **The rollup runs for YESTERDAY, not today** | A rollup of a day still in progress is wrong the moment another booking lands — which is exactly why the headline is computed live. |
| **No chart library** | See §5. A bar is a View with a height; the dependency would risk the SDK 54 pin for nothing. |
| **No "analytics for photographer X" route** | Engagement and revenue are competitively sensitive. The only person entitled to them is their owner. |

### Tests

25 analytics tests; 358 total. The idempotence test runs the same day three
times and asserts one row with unchanged counts — that is the property every
other guarantee here depends on.

```
apps/analytics/tests/test_analytics.py   idempotence, what each counter counts,
                                         gap filling, clamping, owner-only access
```

### Backfill

`python manage.py backfill_analytics --days 400` rebuilt 29,343 daily rows and
6,765 monthly snapshots from the real bookings table. **Run this after any
fresh seed** or the charts are empty — the seeded `DailyPhotographerStat` rows
from the CSVs stop at January 2024 and fall outside every dashboard window.

### Known data limitation

The funnel (seen → clicked → enquired → booked) reads `BuyerInteraction`, and
every seeded interaction row was created at seed time rather than spread over
history. So a 30-day funnel is nearly empty even for a photographer with 410
completed shoots. The chart degrades honestly ("Not enough activity in the last
30 days to chart yet") rather than inventing numbers. Spreading seeded
interactions over the last year would fix the demo — deliberately not done,
for the same reason product photos are generated swatches rather than
downloaded photographs.

---

## 12. Module 9 — Reviews & ratings (complete, 17 Aug 2026)

### The rule the whole module exists to enforce

"Only a buyer with a completed booking may review that photographer, once."

Enforced three times, and the redundancy is the point:

1. **Serializer** — resolves the booking, checks it is COMPLETED and belongs to
   the caller, and returns a friendly, field-attributed 400.
2. **Service** — re-checks under `select_for_update` inside the transaction, and
   returns 409. Two taps on Submit both pass step 1; this is where the loser
   stops.
3. **Database** — `Review.booking` is a OneToOne. This is the only level an
   attacker cannot reach around, and it is what makes review-bombing
   infeasible rather than merely discouraged.

### What happens atomically when a review is posted

Four things must never disagree, so `create_review` does all four in one
transaction and only `notify()` (which defers to `on_commit`) happens after:

1. the `reviews` row
2. `Booking.has_review` — which drives `is_reviewable` and the app's `review`
   action
3. `PhotographerProfile.avg_rating` / `reviews_count` / `bayesian_rating`
4. `BuyerProfile.reviews_written`

Defer (3) to a Celery task and a profile shows "4.8 from 12 reviews" above a
list of 13.

### Decisions made here

| Decision | Why |
|---|---|
| **Editing is time-boxed AND reply-boxed** | 24 hours, and only while there is no reply. Once a photographer has answered publicly, editing the review above it would let a buyer rewrite the question their answer was given to. |
| **Withdrawing a review does not restore the entitlement** | `has_review` stays true. Otherwise delete-and-repost is an unlimited rating weapon aimed at one photographer. |
| **A reply is OneToOne, not a thread** | An unbounded public back-and-forth turns a dispute into a spectacle. The chat module exists for the conversation. |
| **Sub-ratings are nullable and average to `None`** | A photographer whose buyers never filled them in gets "not rated yet", not a damning zero. |
| **`helpful_count` is maintained with `F()`** | Two people voting at once cannot read-modify-write over each other, and the list needs no subquery per row. |
| **Flagging never auto-hides** | A threshold hands anyone with three accounts an eraser for honest criticism. A human decides; the counter is denormalised so mass-reporting is visible in the list itself. |
| **`can_edit` and `marked_helpful` are computed server-side** | Same reason as `available_actions` on a booking: re-deriving the window and the vote in TypeScript guarantees the app eventually offers a button that always errors. |
| **Sentiment inference lives in `apps/core`** | `reviews`, `recommendations` and `analytics` all have a claim on it. Putting it in any consumer would make the others import sideways and break the acyclic graph in docs/01 §5.1. |
| **A missing model artifact is not an error** | `sentiment.joblib` is a build product. A fresh clone must still be able to post a review — the label is decoration on the review, not part of it. Every failure path returns `(None, None)` and logs once. |
| **Comments under 12 characters are left unlabelled** | TF-IDF over "ok" still returns a confident-looking probability, because softmax always sums to one. |

### Tests

93 review tests. `serializers.py` 94%, `views.py` 89%, `services.py` 85%.

```
apps/reviews/tests/test_reviews.py        eligibility, the three levels, rating recompute
apps/reviews/tests/test_review_api.py     authorisation, scoping, per-caller flags
apps/reviews/tests/test_review_tasks.py   the reminder asks exactly once; artifact-free fallback
```

The test that matters most is `test_the_database_refuses_a_second_review_even_without_the_service`:
it bypasses both application layers and asserts the `IntegrityError`. The others
can be defeated by a code path that does not exist yet; that one cannot.

---

## 13. Module 12 — Notifications (complete, 17 Aug 2026)

### Shape

`notify()` already existed and was already being called by bookings, marketplace
and the expiry jobs. What was missing was every way to read the result. The REST
layer is thin on purpose — the interesting decisions are all about what it
refuses to do.

### Decisions made here

| Decision | Why |
|---|---|
| **There is no "send a notification" endpoint** | Every notification is a consequence of a domain event, written by the app that caused it. A client-postable notification is a spam vector with a platform logo on it. The admin broadcast is the single exception: admin-only, audited, and fanned out by a task. |
| **Opening the bell marks nothing read** | Glancing at a list is not reading it. Auto-clearing means the badge vanishes and the user can no longer find what it was about. |
| **The list carries its own unread count in `meta`** | One request draws the screen. Two would let the rows and the number disagree for as long as the second is in flight. |
| **`mark-read` with an empty id list means "all"** | Enumerating 200 ids to clear a badge makes the request size depend on how long the user ignored it. |
| **"Clear all" only clears what was read** | Wiping an unread booking cancellation would be destructive in a way the button does not look. |
| **Notifications are hard-deleted; retention is asymmetric** | This is a delivery record, not a financial one — nothing references it and nobody audits it. Read rows go after 30 days, unread after 90: a notification nobody opened may be the only record of something they need. |
| **Quiet hours suppress the PUSH channel only** | The in-app row is already written, so nothing is lost. Critical types ignore the window entirely. |
| **The category chip is derived server-side from the type prefix** | The chip a notification appears under and the chip that filters it read the same map, so they cannot disagree. |
| **Device registration is an upsert on (user, token)** | The app calls it on every launch because the OS rotates tokens. It also deactivates that device's previous token, so a rotated token stops receiving pushes that go nowhere. |
| **Logout deactivates rather than deletes a token** | `failure_count` history survives; a deleted row restarts that count from zero on the next launch. |

### Known limitation, stated rather than hidden

`tasks.send_push_notification` does all the delivery bookkeeping — preference
check, quiet hours, per-channel `NotificationDelivery` row, SENT/SKIPPED status —
but the provider call itself is a log line. Wiring FCM or Expo Push is a
one-function change; it is not done because it needs credentials this project
does not have, and because `expo-notifications` is a native dependency that would
risk the SDK 54 pin (see §5). The app therefore has no push token to register —
the endpoint is real and tested, and nothing calls it yet.

### Tests

34 notification tests. `selectors.py` 100%, `views.py` 95%, `services.py` 94%.

```
apps/notifications/tests/test_notifications.py  scoping, badge arithmetic, mute vs
                                                critical, quiet hours across
                                                midnight, device rotation, retention
```

The parametrised quiet-hours test is the one worth reading: the default window
(22:00 → 08:00) crosses midnight, and a naive `start <= now <= end` returns False
for every hour of the night — which is precisely the period the feature exists
for.

---

## 14. Module 13 — Chat (complete, 17 Aug 2026)

### MySQL is the source of truth; the socket is transport

`send_message` writes the row, updates both participants' counters, and only then
broadcasts. The WebSocket consumer takes the same path. A phone that switches
from Wi-Fi to mobile data mid-thread reconnects and replays with
`?after=<last id>` — nothing is lost, because nothing ever lived only in the
socket. Building it the other way round is how chat apps lose messages.

### The read watermark

`ConversationParticipant.last_read_message_id` is one integer meaning "everything
up to here is read". The alternative — a row per message per user — makes the
unread count a COUNT over millions of rows. The watermark makes it a single
indexed comparison, and `mark_read` refuses to move it backwards so an
out-of-order frame from a reconnecting client cannot resurrect read messages.

### Decisions made here

| Decision | Why |
|---|---|
| **Only a buyer may start a cold thread** | With a listed, approved photographer. Otherwise the chat becomes cold outreach aimed at everyone who ever viewed a profile. A photographer may open one with a buyer they have a booking with — after an accepted booking the two are working together. |
| **The contact picker mirrors that rule exactly** | A picker that offers somebody the POST then refuses is worse than a shorter picker. |
| **Opening a thread is idempotent** | Two taps on "Message" must not split the history in two — neither side could tell which half the other was reading. No unique constraint can express "one thread per unordered pair" across a through-table, so the lookup runs inside the transaction. |
| **`client_id` is uniquely constrained per conversation** | The app draws its bubble instantly and posts with the key. A retry after a dropped response returns the SAME message instead of posting a second one. |
| **Blocking is silent and one-sided** | The blocker's unread count stops rising; the blocked party gets a normal 201. |
| **Deleting a message keeps the row** | The other party has already read it, and silently erasing text from someone else's history is worse than admitting it was withdrawn. "This message was deleted" is also what an admin redaction leaves behind. |
| **Attachments are re-encoded through `process_image`** | EXIF, including GPS, is stripped. The privacy requirement does not change because the audience is one person instead of a public grid. |
| **The rate limit lives in the service, not in DRF** | A WebSocket frame bypasses DRF throttling entirely, so the limit has to be somewhere both paths reach. Redis with a 60-second TTL; losing it on a cache restart lets one user send a few extra messages, which is the right failure mode for chat. |
| **Archiving is per-thread, not per-participant** | A limitation stated rather than hidden: `Conversation.is_archived` is one column, so it hides the thread for both sides. Per-user archiving needs a column on the participant link and a migration. |

### Tests

50 chat tests. `views.py` 92%, `serializers.py` 86%, `selectors.py` 85%,
`services.py` 84%.

```
apps/chat/tests/test_chat.py  one thread per pair, who may initiate, privacy by id,
                              client_id retry, before/after windows, the watermark,
                              mute vs block, delete semantics, contact parity
```

`test_before_returns_the_window_just_above_the_scroll_position` pins the subtle
one: selecting `pk < before` ordered ascending hands back the *start* of the
conversation, so an old thread would jump to its beginning on every pull.

`consumers.py` remains at 0% coverage — the WebSocket path is exercised by hand
and by the app, not by the suite. Both paths write through
`services.send_message`, so the rules are tested even where the transport is not.

---

## 15. Module 14 — Administration (complete, 17 Aug 2026)

### Why the audit log is the centre of this module

Every privileged action calls `_audit()` **inside** the `atomic()` block of the
action it records. If the block rolls back the entry goes with it — a log
claiming a user was blocked when they were not is worse than no log. And because
it is in the same transaction, there is no path that changes state and forgets to
record it: the action would have to be written without its audit call, which is
visible in every function in `services.py`.

Each entry answers "why was my account blocked?" with evidence: the actor, the
reason, a before/after `changes` dict, a human-readable `target_label` that
survives the target being anonymised, and the request's IP, user agent and
request id — which is what makes an entry correlatable with the JSON access logs.

### What admins deliberately cannot do

* **Edit or delete an audit entry.** No service function, no route (POST is 405,
  there is no detail route at all), and Django's admin registers `AuditLog`
  through `ReadOnlyAdminMixin` — a class that had sat unused in `core/admin.py`
  since it was written.
* **Move money without a ledger row.** `adjust_wallet` goes through
  `credit_wallet` / `debit_wallet`, which lock the row and write the
  `WalletTransaction`. A debit that would overdraw raises `InsufficientBalance`,
  backed by `ck_wallet_no_overdraft` — an admin cannot push a balance negative
  any more than a buyer can.
* **Delete a review.** Reviews are hidden with a stored reason, because a deleted
  review cannot be appealed.
* **Bypass the booking state machine.** `force_cancel_booking` calls
  `bookings.services.cancel_booking`, so the transition is legal, attributed in
  `BookingStatusHistory` and notified. An `.update()` would move a status with no
  record of who did it.

### Decisions made here

| Decision | Why |
|---|---|
| **Blocking bumps `token_version` and cancels open bookings** | Without the bump a blocked user keeps working for up to 30 minutes on the access token in their pocket. Leaving their PENDING bookings in place would hold calendar slots for shoots that cannot happen — each is cancelled through the state machine, with a reason the other party sees. |
| **Rejecting a new application does not unlist an approved photographer** | They keep the listing they already earned. Removing a live listing is `block_user`, audited under its own action, with a reason the user is told. |
| **A rejection requires a reason of at least 10 characters** | A bare rejection gives the applicant nothing to fix and turns every decision into a support ticket. |
| **"More information required" is its own status** | The queue has to show "waiting on them" separately from "decided", or the same application gets reviewed twice. |
| **The approval and moderation queues sort oldest-first** | A queue sorted newest-first starves whoever has been waiting longest, which is the opposite of what a queue is for. |
| **Duplicate reports from one person collapse** | The reporter gets a success response either way, and the queue does not fill with the same complaint tapped three times. |
| **Resolving a flag as ACTIONED applies the consequence** | A queue where "actioned" does not act is a queue that lies. The consequence and the resolution are one transaction. |
| **Removing a product sets `is_approved=False`, never deletes** | `OrderItem.product` is PROTECT and buyers who already paid keep their downloads. A pulled listing must not revoke a licence somebody bought. |
| **The moderation queue previews its targets per row** | Without it the queue is a list of ids and judging one report means opening four screens. A generic relation cannot be prefetched, and this is a handful of rows an admin works through — not a hot endpoint. A missing target renders as a dash rather than a 500. |
| **Queue depths are live; the trend reads the rollups** | Same split as the photographer dashboard: a queue depth an hour stale is useless because the admin acts on it now, while a 30-day series recomputed per request is slow and no more correct. |
| **`settings/public/` is the one AllowAny route** | The app reads it before login. `is_public` is opt-in per row, so adding a setting never exposes it by accident. |
| **The admin user table is a plain `Serializer`** | `fields = "__all__"` on the user model would put the password hash and every security column on the wire. Listing what is exposed is the point. |

### Tests

67 administration tests. `serializers.py` 93%, `selectors.py` 92%,
`views.py` 86%, `services.py` 78%.

```
apps/administration/tests/test_administration.py
    every route refuses a photographer and a buyer (403, not a filtered view)
    approve / reject / more-info, each audited, each notified
    blocking: token_version bumped, bookings cancelled through the machine
    wallet adjustments write the ledger and cannot overdraw
    ACTIONED hides the review AND removes it from the public average
    the audit log has no write path
    unknown and untypeable setting values refused
```

The uncovered lines in `services.py` are mostly the flag consequences for content
types the tests do not each construct (portfolio image, chat message redaction)
and the `except` arm that keeps one immovable booking from aborting a block.

---

## 16. What `./test.sh` now covers

150 checks against the running server, in 15 sections. The four new ones drive
whole flows rather than pinging endpoints:

* **§11 Reviews** — completes a real booking, refuses a bare 1★, posts the
  review, proves the photographer's headline count moved with it, replies as the
  photographer, then proves the review can no longer be edited and cannot be
  posted twice.
* **§12 Notifications** — finds the `REVIEW_RECEIVED` entry the review above
  produced, checks the badge arithmetic, marks read and un-marks it, and proves
  one user cannot delete another's.
* **§13 Chat** — opens a thread, proves opening twice returns the same one,
  proves a repeated `client_id` returns the same message, replays with `?after=`,
  and proves a stranger gets 404 on both read and write.
* **§14 Administration** — dashboard, every queue, the audit log's absent write
  path, a setting change that appears in the log, and 403 for a photographer and
  a buyer on every route.

Each section restores what it touched: the booking, the review, the rating, the
conversation, the notifications and the setting value all go back to how they
were found, which is what makes the script safe to run repeatedly against the
seeded database.

---

## 17. What is left

Nothing in §3 is stubbed. What remains is polish and hardening, none of it
blocking a demo:

| Item | Note |
|---|---|
| **Push provider** | The delivery bookkeeping is real and tested; the provider call is a log line. Needs FCM/Expo credentials, and `expo-notifications` is a native dependency that must be checked against the SDK 54 pin first. |
| **Seller product upload** | Still out of scope (§5). The moderation gate it needs now exists — `POST /admin/products/{id}/approve` — so this is a smaller job than it was. |
| **Email delivery** | `EMAIL_BACKEND` is the console backend. `NotificationDelivery` already models the EMAIL channel. |
| **`consumers.py` coverage** | The WebSocket path is hand-tested. Both transports write through the same service, so the rules are covered even where the socket is not. |
| **Per-user chat archiving** | Currently one column on the conversation, so it hides the thread for both sides. |
| **Spread seeded `BuyerInteraction` rows over history** | Would fill the discovery funnel in the demo. Deliberately not done — see §11's "known data limitation". |

## 18. Where things live

```
akasha/
├── start.sh / stop.sh / test.sh   run + verify (150 checks, 15 sections)
├── backend/
│   ├── pytest.ini · conftest.py   test config + shared fixtures
│   ├── config/settings/           base · dev · prod · test
│   ├── apps/core/sentiment.py     model inference; never raises, degrades to None
│   ├── manage.py backfill_analytics   rebuild rollups after a seed
│   ├── private_media/             product files — NEVER served by URL
│   └── apps/                      15 apps, uniform internal layout
│       └── <app>/                 models · selectors(read) · services(write)
│                                  · serializers · views · urls · tasks · tests
├── mobile/src/
│   ├── api/                       client (single-flight refresh) · config · queryKeys
│   ├── navigation/                Root · Auth · Buyer(stack+tabs) · Photographer(stack+tabs)
│   ├── features/<feature>/        screens · components · hooks
│   │                              (+ reviews · notifications · chat)
│   ├── components/                ui · feedback · layout
│   └── theme/                     colours from the original prototype
├── ml/
│   ├── data/raw/                  the 11 source CSVs
│   ├── pipelines/                 ingest · features · scorer · 3 trainers
│   └── artifacts/                 trained models + metrics.json
├── docs/
│   ├── 01-system-architecture.md  ADRs, NFRs, security, deployment
│   └── PROJECT-STATE.md           this file
└── prototype/                     original RN prototype (UI reference)
```

**Layering rule:** `views → serializers → services/selectors → models`, one
direction only. Writes in `services.py`, reads in `selectors.py`. No app
imports another app's `models.py` except for foreign-key declarations.
