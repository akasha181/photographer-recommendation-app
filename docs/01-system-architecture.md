# MODULE 1 — OVERALL SYSTEM ARCHITECTURE
### SnapSphere — Photographer Booking & Recommendation Platform

**Document version:** 1.0
**Author role:** Senior Software Architect
**Status:** Baseline — approved before Module 2 (Database Design)

---

## 0. GROUNDING — WHAT YOU ALREADY HAVE

Before designing anything, an architect audits the inputs. Here is everything in your folder and its role in the final system.

### 0.1 Asset inventory

| File | What it actually is | Verified facts | Role in final system |
|---|---|---|---|
| `final version.docx` | Your FYP proposal | 8 modules, offline payment scope, Recharts named for dashboards | **Contract.** Scope authority |
| `fyppppppppp.txt` | React Native prototype, 2,646 lines, app name **SnapSphere** | 40 components, dark+gold theme, mock Firebase layer, PKR pricing, Pakistani cities | **UI/UX baseline.** Module 17 refactors this into production structure |
| `photographer_profiles.csv` | 200 photographers | `Years_Experience` 1–15, `Avg_Rating` 2.51–5.00, `Reviews_Count` 6–499, `Bookings_Success_Rate` 0.60–1.00, `Response_Time` 1–48h, `Portfolio_Score` 19–999, `Price` 109–1992 | **Seed data + ranking model features** |
| `buyer_interactions.csv` | 500 interactions, 244 buyers × 186 photographers | Status: Cancelled 171 / Pending 168 / Booked 161 | **Collaborative-filtering interaction matrix** |
| `reviews_feedback.csv` | 300 reviews | ⚠ Only **5 distinct texts**; labels are noise (see 0.3) | **Discard labels.** Text templates only |
| `yelp.csv` | 44,610 real reviews, cols: `business_id, stars, text, useful, cool, funny` | Real English review prose with 1–5 star labels | **Sentiment model training corpus + realistic review seeding** |
| `seasonal_demand.csv` | 12 months × 5 event types | `Avg_Bookings`, `Avg_Price`, `Demand_Score` | **Seasonal boost feature + admin forecast chart** |
| `data.csv` | 1,000 implicit-feedback rows | `click_count, view_time_sec, scroll_depth, add_to_cart, purchase, position` | **Marketplace product recommender + learning-to-rank** |
| `service_engagement_dataset.csv` | 500 daily rows/photographer | funnel: visibility → views → clicks → bookings | **Photographer analytics dashboard** |
| `service_revenue_dataset.csv` | 500 rows | same schema + revenue emphasis | **Revenue forecasting** |
| `service_general_dataset.csv` | 500 rows | duplicate schema, different scale | Merge into engagement table |
| `service_monitoring.csv` | 400 rows | **no `Portfolio_Interactions` column** | Normalize on ingest |
| `service_monitoring_dataset.csv` | 300 rows | full schema, numeric IDs | Merge |

### 0.2 The five canonical categories

Every dataset agrees on exactly five event types. **This is your category taxonomy — do not invent others.**

```
Wedding (44)   Corporate (42)   Fashion (39)   Birthday (38)   Graduation (37)
```

Your prototype uses different tags (`Portrait`, `Nature`, `Travel`, `Architecture`, `Newborn`). **Decision:** the five above become `Category` (top-level, ML-relevant). Prototype tags become `Specialization` (free-form, display-only, many-to-many). Both are stored; only `Category` feeds the model.

### 0.3 ⚠ Data quality findings you must know now

**Finding 1 — `reviews_feedback.csv` sentiment labels are randomly assigned.**

```
Row 2: "Amazing service and very professional."  → labelled Negative   ❌
Row 1: "Average experience, could improve."      → labelled Negative   (plausible)
```
Only 5 unique review texts exist across 300 rows. A model trained on this learns nothing (it would score ~33% — pure chance across 3 classes).

**Mitigation:** train the sentiment model on `yelp.csv` (44,610 real reviews, stars → sentiment: 1–2★ = Negative, 3★ = Neutral, 4–5★ = Positive). Use `reviews_feedback.csv` only as text templates for seeding demo data. Full treatment in Module 10.

**Finding 2 — `Response_Time` is in hours, mean 26.35h.** Low is good. Must be **inverted** before feeding any ranking model, else the model rewards slow photographers.

**Finding 3 — `Portfolio_Score` (19–999) and `Price` (109–1992) are on wildly different scales** from `Avg_Rating` (2.51–5.00). Mandatory `StandardScaler` in the ML pipeline. Details in Module 10.

**Finding 4 — Dataset prices (109–1992) are USD-scale; your prototype prices (6,000–12,000) are PKR.** Decision: **PKR is the platform currency.** Seed script multiplies dataset prices by 100 and rounds to nearest 500.

### 0.4 Scope conflicts I am resolving now

| Conflict | Resolution | Why |
|---|---|---|
| Proposal says *"Excludes: full online payment integration"* — but your feature list requires *"Buy digital products / Download purchased products"* | **Hybrid.** Bookings = offline payment (cash/bank transfer + admin verification). Digital products = **Wallet + manual top-up**: buyer uploads bank-transfer receipt → admin credits wallet → wallet purchases are instant and auto-unlock downloads | Keeps proposal scope honest, still gives a working end-to-end marketplace with instant download. Real gateway = documented future enhancement |
| Proposal names **Recharts** — a *web* library that does not run in React Native | **Two clients.** Mobile app uses `react-native-gifted-charts`. **Admin gets a separate React web dashboard using Recharts** | Matches proposal literally, and admin analytics genuinely need a big screen |
| Proposal has a **Location-Based Matching module**; your feature list only says "Distance filter" | Folded into Search & Filter (Module 11) as first-class: lat/lng on every profile + Haversine bounding-box query + map screen | Nothing from the proposal is dropped |
| Proposal says backend "Django/Flask" | **Django REST Framework**, per your stated stack | DRF gives auth, permissions, serialization, admin, ORM out of the box |

---

## 1. PRODUCT DEFINITION

| Attribute | Value |
|---|---|
| **Product name** | SnapSphere |
| **One-liner** | A mobile marketplace where buyers discover, compare and book professional photographers, guided by an AI recommendation engine |
| **Primary market** | Pakistan (Islamabad, Lahore, Karachi, Rawalpindi, Faisalabad, Multan, Peshawar) |
| **Currency** | PKR (`Rs`) |
| **Clients** | React Native mobile app (Buyer + Photographer) · React web dashboard (Admin) |
| **Roles** | Buyer · Photographer · Admin |
| **Revenue model** | Platform commission on bookings + commission on digital product sales |
| **Payments** | Offline (bookings) · Wallet with admin-verified top-up (digital products) |

---

## 2. ARCHITECTURE DECISION RECORDS (ADR)

An ADR records *what* we chose, *why*, and *what we gave up*. Your evaluators will ask these exact questions.

### ADR-001 — Modular Monolith, not Microservices

**Decision:** One Django project containing 15 well-bounded apps, deployed as a single unit.

| | Modular Monolith ✅ | Microservices ❌ |
|---|---|---|
| Team size needed | 1–4 | 8+ |
| Deploy complexity | 1 pipeline | 15 pipelines, service mesh |
| Cross-module transaction | Single ACID `transaction.atomic()` | Saga pattern + compensating actions |
| Local dev | `python manage.py runserver` | Docker Compose with 15 containers |
| Debug a booking bug | One stack trace | Distributed tracing across 4 services |
| FYP demo risk | Low | High |

