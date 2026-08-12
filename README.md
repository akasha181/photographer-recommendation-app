# SnapSphere

**Photographer Booking & Recommendation Platform** — Final Year Project

A mobile marketplace where buyers discover, compare and book professional
photographers, guided by a recommendation engine, plus a digital marketplace
where photographers sell presets, LUTs and templates.

| | |
|---|---|
| **Mobile** | React Native (Expo SDK 57) + TypeScript |
| **Backend** | Django 5 + Django REST Framework + Channels (ASGI) |
| **Database** | MySQL 8 |
| **Cache / queue / realtime** | Redis 7 (3 logical DBs) |
| **Background jobs** | Celery + Celery Beat |
| **ML** | scikit-learn, pandas, scipy |
| **Auth** | JWT (rotating refresh tokens + blacklist + version kill switch) |
| **Currency** | PKR |

---

## Repository layout

```
akasha/
├── backend/          Django REST API  (15 apps, 46 domain tables)
├── mobile/           React Native app (Expo, TypeScript)
├── admin-web/        React + Recharts admin dashboard (planned)
├── ml/               Datasets, feature pipelines, model training
│   ├── data/raw/     The 10 source CSVs
│   ├── pipelines/    ingest · features · scorer · 3 trainers
│   └── artifacts/    Trained models (.joblib) + metrics.json
├── docs/             Module design documents
├── prototype/        The original SnapSphere RN prototype (UI reference)
└── final version.docx  Project proposal
```

---

## Running it

Everything is already installed and seeded. Three scripts do the work:

```bash
./start.sh              # MySQL + Redis + Django API
./start.sh --workers    # ...plus Celery worker and scheduler
./test.sh               # 23-check end-to-end API test
./stop.sh               # stop the servers
```

`start.sh` is idempotent — it checks what is already running rather than
starting duplicates, and tells you if the database is unseeded.

Then open:

| | |
|---|---|
| Swagger UI | http://127.0.0.1:8000/api/v1/docs/ |
| Django admin | http://127.0.0.1:8000/django-admin/ |
| Health check | http://127.0.0.1:8000/health/ |

### Mobile app

```bash
cd mobile && npx expo start
```

Scan the QR code with **Expo Go**. The app auto-detects your machine's LAN IP
from the Expo host, so no configuration is normally needed. To override, set
`EXPO_PUBLIC_API_URL` in `mobile/.env` — see `src/api/config.ts`.

Your phone and Mac must be on the same Wi-Fi.

### Machine learning

```bash
backend/.venv/bin/python -m ml.pipelines.ingest --audit   # data quality report
backend/.venv/bin/python -m ml.train                      # train all three models
backend/.venv/bin/python -m ml.train --only sentiment     # just one
```

### First-time setup on a new machine

<details>
<summary>Expand — only needed if the venv or database does not exist</summary>

```bash
brew install python@3.12 mysql redis
brew services start mysql && brew services start redis

cd backend
/usr/local/opt/python@3.12/bin/python3.12 -m venv .venv
export MYSQLCLIENT_CFLAGS="-I/usr/local/opt/mysql/include/mysql"
export MYSQLCLIENT_LDFLAGS="-L/usr/local/opt/mysql/lib -lmysqlclient"
.venv/bin/python -m pip install -r requirements/dev.txt
cp .env.example .env      # then set SECRET_KEY

mysql -u root -e "CREATE DATABASE snapsphere CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -e "CREATE USER 'snapsphere'@'localhost' IDENTIFIED BY 'snapsphere';"
mysql -u root -e "GRANT ALL ON snapsphere.* TO 'snapsphere'@'localhost';"

.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_data --flush

cd ../mobile && npm install
```
</details>

---

## Seeded accounts

| Role | Email | Password |
|---|---|---|
| Admin | `admin@snapsphere.pk` | `admin12345` |
| Photographer | `photographer1@snapsphere.pk` … `photographer200@…` | `photographer123` |
| Buyer | `buyer1@snapsphere.pk` … | `buyer12345` |

Seeded from the real datasets: **200 photographers, 244 buyers, 600 services,
499 bookings, 117 reviews, 125 products, 2,221 interactions, 1,196 daily
analytics rows.**

---

## Data-quality findings

Two of the supplied datasets contain **randomly assigned labels**. This was
verified statistically, not assumed, and it shaped the entire ML design.
Run `python -m ml.pipelines.ingest --audit` to reproduce.

### `reviews_feedback.csv` — sentiment labels are noise

300 rows contain only **5 distinct review sentences**, and every sentence
carries all three labels:

```
"Amazing service and very professional."  → Positive 24, Neutral 24, Negative 15
"Not satisfied with the booking process." → Positive 21, Neutral 18, Negative 17
```

**Response:** the sentiment model is trained on `yelp.csv` (44,610 real
reviews with trustworthy star ratings) instead. It reaches **78.9% accuracy /
0.68 macro-F1** on held-out data.

