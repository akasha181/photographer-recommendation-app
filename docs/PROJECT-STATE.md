# SnapSphere — Project State

**Last updated:** 31 July 2026
**Next task:** Module 9 — Reviews (write API), then Module 12 — Notifications API

Read this first when resuming. It records what exists, what was decided and
why, and exactly where to pick up.

---

## 1. How to start working

```bash
cd /Users/mac/Desktop/akasha
./start.sh          # MySQL + Redis + Django on :8000  (idempotent)
./test.sh           # 52-check API smoke test — should be ALL PASSED
cd mobile && npx expo start

# Unit tests (268, ~20s). --create-db after any migration.
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
| Backend (Django) | 237 | 21,190 |
| ML pipelines | 9 | 1,449 |
| Mobile (TypeScript) | 52 | 10,849 |
| Backend tests | 10 files | 268 tests |

**Database:** 77 tables · 445 users · 200 photographers · 52,199 bookings ·
51,822 reviews · 124 products · 362 product files · 496 generated cover
images · 40 funded wallets.

---

## 3. Module status

| # | Module | State |
|---|---|---|
| 1 | System architecture | ✅ Documented — `docs/01-system-architecture.md` |
| 2 | Database design | ✅ 46 domain tables, migrated, seeded |
| 3 | Authentication | ✅ Complete, verified end-to-end |
| 4 | **Buyer module** | ✅ **Complete — profile, wallet, top-ups, wishlist, purchases** |
| 5 | Photographer module | 🟡 Profile read+write, requests, seller view done; portfolio/product upload pending |
| 6 | Portfolio | 🟡 Models + read; upload pending |
| 7 | **Booking** | ✅ **Complete — state machine, API, calendar, screens** |
| 8 | **Digital marketplace** | ✅ **Buyer-side complete — browse, cart, wallet checkout, secure downloads** |
| 9 | Reviews & ratings | 🟡 **NEXT** — models + read done; write API pending |
| 10 | AI recommendation | ✅ Pipelines, 3 models, live engine, explanations |
| 11 | Search & filters | ✅ 12 filters, 6 sorts, distance |
| 12 | Notifications | 🟡 Models + `notify()` + consumer, fired by bookings; REST API pending |
| 13 | Chat | 🟡 Models + consumers; REST API pending |
| 14 | Admin | ⬜ Models only |
| 15 | Analytics | ⬜ Models + task stubs |
| 16 | API docs | ✅ Auto-generated at `/api/v1/docs/` |
| 17 | RN screens | 🟡 Auth · Home · Explore · Detail · Bookings · Shop · Profile — all five buyer tabs live |
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

## 10. NEXT: Module 9 — Reviews (write API)

Bookings produce `COMPLETED` rows with `is_reviewable` true and a `review`
entry already in `available_actions`; marketplace orders carry `has_review` on
each item. Both entry points are waiting.

### To build

1. **`apps/reviews/services.py`** — `create_review(booking, rating, …)`. Verify
   the booking is COMPLETED, belongs to this buyer, and has no review yet;
   then set `Booking.has_review` and call
   `profiles.services.refresh_photographer_rating()` in the same transaction.
2. **`apps/reviews/views.py`** — create + photographer reply.
3. **Product reviews** — `ProductReview` exists and `OrderItem.has_review` is
   already serialised to the app.
4. **Sentiment** — `apps/core/review_text.py` and the trained model are ready
   to classify the comment on save.
5. **Mobile** — review form from the booking detail screen's `review` action
   and from the Purchases library.

Then Module 12 (notifications REST API) — the bell has no list endpoint yet,
though bookings and marketplace sales are already writing to it.

---

## 11. Where things live

```
akasha/
├── start.sh / stop.sh / test.sh   run + verify (36 checks)
├── backend/
│   ├── pytest.ini · conftest.py   test config + shared fixtures
│   ├── config/settings/           base · dev · prod · test
│   ├── private_media/             product files — NEVER served by URL
│   └── apps/                      15 apps, uniform internal layout
│       └── <app>/                 models · selectors(read) · services(write)
│                                  · serializers · views · urls · tasks · tests
├── mobile/src/
│   ├── api/                       client (single-flight refresh) · config · queryKeys
│   ├── navigation/                Root · Auth · Buyer(stack+tabs) · Photographer(stack+tabs)
│   ├── features/<feature>/        screens · components · hooks
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