**Consequence:** module boundaries must be enforced by *discipline*, not by network calls. Rule: **apps communicate through `services.py` functions, never by importing another app's `models.py` directly** (except for `ForeignKey` declarations). This keeps the option of extracting a service later.

**Rejected because:** microservices solve organisational scaling problems you do not have, at a cost you cannot pay in one semester.

### ADR-002 — ASGI (Daphne), not WSGI (Gunicorn)

**Decision:** Serve the whole application over ASGI.

**Why:** the chat module requires WebSockets. WSGI cannot hold a persistent connection. Django Channels needs ASGI. Running WSGI for HTTP plus a separate ASGI process for WebSockets means two deployments and duplicated settings. One ASGI server handles both protocols.

**Trade-off:** ASGI is marginally slower for pure sync views. Irrelevant at FYP scale (< 500 concurrent users).

### ADR-003 — AI runs in-process, training runs in Celery

**Decision:** Do **not** build a separate FastAPI ML microservice.

```
Training  →  Celery worker  →  fits model  →  writes joblib artifact to /ml/artifacts/
Inference →  Django process →  loads artifact once at startup  →  scores in RAM
```

**Why:** inference on 200 photographers is a NumPy matrix operation taking < 5 ms. An HTTP hop to another service would cost 20–50 ms — the network call would be **10× slower than the prediction itself**. Training is slow and bursty, so it belongs in a background worker, not a web request.

**Trade-off:** scaling Django and the ML model independently is impossible. Acceptable — you have one model and one app server.

**Migration path (document this):** `recommendations/engine.py` exposes a single `recommend(buyer_id, filters) -> list[ScoredPhotographer]`. Swapping its body for an HTTP call to a FastAPI service later touches exactly one file.

### ADR-004 — MySQL FULLTEXT, not Elasticsearch

**Decision:** search via MySQL 8 `FULLTEXT` indexes + composite B-tree indexes.

**Why:** Elasticsearch adds a 1GB+ JVM service, an index-sync problem, and a whole consistency model — to search 200 rows. MySQL FULLTEXT with `MATCH...AGAINST` and a `ft_min_word_len=3` config handles this in single-digit milliseconds.

**Threshold for revisiting:** > 100,000 photographers, or a requirement for typo-tolerant fuzzy search.

### ADR-005 — JWT (stateless) with rotating refresh tokens + blacklist

**Decision:** `djangorestframework-simplejwt` with rotation and blacklisting enabled.

**Why:** mobile clients have no cookie jar and no CSRF story. JWT is the standard mobile answer. Rotation + blacklist recovers the "log out everywhere / revoke a stolen token" capability that pure stateless JWT lacks. Full design in §11 and Module 3.

### ADR-006 — Redis serves three roles

| Role | Why Redis |
|---|---|
| Celery broker | Standard, zero extra infra |
| Channels layer (WebSocket pub/sub) | Required for multi-worker chat fan-out |
| Cache (recommendations, analytics, hot profiles) | Sub-ms reads, TTL semantics built in |

One Redis instance, three logical databases (`/0` cache, `/1` celery, `/2` channels).

---

## 3. HIGH-LEVEL SYSTEM ARCHITECTURE

```
╔════════════════════════════════════════════════════════════════════════════╗
║                            CLIENT TIER                                     ║
╠═══════════════════════════╦═══════════════════╦════════════════════════════╣
║  React Native (Expo)      ║  React Native     ║  React + Vite (Web)        ║
║  ── BUYER APP ──          ║  ── PHOTOGRAPHER ─║  ── ADMIN DASHBOARD ──     ║
║  Explore · Search         ║  Portfolio Mgr    ║  User Mgmt · Approvals     ║
║  Booking · Wishlist       ║  Services/Pricing ║  Booking Oversight         ║
║  Marketplace · Chat       ║  Calendar         ║  Reports · Recharts        ║
║  Reviews · Notifications  ║  Earnings/Analytics║ Categories · Moderation   ║
╚═══════════╦═══════════════╩═════════╦═════════╩═══════════╦════════════════╝
            │ HTTPS/JSON              │ WSS                 │ HTTPS/JSON
            │ Bearer <access_jwt>     │ ?token=<jwt>        │
            ▼                         ▼                     ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                     NGINX  —  reverse proxy / TLS termination              │
│   · /api/*  → ASGI upstream      · /ws/*  → ASGI upstream (Upgrade)        │
│   · /media/* → static file serve (X-Accel-Redirect for protected files)    │
│   · rate limiting · gzip · security headers                                │
└──────────────────────────────┬─────────────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────────────┐
│              DAPHNE (ASGI)  ·  Django 5.x + DRF 3.15 + Channels 4          │
│                                                                            │
│  ┌── MIDDLEWARE PIPELINE (order matters) ───────────────────────────────┐  │
│  │ Security → CORS → Session → Auth → JWT → RequestID → AuditLog        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌── PRESENTATION  (views.py / consumers.py) ──────────────────────────┐   │
│  │ ViewSets · Routers · Permission classes · Throttle scopes            │   │
│  └──────────────────────────────────────────────────────────────────────┘  │
│  ┌── VALIDATION  (serializers.py) ──────────────────────────────────────┐  │
│  │ Field validation · cross-field rules · shaping input & output        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│  ┌── BUSINESS LOGIC  (services.py — WRITE  |  selectors.py — READ) ─────┐  │
│  │ Booking state machine · wallet debits · commission · ratings         │  │
│  │  ↑ THE ONLY LAYER ALLOWED TO CHANGE STATE ↑                          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│  ┌── DOMAIN  (models.py / managers.py) ─────────────────────────────────┐  │
│  │ ORM entities · custom QuerySets · constraints · invariants           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└───┬────────────────┬────────────────┬───────────────┬─────────────────┬────┘
    │                │                │               │                 │
    ▼                ▼                ▼               ▼                 ▼
┌─────────┐  ┌──────────────┐  ┌────────────┐  ┌───────────┐  ┌──────────────┐
│ MySQL 8 │  │    REDIS     │  │  CELERY    │  │   MEDIA   │  │  ML RUNTIME  │
│         │  │ /0 cache     │  │  WORKERS   │  │  STORAGE  │  │  (in-proc)   │
│ InnoDB  │  │ /1 broker    │  │            │  │           │  │              │
│ utf8mb4 │  │ /2 channels  │  │ · email    │  │ dev: FS   │  │ joblib load  │
│ FULLTEXT│  │              │  │ · push     │  │ prod: S3  │  │ scikit-learn │
│ 30+ tbl │  │ TTL caches   │  │ · thumbs   │  │ + presign │  │ 5ms scoring  │
└─────────┘  └──────────────┘  │ · retrain  │  └───────────┘  └──────────────┘
                               │ · expiry   │         ▲               ▲
                               │ · digests  │         │               │
                               └──────┬─────┘         │        ┌──────┴──────┐
                                      │               │        │ /ml/artifacts│
                               ┌──────▼──────┐        │        │ ranker.joblib│
                               │ CELERY BEAT │────────┘        │ cf_matrix.npz│
                               │  scheduler  │  nightly retrain│ scaler.joblib│
                               └─────────────┘                 └──────────────┘
```

### 3.1 Why each layer exists (beginner explanation)

| Layer | Plain-English job | Analogy |
|---|---|---|
| **Nginx** | Front door. Handles HTTPS, blocks floods, serves images fast | Building reception |
| **Middleware** | Every request passes through here first | Security checkpoint |
| **Views** | Decide *who* may do *what*, then delegate | Manager who routes work |
| **Serializers** | Check input is valid, format output | Form validator |
| **Services** | The actual rules ("a booking can only be accepted if pending") | The rulebook |
| **Selectors** | Efficient reads, no state change | Librarian |
| **Models** | Table definitions and their guarantees | Filing cabinet |
| **Celery** | Slow work moved off the request path | Back office |
| **Redis** | Fast temporary memory | Sticky notes on the desk |
| **ML runtime** | Predicts who you'd like | In-house analyst |