### `buyer_interactions.csv` — booking outcomes are random

Not one photographer attribute predicts whether a booking happened:

| Feature | Pearson r | p |
|---|---|---|
| avg_rating | −0.006 | 0.90 |
| reviews_count | 0.054 | 0.23 |
| response_time | −0.000 | 0.998 |
| χ²(category, booking_status) | — | 0.95 |

Booking rate by rating quartile: **32.3% / 32.5% / 32.8% / 31.2%** — flat.

**Response:** `ml/pipelines/train_ranker.py` runs a signal test *before*
training. Finding none, it ships a **transparent weighted scorer** with stated,
domain-justified weights instead of a model that would be confidently wrong
(a fitted regressor scores R² = −0.03, worse than predicting the mean).

The nightly retrain re-runs the same test against real outcomes collected in
the `recommendation_events` table and switches to the learned model
automatically the moment genuine signal appears — no code change required.

---

## Model results (honest, held-out)

| Model | Algorithm | Result |
|---|---|---|
| **Sentiment** | TF-IDF (1,2-gram) + LogisticRegression | accuracy **0.789**, macro-F1 **0.681** |
| **Ranker** | Transparent weighted scorer | no learnable signal in source data — see above |
| **Collaborative filter** | Item-item cosine on weighted implicit feedback | HitRate@10 **0.094** (1.75× random) at 1.1% density |

The CF number is deliberately modest. An earlier version of the evaluation
reported 0.97 — it was leaking, because the similarity matrix had been built
from data that included the held-out interaction. The evaluation now
recomputes similarity per trial.

---

## Notable engineering decisions

**MySQL silently drops conditional unique constraints.** Django's
`UniqueConstraint(condition=...)` becomes a partial index on PostgreSQL and
*nothing at all* on MySQL — with only a `models.W036` warning. The
double-booking guard, order idempotency and four other integrity rules were
therefore not in the database. Restored using MySQL's generated-column idiom
(`apps/*/migrations/000*_partial_unique_*.py`); verified by test:

```
Duplicate entry '280|2026-09-25|16:00:00' for key 'bookings.uniq_active_booking_slot'
```

**`token_version` is enforced on every request.** Stock
`JWTAuthentication` validates only signature and expiry, so blocking a user
left their access token working for up to 30 minutes.
`apps/accounts/authentication.py` re-checks the version claim and account
state on every call, at the cost of zero extra queries.

**Concurrent token refresh is single-flight.** Five parallel 401s would
otherwise trigger five refreshes, four of them reusing an already-rotated
token — which the backend's reuse detection treats as theft and responds to by
revoking the whole family. `mobile/src/api/client.ts` queues them onto one
promise.

**Layering is enforced by convention, not framework.**
`views → serializers → services/selectors → models`, one direction only.
Writes live in `services.py`, reads in `selectors.py`, and no app imports
another app's `models.py` except for foreign-key declarations.

---

## Documentation

| Document | Contents |
|---|---|
| **[docs/PROJECT-STATE.md](docs/PROJECT-STATE.md)** | **Start here when resuming** — module status, decisions, traps already hit, next task |
| [docs/01-system-architecture.md](docs/01-system-architecture.md) | ADRs, NFRs, security model, threat model, folder structure, deployment topology |

---

## Status

| # | Module | State |
|---|---|---|
| 1 | System architecture | ✅ Documented |
| 2 | Database design | ✅ 46 domain tables, migrated, seeded |
| 3 | Authentication | ✅ Complete, verified end-to-end |
| 4 | Buyer module | 🟡 Discovery done; wishlist/wallet pending |
| 5 | Photographer module | 🟡 Read APIs done; write APIs pending |
| 6 | Portfolio | 🟡 Models + read; upload pending |
| 7 | **Booking** | ⬜ **Next** — models + constraints exist, no services/API |
| 8 | Digital marketplace | ⬜ Models only |
| 9 | Reviews & ratings | 🟡 Models + read; write API pending |
| 10 | AI recommendation | ✅ Pipelines, 3 models, live engine with explanations |
| 11 | Search & filters | ✅ 12 filters, 6 sorts, distance |
| 12 | Notifications | 🟡 Models + service + consumer; API pending |
| 13 | Chat | 🟡 Models + consumers; REST API pending |
| 14 | Admin | ⬜ Models only |
| 15 | Analytics | ⬜ Models + task stubs |
| 16 | API documentation | ✅ Auto-generated at `/api/v1/docs/` |
| 17 | React Native screens | 🟡 Auth + Home + Explore + Detail working |
| 18 | Deployment | ✅ Documented in `docs/01` §12 |

**Code:** 222 backend files (13,349 lines) · 33 mobile files (4,765 lines) ·
9 ML files (1,449 lines).
**Data:** 77 tables · 445 users · 200 photographers · 52,199 bookings ·
51,822 reviews.