### 3.2 The layering rule (memorise this)

```
views.py      →  MAY call serializers, services, selectors
serializers.py→  MAY call selectors            ✗ NEVER services (no writes in validation)
services.py   →  MAY call models, other apps' services, tasks
selectors.py  →  MAY call models (read-only)   ✗ NEVER writes
models.py     →  MAY call nothing above it     ✗ NEVER views/serializers
```

A single violation of this rule is where 90% of "why is my Django project unmaintainable" comes from.

---

## 4. TECHNOLOGY STACK

### 4.1 Backend

| Package | Version | Purpose | Why this one |
|---|---|---|---|
| Python | 3.11+ | Runtime | 25% faster than 3.10; scikit-learn 1.5 compatible |
| Django | 5.0 LTS | Framework | ORM, migrations, admin, auth |
| djangorestframework | 3.15 | REST layer | Serializers, ViewSets, permissions |
| djangorestframework-simplejwt | 5.3 | JWT auth | Rotation + blacklist built in |
| channels | 4.1 | WebSockets | Official Django async |
| channels-redis | 4.2 | Channel layer | Multi-worker WS fan-out |
| daphne | 4.1 | ASGI server | Channels' reference server |
| celery | 5.4 | Task queue | Industry standard |
| django-celery-beat | 2.6 | Cron in DB | Editable schedules via admin |
| mysqlclient | 2.2 | DB driver | Fastest MySQL driver (C ext) |
| django-filter | 24.2 | Query filters | Declarative filtering |
| django-cors-headers | 4.4 | CORS | Needed by admin web client |
| Pillow | 10.3 | Images | Thumbnails, EXIF strip |
| drf-spectacular | 0.27 | OpenAPI 3 | Auto Swagger — Module 16 |
| django-storages + boto3 | 1.14 | S3 media | Production media |
| python-decouple | 3.8 | Env config | 12-factor secrets |
| scikit-learn | 1.5 | ML | Ranking + CF + sentiment |
| pandas / numpy | 2.2 / 1.26 | Data | Feature engineering |
| scipy | 1.13 | Sparse matrices | CF interaction matrix |
| joblib | 1.4 | Model persistence | Artifact save/load |
| pytest + pytest-django | 8.x | Testing | Better fixtures than unittest |
| factory-boy + Faker | 3.3 | Test data | Realistic fixtures |
| sentry-sdk | 2.x | Error tracking | Production observability |

### 4.2 Mobile (React Native)

| Package | Purpose | Why |
|---|---|---|
| Expo SDK 51 | Toolchain | No Xcode/Android Studio needed for FYP demo |
| TypeScript 5.x | Types | Catches API-shape bugs at compile time |
| @react-navigation/native v6 | Navigation | Stack + Tabs + role-based navigators |
| @tanstack/react-query v5 | Server state | Caching, retries, background refetch, infinite scroll |
| zustand | Client state | 1KB; auth/cart/theme only |
| axios | HTTP | Interceptors for token refresh |
| react-hook-form + zod | Forms | Schema validation mirroring backend rules |
| expo-secure-store | Token storage | Keychain/Keystore — **never AsyncStorage for tokens** |
| expo-image | Images | Disk caching, blurhash placeholders |
| expo-image-picker | Uploads | Portfolio & chat images |
| expo-notifications | Push | FCM/APNs |
| expo-file-system | Downloads | Digital product delivery |
| react-native-gifted-charts | Charts | Photographer analytics |
| react-native-calendars | Calendar | Availability picker |
| react-native-maps | Maps | Location matching |
| react-native-reanimated v3 | Animation | 60fps on UI thread |

**Explicit non-goal:** the mobile app does **not** talk to Firebase in production. Your prototype's `FB` mock object is replaced by Django Channels WebSockets. One backend, one source of truth.

### 4.3 Admin web dashboard

| Package | Purpose |
|---|---|
| React 18 + Vite 5 | SPA + fast HMR |
| TypeScript | Types |
| **Recharts 2.x** | Charts — *as named in your proposal* |
| TanStack Query + Table | Data fetching + sortable/paginated tables |
| React Router v6 | Routing |
| Tailwind CSS | Styling |

---

## 5. DJANGO APP DECOMPOSITION

15 apps. Each owns its tables and exposes behaviour through `services.py`.

| # | App | Responsibility | Core models | Depends on | Module |
|---|---|---|---|---|---|
| 1 | `core` | Shared base classes, pagination, exception handler, permissions, mixins | `TimeStampedModel`, `SoftDeleteModel` | — | 1 |
| 2 | `accounts` | Identity, JWT, roles, OTP, password reset, devices | `User`, `OTPCode`, `PasswordReset`, `Device` | core | 3 |
| 3 | `profiles` | Buyer & photographer profiles, verification, wallet | `BuyerProfile`, `PhotographerProfile`, `Wallet`, `WalletTxn` | accounts | 4, 5 |
| 4 | `catalog` | Categories, specializations, services, packages | `Category`, `Specialization`, `Service`, `ServicePackage` | profiles | 5 |
| 5 | `portfolio` | Images, videos, albums, featured works | `PortfolioAlbum`, `PortfolioImage`, `PortfolioVideo` | profiles, catalog | 6 |
| 6 | `availability` | Calendar, blackout dates, slot locking | `AvailabilityRule`, `BlackoutDate`, `TimeSlot` | profiles | 7 |
| 7 | `bookings` | Booking state machine, cancellation, offline payment | `Booking`, `BookingStatusHistory`, `BookingPayment` | all above | 7 |
| 8 | `marketplace` | Digital products, orders, licenced downloads | `DigitalProduct`, `ProductFile`, `Order`, `OrderItem`, `DownloadToken` | profiles, catalog | 8 |
| 9 | `reviews` | Ratings, replies, review images, aggregates | `Review`, `ReviewImage`, `ReviewReply`, `ProductReview` | bookings, marketplace | 9 |
| 10 | `wishlist` | Saved photographers & products | `WishlistItem` | profiles, marketplace | 4 |
| 11 | `chat` | Conversations, messages, receipts, presence | `Conversation`, `Message`, `MessageAttachment`, `Presence` | accounts | 13 |
| 12 | `notifications` | In-app + push notifications, preferences | `Notification`, `NotificationPreference`, `PushToken` | accounts | 12 |
| 13 | `recommendations` | Feature store, model artifacts, scoring, events | `RecommendationEvent`, `PhotographerFeature`, `ModelVersion` | all | 10 |
| 14 | `analytics` | Daily rollups, dashboards, reports | `DailyPhotographerStat`, `PlatformStat`, `RevenueSnapshot` | all | 15 |
| 15 | `administration` | Approvals, moderation, bans, audit log, settings | `ApprovalRequest`, `ModerationFlag`, `AuditLog`, `PlatformSetting` | all | 14 |

### 5.1 Dependency graph (must stay acyclic)

```
                        ┌────────┐
                        │  core  │  ← everything imports this
                        └───┬────┘
                            ▼
                       ┌─────────┐
                       │accounts │
                       └────┬────┘
              ┌─────────────┼───────────────┬──────────────┐
              ▼             ▼               ▼              ▼
        ┌──────────┐  ┌──────────┐   ┌───────────────┐ ┌──────┐
        │ profiles │  │   chat   │   │ notifications │ │admin.│
        └────┬─────┘  └──────────┘   └───────────────┘ └──────┘
             ▼
      ┌────────────┐
      │  catalog   │
      └──┬──────┬──┘
         ▼      ▼
  ┌──────────┐ ┌──────────────┐
  │portfolio │ │ availability │
  └──────────┘ └──────┬───────┘
                      ▼
               ┌────────────┐      ┌──────────────┐
               │  bookings  │      │ marketplace  │
               └──────┬─────┘      └──────┬───────┘
                      └────────┬──────────┘
                               ▼
                         ┌──────────┐
                         │ reviews  │
                         └────┬─────┘
                              ▼
                  ┌───────────────────────┐
                  │ recommendations       │
                  │ analytics             │  ← read from everything
                  └───────────────────────┘
```

**Rule:** arrows point one way only. If `bookings` ever needs to import from `recommendations`, you have a design error — emit an event instead.

---

## 6. CROSS-CUTTING CONCERNS (decide once, apply everywhere)

### 6.1 Uniform API response envelope

Every response — success or failure — has the same top-level shape. The mobile app then needs exactly one response handler.

**Success:**
```json
{
  "success": true,
  "message": "Booking created successfully",
  "data": { "id": 1042, "status": "PENDING" },
  "meta": { "request_id": "req_8f3a2b1c" }
}
```

**Paginated success:**
```json
{
  "success": true,
  "message": "Photographers retrieved",
  "data": [ { "id": 12, "display_name": "Zara Malik" } ],
  "meta": {
    "pagination": {
      "page": 1, "page_size": 20, "total_pages": 10,
      "total_items": 200, "has_next": true, "has_previous": false
    },
    "request_id": "req_8f3a2b1c"
  }
}
```

**Error:**
```json
{
  "success": false,
  "message": "Validation failed",
  "error": {
    "code": "VALIDATION_ERROR",
    "details": {
      "event_date": ["Booking date must be in the future."],
      "guest_count": ["Ensure this value is less than or equal to 5000."]
    }
  },
  "meta": { "request_id": "req_8f3a2b1c" }
}
```

Implemented once in `core/exceptions.py` (custom `EXCEPTION_HANDLER`) and `core/renderers.py`.

### 6.2 Canonical error codes

| HTTP | `error.code` | Meaning |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Field-level validation failed |
| 400 | `BUSINESS_RULE_VIOLATION` | Valid input, illegal action (e.g. accept a cancelled booking) |
| 401 | `AUTHENTICATION_FAILED` | Missing/invalid credentials |
| 401 | `TOKEN_EXPIRED` | Access token expired → client refreshes |
| 401 | `TOKEN_INVALID` | Blacklisted/malformed → force logout |
| 403 | `PERMISSION_DENIED` | Authenticated but wrong role |
| 403 | `ACCOUNT_BLOCKED` | Admin ban |
| 403 | `ACCOUNT_NOT_APPROVED` | Photographer pending approval |
| 403 | `EMAIL_NOT_VERIFIED` | Verification required |
| 404 | `NOT_FOUND` | Resource missing or not visible to caller |
| 409 | `CONFLICT` | Double booking, duplicate review |
| 413 | `FILE_TOO_LARGE` | Upload over limit |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Bad file type |
| 422 | `INSUFFICIENT_BALANCE` | Wallet too low |
| 429 | `RATE_LIMIT_EXCEEDED` | Throttled |
| 500 | `INTERNAL_ERROR` | Unhandled — logged to Sentry, never leaks a stack trace |
| 503 | `SERVICE_UNAVAILABLE` | Maintenance mode |

### 6.3 Concern → decision table

| Concern | Decision |
|---|---|
| **API versioning** | URL path: `/api/v1/...`. Breaking change ⇒ `/api/v2/`, v1 supported 6 months |
| **Pagination** | Page-number default (`?page=&page_size=`), max 100. **Cursor pagination for chat & notifications** (stable under inserts) |
| **Filtering** | `django-filter` FilterSets. Never build raw querystring parsing by hand |
| **Sorting** | `?ordering=-created_at`, whitelisted fields only (prevents ORDER BY on unindexed columns) |
| **Throttling** | anon 60/min · user 300/min · login 5/min · register 3/hr · OTP 3/hr · chat-send 30/min · search 60/min |
| **Timezone** | Store **UTC** in DB (`USE_TZ=True`). Serialize ISO-8601 with offset. Client renders in `Asia/Karachi` |
| **Money** | `DECIMAL(12,2)` — **never `FLOAT`**. Serialized as string `"8500.00"` to dodge JS float errors |
| **Soft delete** | `is_deleted` + `deleted_at` on User, Booking, Review, Product. Managers exclude by default |
| **Idempotency** | `Idempotency-Key` header on POST /bookings and POST /orders; key+user cached 24h in Redis |
| **Request tracing** | Middleware assigns `X-Request-ID`, echoed in every response `meta` and every log line |
| **File uploads** | Images ≤ 5MB (jpg/png/webp) · Videos ≤ 100MB (mp4/mov) · Product files ≤ 500MB (zip). Magic-byte check, not extension |
| **Private files** | Product downloads never served directly — signed token URL, 15-min TTL, `X-Accel-Redirect` |
| **Logging** | JSON structured logs: `timestamp, level, request_id, user_id, event, duration_ms` |
| **N+1 prevention** | Every list endpoint must use `select_related` / `prefetch_related`; `django-debug-toolbar` in dev asserts query count |
| **DB transactions** | `ATOMIC_REQUESTS = False`; explicit `transaction.atomic()` inside service functions only |

---

## 7. CANONICAL FLOW 1 — BUYER BOOKS A PHOTOGRAPHER (sequence diagram)

```
Buyer     RN App      Nginx    DRF View   Serializer  BookingSvc  MySQL   Celery  Channels  Photog
  │          │          │          │          │           │         │       │        │        │
  │ tap Book │          │          │          │           │         │       │        │        │
  ├─────────►│          │          │          │           │         │       │        │        │
  │          │ POST /api/v1/bookings/                     │         │       │        │        │
  │          │ Bearer <jwt> + Idempotency-Key             │         │       │        │        │
  │          ├─────────►│          │          │           │         │       │        │        │
  │          │          │ proxy    │          │           │         │       │        │        │
  │          │          ├─────────►│          │           │         │       │        │        │
  │          │          │          │ authenticate JWT     │         │       │        │        │
  │          │          │          │ IsBuyer permission   │         │       │        │        │
  │          │          │          ├─────────►│           │         │       │        │        │
  │          │          │          │          │ field validation    │       │        │        │
  │          │          │          │          │ · date > now+24h    │       │        │        │
  │          │          │          │          │ · service active    │       │        │        │
  │          │          │          │          │ · photog approved   │       │        │        │
  │          │          │          │◄─────────┤ validated_data      │       │        │        │
  │          │          │          ├─────────────────────►│         │       │        │        │
  │          │          │          │      create_booking()│         │       │        │        │
  │          │          │          │          │           │ BEGIN TRANSACTION       │        │
  │          │          │          │          │           ├────────►│       │        │        │
  │          │          │          │          │           │ SELECT ... FOR UPDATE   │        │
  │          │          │          │          │           │ (lock photographer row) │        │
  │          │          │          │          │           ├────────►│       │        │        │
  │          │          │          │          │           │ check slot free         │        │
  │          │          │          │          │           │ check no overlap        │        │
  │          │          │          │          │           │ check not blackout      │        │
  │          │          │          │          │           │ compute total_price     │        │
  │          │          │          │          │           │ INSERT Booking(PENDING) │        │
  │          │          │          │          │           ├────────►│       │        │        │
  │          │          │          │          │           │ INSERT StatusHistory    │        │
  │          │          │          │          │           ├────────►│       │        │        │
  │          │          │          │          │           │ COMMIT  │       │        │        │
  │          │          │          │          │           ├────────►│       │        │        │
  │          │          │          │          │           │ enqueue notify + expiry │        │
  │          │          │          │          │           ├─────────────────►│       │        │
  │          │          │          │◄─────────────────────┤ Booking │       │        │        │
  │          │          │◄─────────┤ 201 Created          │         │       │        │        │
  │          │◄─────────┤          │          │           │         │       │        │        │
  │◄─────────┤ confirmation screen │          │           │         │       │        │        │
  │          │          │          │          │           │         │       │ push notif      │
  │          │          │          │          │           │         │       ├───────►│        │
  │          │          │          │          │           │         │       │        ├───────►│
  │          │          │          │          │           │         │       │        │ "New   │
  │          │          │          │          │           │         │       │        │ request"│
  │          │          │          │          │           │         │       │        │        │
  │  ═══ 48h later, if still PENDING ═══                  │         │       │        │        │
  │          │          │          │          │           │  Celery Beat fires expire_bookings│
  │          │          │          │          │           │◄────────────────┤       │        │
  │          │          │          │          │           │ PENDING → EXPIRED       │        │
  │          │          │          │          │           ├────────►│       │        │        │
```

### 7.1 Why `SELECT ... FOR UPDATE` matters

Two buyers tap "Book" on the same slot at the same instant:

```
WITHOUT row lock:                      WITH row lock (FOR UPDATE):
T1: check slot free → free             T1: LOCK row → check → free → INSERT → COMMIT (lock released)
T2: check slot free → free             T2: LOCK row (BLOCKS until T1 commits)
T1: INSERT booking                     T2: → check → TAKEN → 409 CONFLICT ✅
T2: INSERT booking                     
Result: DOUBLE BOOKING ❌
```

Backed up by a DB-level `UniqueConstraint(photographer, event_date, start_time, condition=Q(status__in=['PENDING','ACCEPTED']))` — belt *and* braces.

---

## 8. CANONICAL FLOW 2 — AI RECOMMENDATION SERVING

```
┌─ OFFLINE (Celery Beat, nightly 02:00 Asia/Karachi) ───────────────────────┐
│                                                                            │
│  MySQL ──► extract ──► pandas DataFrame ──► feature engineering            │
│  (bookings, reviews, interactions, profiles, seasonal)                     │
│                              │                                             │
│                              ▼                                             │
│              ┌───────────────────────────────────┐                         │
│              │ TRAIN 3 MODELS                    │                         │
│              │ 1. Content ranker (GBR/RF)        │                         │
│              │ 2. Collaborative filter (item-item│                         │
│              │    cosine on interaction matrix)  │                         │
│              │ 3. Sentiment (TF-IDF + LogReg,    │                         │
│              │    trained on yelp.csv)           │                         │
│              └───────────────┬───────────────────┘                         │
│                              ▼                                             │
│         evaluate → if RMSE/Precision@10 not worse than live → promote      │
│                              ▼                                             │
│         /ml/artifacts/v{n}/{ranker,cf,scaler,vectorizer}.joblib            │
│         + ModelVersion row (is_active=True)                                │
└────────────────────────────────────────────────────────────────────────────┘
                              │  loaded once at Django startup (AppConfig.ready)
                              ▼
┌─ ONLINE (per request, target p95 < 150 ms) ───────────────────────────────┐
│                                                                            │
│  GET /api/v1/recommendations/?category=Wedding&city=Lahore&budget=15000    │
│              │                                                             │
│              ├─► Redis cache key: rec:{user}:{filters_hash}  ── HIT ──► ✅ │
│              │                                                  (TTL 30m)  │
│              ▼ MISS                                                        │
│  1. CANDIDATE GENERATION  (SQL, indexed)                                   │
│     WHERE is_approved AND is_active AND city=? AND base_price<=?           │
│     AND category=? AND available_on(date)          → ~40 candidates        │
│                              ▼                                             │
│  2. FEATURE LOOKUP  (PhotographerFeature table, pre-computed nightly)      │
│     rating · reviews · success_rate · 1/response_time · portfolio ·        │
│     price_fit · experience · popularity · seasonal_boost · distance_km     │
│                              ▼                                             │
│  3. CONTENT SCORE      ranker.predict(X_scaled)          → 0..1            │
│  4. COLLAB SCORE       cf_matrix[buyer] · candidates     → 0..1            │
│     (skipped if buyer has < 3 interactions → cold start)                   │
│  5. BUSINESS RULES     +new-photographer floor, −recent-cancellation       │
│                              ▼                                             │
│  6. HYBRID BLEND                                                           │
│     final = 0.55·content + 0.30·collab + 0.15·business                     │
│     (weights are PlatformSetting rows — tunable without redeploy)          │
│                              ▼                                             │
│  7. RANK, take top-20, attach human-readable reason:                       │
│     "4.9★ · 214 reviews · specialises in Wedding · replies in 2h"          │
│                              ▼                                             │
│  8. Cache 30m  +  log RecommendationEvent (for offline CTR evaluation)     │
└────────────────────────────────────────────────────────────────────────────┘
```

**Cold-start handling (your proposal explicitly lists this as a limitation — here is the fix):**

| Situation | Strategy |
|---|---|
| New buyer, 0 interactions | Popularity ranking with **Bayesian-smoothed rating** (already in your prototype!): `(n/(n+m))·R + (m/(n+m))·C`, m=10, C=4.0 |
| New photographer, 0 bookings | Guaranteed **exploration slot**: 2 of the top 20 reserved for photographers < 30 days old with a complete portfolio. Prevents the rich-get-richer trap |
| Filters return < 5 results | Progressive relaxation: budget +20% → adjacent city → drop availability → notify user what was relaxed |

---

## 9. CANONICAL FLOW 3 — REAL-TIME CHAT

```
Buyer App                Daphne/Channels           Redis            Photographer App
    │                          │                     │                      │
    │ WS connect               │                     │                      │
    │ /ws/chat/<conv_id>/?token=<jwt>                │                      │
    ├─────────────────────────►│                     │                      │
    │                          │ 1 decode JWT        │                      │
    │                          │ 2 verify participant│                      │
    │                          │ 3 group_add         │                      │
    │                          ├────────────────────►│                      │
    │                          │ 4 set presence ONLINE (TTL 60s)            │
    │                          ├────────────────────►│                      │
    │◄─────────────────────────┤ accept + unread count                      │
    │                          │                     │                      │
    │ {"type":"typing"}        │                     │                      │
    ├─────────────────────────►│ group_send ────────►│──────────────────────►│
    │                          │                     │       typing dots ▪▪▪ │
    │ {"type":"message","body":"Are you free 12 Aug?"}                      │
    ├─────────────────────────►│                     │                      │
    │                          │ · rate-limit 30/min │                      │
    │                          │ · sanitise HTML     │                      │
    │                          │ · persist to MySQL  │                      │
    │                          │ · group_send ──────►│──────────────────────►│
    │◄─────────────────────────┤ ack {id, server_ts} │        message shown  │
    │                          │                     │                      │
    │                          │           if receiver offline:             │
    │                          │           Celery → FCM push                │
    │                          │                     │                      │
    │                          │◄─────────────────── {"type":"read","up_to":88}
    │◄─────────────────────────┤ read receipt ✓✓     │                      │
```

**Offline-message guarantee:** MySQL is the source of truth; WebSocket is only transport. On reconnect the client calls `GET /api/v1/chat/conversations/{id}/messages/?after=<last_id>` and never loses a message.

---

## 10. NON-FUNCTIONAL REQUIREMENTS

| # | Category | Requirement | Measurable target | How we achieve it |
|---|---|---|---|---|
| NFR-01 | Performance | API latency | p95 < 300ms, p99 < 800ms | Indexes, `select_related`, Redis |
| NFR-02 | Performance | Recommendations | p95 < 150ms | Pre-computed features + cache |
| NFR-03 | Performance | Search | p95 < 200ms on 200 rows | FULLTEXT + composite indexes |
| NFR-04 | Performance | App cold start | < 3s to first paint | Hermes engine, lazy screens |
| NFR-05 | Performance | Image load | < 1s on 3G | WebP thumbnails, 3 sizes, CDN |
| NFR-06 | Performance | Chat delivery | < 500ms end-to-end | WebSocket, no polling |
| NFR-07 | Scalability | Concurrent users | 500 without degradation | Stateless API, horizontal scale |
| NFR-08 | Scalability | Data volume | 100k bookings, 1M messages | Partition-ready schema, archival job |
| NFR-09 | Availability | Uptime | 99.5% (≈3.6h/month) | Health checks, auto-restart |
| NFR-10 | Reliability | Data durability | Zero committed-txn loss | Daily backup + binlog, 30-day retention |
| NFR-11 | Security | Passwords | Argon2, never plaintext | Django `PASSWORD_HASHERS` |
| NFR-12 | Security | Transport | TLS 1.2+ everywhere | Nginx + HSTS |
| NFR-13 | Security | Tokens | Access 30m / Refresh 14d rotating | SimpleJWT + blacklist |
| NFR-14 | Security | Injection | 0 SQLi/XSS | ORM only, DOMPurify, CSP |
| NFR-15 | Security | Files | Malicious upload blocked | Magic bytes, EXIF strip, size cap |
| NFR-16 | Usability | Key task depth | Booking in ≤ 5 taps | IA design, Module 17 |
| NFR-17 | Usability | Accessibility | WCAG AA contrast, 44pt targets | Theme tokens, a11y labels |
| NFR-18 | Usability | Offline | Graceful degradation | React Query cache + banner |
| NFR-19 | Maintainability | Test coverage | ≥ 70% overall, 100% on state machines | pytest + CI gate |
| NFR-20 | Maintainability | Docs | 100% endpoints in OpenAPI | drf-spectacular |
| NFR-21 | Portability | Platforms | Android 8+, iOS 13+ | Expo SDK 51 |
| NFR-22 | Compliance | Data rights | Export + delete account | Module 14 |
| NFR-23 | Observability | Traceability | Every request traceable | X-Request-ID, JSON logs |
| NFR-24 | Auditability | Admin actions | 100% logged, immutable | `AuditLog`, append-only |

---

## 11. SECURITY ARCHITECTURE

### 11.1 Defence in depth

```
Layer 1 TRANSPORT  TLS 1.2+ · HSTS 1yr · cert pinning (release build)
Layer 2 EDGE       Nginx rate limit · body size cap · security headers · block bad UA
Layer 3 AUTH       JWT verify · signature+exp+iss+aud · blacklist check
Layer 4 AUTHZ      Role permission → object ownership → state guard
Layer 5 INPUT      Serializer validation · magic-byte file check · HTML sanitisation
Layer 6 DOMAIN     Service-layer invariants · DB constraints (last line of defence)
Layer 7 DATA       Argon2 hashes · encrypted backups · PII minimisation
Layer 8 AUDIT      AuditLog · Sentry · anomaly alerts
```

### 11.2 JWT token design

| Property | Access token | Refresh token |
|---|---|---|
| Lifetime | 30 minutes | 14 days |
| Storage (mobile) | In-memory (zustand) | `expo-secure-store` (Keychain/Keystore) |
| Storage (admin web) | In-memory | httpOnly Secure SameSite=Strict cookie |
| Rotation | — | Yes: every refresh issues a new one, old one blacklisted |
| Revocation | Not individually (short life) | Blacklist table |
| Algorithm | HS256 (single service) | HS256 |

**Custom claims:** `user_id`, `role`, `is_approved`, `token_version`.
`token_version` increments on password change / admin ban — instantly invalidating **all** issued tokens without waiting for expiry.

**Refresh-reuse detection:** if a blacklisted refresh token is presented, the whole token family is revoked — that pattern means a token was stolen.

### 11.3 Role × capability matrix

`✅ full · 🟡 own records only · ❌ denied`

| Capability | Anonymous | Buyer | Photographer | Admin |
|---|---|---|---|---|
| Browse photographers | ✅ | ✅ | ✅ | ✅ |
| View portfolio | ✅ | ✅ | ✅ | ✅ |
| View reviews | ✅ | ✅ | ✅ | ✅ |
| Get recommendations | 🟡 popular only | ✅ personalised | ✅ | ✅ |
| Create booking | ❌ | ✅ | ❌ | ❌ |
| Accept/reject booking | ❌ | ❌ | 🟡 | ❌ |
| Cancel booking | ❌ | 🟡 | 🟡 | ✅ |
| Mark completed | ❌ | 🟡 confirm | 🟡 initiate | ✅ |
| Upload portfolio | ❌ | ❌ | 🟡 | ❌ |
| Create service | ❌ | ❌ | 🟡 | ❌ |
| Set availability | ❌ | ❌ | 🟡 | ❌ |
| Write review | ❌ | 🟡 completed bookings only | ❌ | ❌ |
| Reply to review | ❌ | ❌ | 🟡 | ❌ |
| Sell digital product | ❌ | ❌ | 🟡 | ❌ |
| Buy digital product | ❌ | ✅ | ✅ | ❌ |
| Download product | ❌ | 🟡 purchased only | 🟡 | ✅ |
| Chat | ❌ | 🟡 own convos | 🟡 own convos | ❌ |
| View own earnings | ❌ | ❌ | 🟡 | ✅ |
| Approve photographer | ❌ | ❌ | ❌ | ✅ |
| Block / delete user | ❌ | ❌ | ❌ | ✅ |
| Manage categories | ❌ | ❌ | ❌ | ✅ |
| Platform analytics | ❌ | ❌ | ❌ | ✅ |
| Broadcast notification | ❌ | ❌ | ❌ | ✅ |

### 11.4 Threat model (OWASP-aligned)

| Threat | Attack | Mitigation |
|---|---|---|
| Broken object-level authz | Buyer A opens `/bookings/999/` belonging to B | `IsOwner` object permission on **every** detail view; querysets always filtered by `request.user` |
| Privilege escalation | Client sends `"role":"ADMIN"` at registration | `role` is read-only in serializer; admins created only by CLI/admin panel |
| Mass assignment | Client sends `"is_approved":true` | Explicit `fields` list; never `fields = "__all__"` on writable serializers |
| Free product download | Guessing `/media/products/preset.zip` | Product files stored outside web root; signed 15-min token; ownership check |
| Review bombing | Fake reviews | One review per completed booking, DB-enforced unique |
| Booking spam | Script floods requests | Throttle + max 5 concurrent PENDING per buyer + idempotency key |
| Wallet manipulation | Race to double-spend | `SELECT FOR UPDATE` on wallet row inside atomic block |
| Chat data leak | Connect to another user's conversation | Participant check inside `connect()` before `accept()` |
| Stored XSS | `<script>` in bio/review | Sanitise on input, escape on output, CSP on admin web |
| Enumeration | Probing which emails exist | Identical response + timing for existing/non-existing email on login & reset |
| Brute force | Password spraying | 5/min throttle + 30-min lockout after 10 fails + optional CAPTCHA |
| Token theft | Stolen refresh token | Rotation + reuse detection + `token_version` kill switch |
| EXIF privacy leak | GPS in uploaded photo | Strip all EXIF on upload (Pillow) |

---

## 12. DEPLOYMENT TOPOLOGY

### 12.1 Development

```
Developer machine
├── Django dev server    :8000   (runserver / daphne)
├── MySQL 8              :3306   (Docker)
├── Redis 7              :6379   (Docker)
├── Celery worker        (terminal 2)
├── Celery beat          (terminal 3)
├── Expo dev server      :19000  → phone via Expo Go on same Wi-Fi
└── Vite admin dev       :5173
```

### 12.2 Production (single VPS — realistic and defensible for an FYP)

```
                            Internet
                               │  HTTPS :443
                               ▼
                    ┌──────────────────────┐
                    │  Nginx + Let's Encrypt│
                    └──────────┬────────────┘
        ┌──────────────────────┼──────────────────────┐
        │ /api/ /ws/           │ /admin-panel/        │ /media/
        ▼                      ▼                      ▼
┌───────────────┐    ┌──────────────────┐   ┌──────────────────┐
│ Daphne (ASGI) │    │ Admin SPA static │   │ Media / S3 + CDN │
│ systemd, 4 wk │    │ build artifacts  │   └──────────────────┘
└───────┬───────┘    └──────────────────┘
        ├──────────────┬──────────────┬───────────────┐
        ▼              ▼              ▼               ▼
   ┌─────────┐   ┌─────────┐   ┌───────────┐   ┌───────────┐
   │ MySQL 8 │   │ Redis 7 │   │  Celery   │   │Celery Beat│
   │ systemd │   │ systemd │   │  worker×2 │   │           │
   └────┬────┘   └─────────┘   └───────────┘   └───────────┘
        ▼
  Nightly mysqldump → off-site (30-day retention)
```

### 12.3 Scheduled jobs (Celery Beat)

| Task | Schedule | Purpose |
|---|---|---|
| `expire_pending_bookings` | every 15 min | PENDING older than 48h → EXPIRED |
| `auto_complete_bookings` | daily 03:00 | ACCEPTED + event date passed 72h → COMPLETED |
| `send_booking_reminders` | daily 09:00 | Notify both parties 24h before shoot |
| `rollup_daily_analytics` | daily 01:00 | Aggregate into `DailyPhotographerStat` |
| `retrain_models` | daily 02:00 | Retrain + evaluate + promote |
| `refresh_photographer_features` | daily 02:30 | Rebuild `PhotographerFeature` |
| `cleanup_expired_tokens` | daily 04:00 | Purge blacklist + download tokens |
| `cleanup_orphan_media` | weekly Sun 04:30 | Delete unreferenced files |
| `send_weekly_digest` | Mon 10:00 | Photographer performance email |
| `check_review_eligibility` | daily 11:00 | Nudge buyers to review |

---

## 13. FOLDER STRUCTURE

### 13.1 Repository root

```
snapsphere/
├── backend/            Django REST API
├── mobile/             React Native app
├── admin-web/          React admin dashboard
├── ml/                 Notebooks, training pipelines, artifacts
├── docs/               These module documents + diagrams
├── docker-compose.yml
└── README.md
```

### 13.2 Backend

```
backend/
├── manage.py
├── pytest.ini
├── .env.example
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── config/                          # project package (NOT an app)
│   ├── settings/
│   │   ├── base.py                  # shared settings
│   │   ├── dev.py                   # DEBUG=True, console email
│   │   ├── prod.py                  # DEBUG=False, S3, Sentry
│   │   └── test.py                  # sqlite/in-memory, eager celery
│   ├── urls.py                      # /api/v1/ include per app
│   ├── asgi.py                      # HTTP + WebSocket router
│   ├── wsgi.py
│   └── celery.py
├── apps/
│   ├── core/
│   │   ├── models.py                # TimeStampedModel, SoftDeleteModel
│   │   ├── pagination.py            # StandardPagination, CursorPagination
│   │   ├── exceptions.py            # custom_exception_handler
│   │   ├── renderers.py             # envelope renderer
│   │   ├── permissions.py           # IsBuyer, IsPhotographer, IsAdmin, IsOwner
│   │   ├── middleware.py            # RequestID, AuditLog
│   │   ├── validators.py            # file size/type, phone, future-date
│   │   ├── utils.py                 # image resize, EXIF strip, haversine
│   │   └── management/commands/seed_data.py
│   ├── accounts/
│   ├── profiles/
│   ├── catalog/
│   ├── portfolio/
│   ├── availability/
│   ├── bookings/
│   ├── marketplace/
│   ├── reviews/
│   ├── wishlist/
│   ├── chat/
│   ├── notifications/
│   ├── recommendations/
│   ├── analytics/
│   └── administration/
├── media/                           # dev only
└── staticfiles/
```

**Internal structure of every app (uniform — this consistency is the point):**

```
apps/bookings/
├── __init__.py
├── apps.py
├── constants.py            # BookingStatus choices, transition map
├── models.py               # Booking, BookingStatusHistory, BookingPayment
├── managers.py             # BookingQuerySet.for_buyer(), .active()
├── serializers.py          # Create/Detail/List/StatusUpdate serializers
├── selectors.py            # READ  — get_buyer_bookings(user, filters)
├── services.py             # WRITE — create_booking(), accept_booking()
├── permissions.py          # IsBookingParticipant
├── filters.py              # BookingFilterSet
├── views.py                # BookingViewSet
├── urls.py
├── tasks.py                # expire_pending_bookings, send_reminder
├── signals.py              # post-save → notification event
├── admin.py
├── migrations/
└── tests/
    ├── factories.py
    ├── test_models.py
    ├── test_services.py    # state machine — 100% coverage required
    ├── test_selectors.py
    └── test_api.py
```

### 13.3 Mobile app

```
mobile/
├── app.config.ts
├── tsconfig.json
├── .env
├── assets/{images,fonts,lottie}/
└── src/
    ├── api/
    │   ├── client.ts               # axios + auth interceptor + refresh queue
    │   ├── endpoints.ts            # single source of URL truth
    │   ├── queryKeys.ts            # React Query key factory
    │   └── services/
    │       ├── auth.api.ts
    │       ├── photographers.api.ts
    │       ├── bookings.api.ts
    │       ├── marketplace.api.ts
    │       ├── reviews.api.ts
    │       ├── chat.api.ts
    │       └── notifications.api.ts
    ├── navigation/
    │   ├── RootNavigator.tsx       # decides Auth vs Buyer vs Photographer
    │   ├── AuthNavigator.tsx
    │   ├── BuyerTabNavigator.tsx
    │   ├── PhotographerTabNavigator.tsx
    │   └── linking.ts              # deep links
    ├── features/
    │   ├── auth/{screens,components,hooks,schemas}/
    │   ├── explore/
    │   ├── photographer/
    │   ├── booking/
    │   ├── portfolio/
    │   ├── marketplace/
    │   ├── reviews/
    │   ├── chat/
    │   ├── wishlist/
    │   ├── notifications/
    │   ├── profile/
    │   └── dashboard/
    ├── components/                 # cross-feature UI
    │   ├── ui/{Button,Input,Card,Badge,Avatar,Stars,Modal,Sheet}.tsx
    │   ├── feedback/{Toast,EmptyState,ErrorState,Skeleton}.tsx
    │   └── layout/{Screen,Header,TabBar}.tsx
    ├── store/
    │   ├── authStore.ts
    │   ├── cartStore.ts
    │   └── uiStore.ts
    ├── hooks/{useAuth,useDebounce,useWebSocket,useUpload}.ts
    ├── theme/{colors.ts,spacing.ts,typography.ts,shadows.ts}
    ├── utils/{format.ts,date.ts,validation.ts,permissions.ts}
    └── types/{api.ts,models.ts,navigation.ts}
```

> `theme/colors.ts` is seeded directly from your prototype's `C` object — the dark `#080A0E` + gold `#D4A843` identity is kept.

### 13.4 ML workspace

```
ml/
├── data/
│   ├── raw/                        # your 10 CSVs, untouched
│   ├── interim/
│   └── processed/
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_feature_engineering.ipynb
│   ├── 03_ranking_model.ipynb
│   ├── 04_collaborative_filtering.ipynb
│   ├── 05_sentiment_yelp.ipynb
│   └── 06_evaluation.ipynb
├── pipelines/
│   ├── ingest.py                   # CSV → normalised DataFrames
│   ├── features.py                 # engineering + scaling
│   ├── train_ranker.py
│   ├── train_cf.py
│   ├── train_sentiment.py
│   └── evaluate.py
├── artifacts/
│   └── v1/{ranker.joblib, cf_item_sim.npz, scaler.joblib, tfidf.joblib, metrics.json}
└── train.py                        # orchestrator, called by Celery
```

---

## 14. SYSTEM-LEVEL EDGE CASES

| # | Scenario | System behaviour |
|---|---|---|
| E-01 | Photographer deleted with ACCEPTED bookings | Block hard delete → soft-delete, auto-cancel future bookings, notify buyers, refund wallet holds |
| E-02 | Two buyers book same slot simultaneously | Row lock + DB unique constraint → second gets 409 `CONFLICT` |
| E-03 | Buyer books, then photographer is blocked by admin | Bookings auto-CANCELLED with reason `PHOTOGRAPHER_SUSPENDED`, buyers notified |
| E-04 | Access token expires mid-upload | Interceptor refreshes and retries **once**; concurrent 401s queue behind one refresh |
| E-05 | Network drops mid-booking POST | Idempotency key makes retry safe — no duplicate booking |
| E-06 | Photographer never responds | Celery expires at 48h, buyer notified and shown alternatives |
| E-07 | Category deleted while services reference it | `PROTECT` on FK; admin must reassign first |
| E-08 | ML model artifact missing/corrupt | Engine falls back to popularity ranking; alert raised; **API never 500s** |
| E-09 | Redis down | Cache decorator degrades to direct DB; chat shows "reconnecting"; API stays up |
| E-10 | Product file deleted from storage but row exists | Download returns 410 `GONE` with support message; weekly integrity job flags it |
| E-11 | Buyer reviews, then booking is disputed and reverted | Review soft-hidden, excluded from average, restored if dispute resolves |
| E-12 | Clock skew between client and server | All time authority is server-side; client `created_at` is ignored |
| E-13 | Photographer changes service price after a PENDING booking | Booking stores a **price snapshot** at creation — never re-reads live price |
| E-14 | Same email registers as Buyer and Photographer | Email is globally unique; one account, role chosen at signup; role switching is an admin action |
| E-15 | Huge portfolio upload on 2G | Chunked upload + resumable + per-image progress; failure doesn't lose earlier images |
| E-16 | Wallet balance changes during checkout | Balance re-checked inside the locked transaction, not at page load |
| E-17 | Timezone confusion (buyer travelling) | UTC in DB; both parties see `Asia/Karachi` labelled "PKT" on booking screens |
| E-18 | Admin deletes a category with active bookings | Categories are soft-archived (`is_active=False`), never hard-deleted |

---

## 15. BEST PRACTICES (enforced, not suggested)

**Backend**
1. Fat services, thin views — a view should be < 15 lines.
2. Never `fields = "__all__"` on a writable serializer.
3. Every list endpoint declares `select_related`/`prefetch_related`.
4. `Decimal` for money, always.
5. Business rules live in `services.py` **and** as DB constraints.
6. Migrations are reviewed like code; never edit an applied migration.
7. All secrets from environment; `.env` is git-ignored.
8. Custom `User` model from **commit one** (swapping it later is a nightmare).
9. Every model inherits `TimeStampedModel`.
10. Enums via `models.TextChoices` — no bare strings.

**Mobile**
11. TypeScript `strict: true`.
12. Server state → React Query. Client state → zustand. Never mix.
13. Tokens in SecureStore only.
14. Every screen handles four states: loading, empty, error, success.
15. `FlatList` (never `.map()` over long arrays) with `keyExtractor` + `getItemLayout`.
16. All colors/spacing from theme tokens — zero hard-coded hex.
17. Debounce search input at 400ms.
18. Optimistic UI for wishlist/like; rollback on failure.

**Data / ML**
19. Never train on data the model won't see at inference (no leakage).
20. Fit the scaler on train only; persist and reuse it.
21. Version every artifact; keep the previous one for instant rollback.
22. Log every recommendation shown — you cannot evaluate what you didn't record.
23. Recommendations must be **explainable** — always return the reason string.

---

## 16. BUILD ROADMAP

| Phase | Weeks | Modules | Deliverable |
|---|---|---|---|
| 0 Foundation | 1 | Setup | Repo, Docker, settings split, `core` app, CI |
| 1 Identity | 2 | 3 | Register/login/JWT/roles/OTP |
| 2 Profiles | 3 | 4, 5 | Buyer + photographer profiles, wallet |
| 3 Content | 4 | 6 | Portfolio, services, categories, availability |
| 4 Core loop | 5–6 | 7 | Booking state machine + notifications |
| 5 Discovery | 7 | 11 | Search, filters, sorting, map |
| 6 Trust | 8 | 9 | Reviews, ratings, replies |
| 7 Commerce | 9 | 8 | Marketplace, wallet, secure downloads |
| 8 Intelligence | 10–11 | 10 | Feature store, 3 models, hybrid engine, evaluation |
| 9 Communication | 12 | 12, 13 | Chat + push notifications |
| 10 Control | 13 | 14 | Admin dashboard |
| 11 Insight | 14 | 15 | Analytics, Recharts, reports |
| 12 Polish | 15 | 17 | RN screens, animation, a11y |
| 13 Ship | 16 | 16, 18 | OpenAPI docs, deploy, FYP report |

---

## 17. FUTURE ENHANCEMENTS

| # | Enhancement | Value | Effort |
|---|---|---|---|
| F-01 | Stripe / JazzCash / Easypaisa gateway | Instant payment, escrow | High |
| F-02 | Video calls for consultations | Higher conversion | High |
| F-03 | Multi-language (Urdu) + RTL | Market reach | Medium |
| F-04 | Deep-learning recommender (two-tower) | Better cold start | High |
| F-05 | CLIP image-similarity search ("find this style") | Strong differentiator | High |
| F-06 | Dynamic pricing from `seasonal_demand.csv` | Revenue optimisation | Medium |
| F-07 | Contract e-signing | Legal protection | Medium |
| F-08 | Team/second-shooter bookings | Bigger jobs | Medium |
| F-09 | Client photo-delivery galleries | Retention | Medium |
| F-10 | Reels/short-video discovery feed | Engagement | High |
| F-11 | Photographer subscription tiers | Recurring revenue | Medium |
| F-12 | Fraud/fake-review detection (isolation forest) | Trust | Medium |
| F-13 | Web app (Next.js) sharing the same API | SEO reach | High |
| F-14 | A/B testing framework for ranking weights | Data-driven tuning | Medium |

---

## MODULE 1 COMPLETE
