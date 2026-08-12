"""
The recommendation engine — Module 10's serving path.

ARCHITECTURE (see docs/01-system-architecture.md §8)
----------------------------------------------------
    candidate generation  (indexed SQL — narrow 200 → ~40)
        ↓
    feature assembly      (pandas frame in FEATURE_ORDER)
        ↓
    content score         (the trained ranker artifact)
        ↓
    collaborative score   (item-item similarity, if the buyer has history)
        ↓
    business rules        (exploration slots, availability boost)
        ↓
    hybrid blend + reason string + cache

THE SINGLE MOST IMPORTANT PROPERTY OF THIS MODULE
-------------------------------------------------
It never raises. Every failure path — missing artifact, corrupt pickle, Redis
down, pandas error — degrades to popularity ranking and logs. A recommendation
screen that returns slightly worse results is a minor problem; one that
returns HTTP 500 is the home screen of the app being broken.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("snapsphere")

# Must match ml/pipelines/features.py FEATURE_ORDER exactly. A mismatch here
# scores garbage silently, so it is asserted at load time in _load_ranker().
FEATURE_ORDER = [
    "bayesian_rating",
    "reviews_count_log",
    "years_experience",
    "success_rate",
    "response_speed_score",
    "portfolio_score_norm",
    "popularity_score",
    "engagement_rate",
    "recency_score",
    "price_percentile",
    "sentiment_score",
    "portfolio_image_count",
]

_ranker = None
_ranker_loaded = False
_cf = None
_cf_loaded = False


# ═══════════════════════════════════════════════════════════════════════════
# ARTIFACT LOADING (once per process, at first use)
# ═══════════════════════════════════════════════════════════════════════════
def _artifact_dir() -> Path:
    return Path(settings.ML_ARTIFACTS_DIR)


def _load_ranker():
    """Load and validate the ranker. Returns None if unusable."""
    global _ranker, _ranker_loaded
    if _ranker_loaded:
        return _ranker
    _ranker_loaded = True

    path = _artifact_dir() / "ranker.joblib"
    if not path.exists():
        logger.warning(
            "Ranker artifact missing at %s — falling back to popularity ranking. "
            "Run: python -m ml.train", path,
        )
        return None

    try:
        import joblib

        model = joblib.load(path)
        order = getattr(model, "feature_order", None)
        if order and list(order) != FEATURE_ORDER:
            # Loud, because a silent mismatch produces confident nonsense.
            logger.error(
                "FEATURE ORDER MISMATCH — engine expects %s but the artifact "
                "was trained on %s. Refusing to use it.", FEATURE_ORDER, list(order),
            )
            return None
        _ranker = model
        logger.info("Ranker loaded (mode=%s)", getattr(model, "mode", "unknown"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not load the ranker artifact: %s", exc)
        _ranker = None
    return _ranker


def _load_cf():
    """Load the collaborative-filtering similarity matrix."""
    global _cf, _cf_loaded
    if _cf_loaded:
        return _cf
    _cf_loaded = True

    path = _artifact_dir() / "cf.joblib"
    if not path.exists():
        return None
    try:
        import joblib

        _cf = joblib.load(path)
        logger.info(
            "CF matrix loaded (%s photographers)", len(_cf.get("photographer_ids", []))
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load the CF artifact: %s", exc)
        _cf = None
    return _cf


def reset_artifact_cache() -> None:
    """Force a reload — called after a nightly retrain promotes a new model."""
    global _ranker, _ranker_loaded, _cf, _cf_loaded
    _ranker, _ranker_loaded = None, False
    _cf, _cf_loaded = None, False


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════
def build_feature_frame(photographers: list):
    """
    Turn PhotographerProfile rows into the model's input frame.

    Features are computed here from the denormalised columns on the profile
    rather than read from the PhotographerFeature table, so a stale or unbuilt
    feature store can never serve wrong scores. The nightly
    `refresh_photographer_features` task keeps that table in sync for offline
    training; this path stays live-accurate.
    """
    import pandas as pd

    if not photographers:
        return pd.DataFrame(columns=FEATURE_ORDER)

    prices = [float(p.base_price or 0) for p in photographers]
    completed = [float(p.completed_bookings or 0) for p in photographers]

    # Percentile and popularity are relative to the candidate set, matching
    # how they were computed at training time.
    sorted_prices = sorted(prices)
    log_completed = [math.log1p(c) for c in completed]
    max_log = max(log_completed) if log_completed else 0.0
    min_log = min(log_completed) if log_completed else 0.0
    log_span = (max_log - min_log) or 1.0

    rows = []
    for p, price, log_c in zip(photographers, prices, log_completed):
        response_hours = float(p.avg_response_time_hours or 24)
        rank = sorted_prices.index(price) if sorted_prices else 0
        rows.append(
            {
                "bayesian_rating": float(p.bayesian_rating or 0),
                "reviews_count_log": math.log1p(float(p.reviews_count or 0)),
                "years_experience": float(p.years_experience or 0),
                "success_rate": float(p.success_rate or 0),
                # INVERTED: low response time is good. See features.py.
                "response_speed_score": 1.0 / (1.0 + response_hours),
                "portfolio_score_norm": float(p.portfolio_score or 0) / 999.0,
                "popularity_score": (log_c - min_log) / log_span,
                "engagement_rate": min(
                    float(p.profile_views or 0) / 1000.0, 1.0
                ),
                "recency_score": float(p.success_rate or 0),
                "price_percentile": rank / max(len(sorted_prices) - 1, 1),
                "sentiment_score": max(
                    min((float(p.avg_rating or 0) - 1.0) / 4.0, 1.0), 0.0
                ),
                "portfolio_image_count": min(
                    float(p.portfolio_score or 0) / 40.0, 60.0
                ),
            }
        )
    return pd.DataFrame(rows, columns=FEATURE_ORDER)


# ═══════════════════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════════════════
def _content_scores(photographers: list) -> list[float]:
    """Score with the trained ranker, or fall back to a rating proxy."""
    ranker = _load_ranker()
    if ranker is None:
        return [float(p.bayesian_rating or 0) / 5.0 for p in photographers]
    try:
        frame = build_feature_frame(photographers)
        return [float(s) for s in ranker.predict(frame)]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ranker scoring failed, using rating proxy: %s", exc)
        return [float(p.bayesian_rating or 0) / 5.0 for p in photographers]


def _collab_scores(buyer_id: int | None, photographers: list) -> list[float]:
    """
    Item-item collaborative score for this buyer.

    Returns zeros when the buyer has too little history — the model has
    nothing to generalise from below REC_MIN_INTERACTIONS_FOR_CF, and a
    confident-looking score built on one interaction is worse than none.
    """
    zeros = [0.0] * len(photographers)
    if buyer_id is None:
        return zeros

    cf = _load_cf()
    if cf is None:
        return zeros

    try:
        import numpy as np

        from apps.recommendations.models import BuyerInteraction

        history = list(
            BuyerInteraction.objects.filter(buyer_id=buyer_id).values_list(
                "photographer_id", "weight"
            )
        )
        if len(history) < settings.REC_MIN_INTERACTIONS_FOR_CF:
            return zeros

        index = cf["photographer_index"]
        similarity = cf["similarity"]

        profile = np.zeros(similarity.shape[0], dtype=np.float32)
        for photographer_id, weight in history:
            col = index.get(photographer_id)
            if col is not None:
                profile[col] += float(weight)

        if not profile.any():
            return zeros

        raw = profile @ similarity
        peak = float(raw.max())
        if peak <= 0:
            return zeros

        return [
            float(raw[index[p.pk]] / peak) if p.pk in index else 0.0
            for p in photographers
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Collaborative scoring failed: %s", exc)
        return zeros


def _business_score(photographer) -> float:
    """
    Hand-tuned adjustments the models cannot express.

    The new-photographer floor is the important one: without it, ranking is
    purely a function of accumulated history, so a photographer with no
    bookings can never get their first — and the marketplace slowly starves
    its own supply side.
    """
    from django.utils import timezone

    score = 0.5

    if photographer.is_accepting_bookings:
        score += 0.2
    if photographer.is_verified:
        score += 0.15
    if photographer.is_featured:
        score += 0.15

    age_days = (timezone.now() - photographer.created_at).days
    if age_days <= 30 and photographer.completed_bookings == 0:
        score += 0.25  # exploration boost

    if photographer.total_bookings > 5:
        cancel_rate = photographer.cancelled_bookings / photographer.total_bookings
        if cancel_rate > 0.3:
            score -= 0.3

    return max(min(score, 1.0), 0.0)


def _reason(photographer, content: float, collab: float, strategy: str) -> str:
    """
    A human-readable justification.

    Non-negotiable for this product: a Pakistani buyer choosing a wedding
    photographer is making one of the largest discretionary purchases of their
    year. "Because our model said 0.87" earns no trust. "4.9★ from 214
    reviews, replies within an hour" does.
    """
    parts = []

    if photographer.avg_rating and photographer.reviews_count:
        parts.append(
            f"{float(photographer.avg_rating):.1f}★ from "
            f"{photographer.reviews_count} reviews"
        )
    if photographer.is_verified:
        parts.append("verified")

    category = photographer.categories.first() if photographer.pk else None
    if category:
        parts.append(f"specialises in {category.name}")

    hours = float(photographer.avg_response_time_hours or 24)
    if hours <= 1:
        parts.append("replies within an hour")
    elif hours <= 6:
        parts.append(f"replies in ~{int(hours)}h")

    if collab > 0.5:
        parts.append("popular with buyers like you")
    if strategy == "EXPLORATION":
        parts.append("new on SnapSphere")
    if photographer.completed_bookings > 40:
        parts.append(f"{photographer.completed_bookings} shoots completed")

    return " · ".join(parts[:4]) if parts else "Recommended for you"


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
def recommend(
    *,
    buyer=None,
    category: str | None = None,
    city: str | None = None,
    max_price: float | None = None,
    limit: int = 20,
    use_cache: bool = True,
) -> dict:
    """
    Return ranked photographers with explanations.

    This is the ONLY function the API layer calls. Swapping the whole engine
    for an HTTP call to a separate ML service later means rewriting this
    function body and nothing else (ADR-003).
    """
    from apps.profiles import selectors

    buyer_id = buyer.pk if buyer and buyer.is_authenticated else None
    cache_key = _cache_key(buyer_id, category, city, max_price, limit)

    if use_cache:
        hit = _cache_get(cache_key)
        if hit is not None:
            return hit

    # ─── 1. Candidate generation ─────────────────────────────────────────────
    queryset = selectors.photographers_for_list().filter(is_accepting_bookings=True)
    if category:
        queryset = queryset.filter(categories__slug=category)
    if city:
        queryset = queryset.filter(user__city__iexact=city)
    if max_price:
        queryset = queryset.filter(base_price__lte=max_price)

    # Cap the candidate pool: scoring is linear in candidates, and beyond a
    # few hundred the extra rows never reach the top 20 anyway.
    candidates = list(queryset.distinct()[:200])

    if not candidates:
        result = _relaxed_fallback(category, city, max_price, limit)
        _cache_set(cache_key, result)
        return result

    # ─── 2-5. Score ──────────────────────────────────────────────────────────
    ranker = _load_ranker()
    content = _content_scores(candidates)
    collab = _collab_scores(buyer_id, candidates)
    has_collab = any(c > 0 for c in collab)

    w_content = settings.REC_WEIGHT_CONTENT
    w_collab = settings.REC_WEIGHT_COLLAB
    w_business = settings.REC_WEIGHT_BUSINESS

    if not has_collab:
        # Redistribute the collaborative weight rather than letting a block of
        # zeros drag every final score down uniformly.
        total = w_content + w_business
        w_content, w_business, w_collab = w_content / total, w_business / total, 0.0

    scored = []
    for photographer, c_score, cf_score in zip(candidates, content, collab):
        business = _business_score(photographer)
        final = w_content * c_score + w_collab * cf_score + w_business * business

        from django.utils import timezone

        is_new = (
            (timezone.now() - photographer.created_at).days <= 30
            and photographer.completed_bookings == 0
        )
        if is_new:
            strategy = "EXPLORATION"
        elif has_collab and cf_score > c_score:
            strategy = "COLLABORATIVE"
        elif ranker is None:
            strategy = "POPULARITY"
        else:
            strategy = "HYBRID"

        photographer.score = round(final, 4)
        photographer.content_score = round(c_score, 4)
        photographer.collab_score = round(cf_score, 4)
        photographer.business_score = round(business, 4)
        photographer.strategy = strategy
        photographer.reason = _reason(photographer, c_score, cf_score, strategy)
        scored.append(photographer)

    scored.sort(key=lambda p: -p.score)
    top = _apply_exploration_quota(scored, limit)

    result = {
        "photographers": top,
        "strategy": "HYBRID" if has_collab else ("CONTENT" if ranker else "POPULARITY"),
        "personalised": has_collab,
        "model_mode": getattr(ranker, "mode", "none") if ranker else "none",
        "relaxed": None,
    }
    _cache_set(cache_key, result)
    return result


def _apply_exploration_quota(scored: list, limit: int) -> list:
    """
    Reserve slots for new photographers.

    Pure score ordering is a rich-get-richer loop: established photographers
    rank high, get booked, rank higher. Holding back a couple of slots is what
    keeps new supply discoverable — and it is a deliberate, tunable business
    decision (REC_EXPLORATION_SLOTS), not an accident of the model.
    """
    quota = settings.REC_EXPLORATION_SLOTS
    if quota <= 0 or len(scored) <= limit:
        return scored[:limit]

    top = scored[:limit]
    if sum(1 for p in top if p.strategy == "EXPLORATION") >= quota:
        return top

    newcomers = [
        p for p in scored[limit:] if p.strategy == "EXPLORATION"
    ][:quota]
    if not newcomers:
        return top

    # Displace from the bottom of the page, never the top three.
    keep = top[: limit - len(newcomers)]
    return keep + newcomers


def _relaxed_fallback(category, city, max_price, limit) -> dict:
    """
    Progressive relaxation when the filters match nobody.

    An empty state is a dead end. Widening the budget, then dropping the city,
    then dropping the category gives the buyer something to act on — and the
    `relaxed` field tells the UI what was loosened so it can say so honestly
    instead of pretending these were exact matches.
    """
    from apps.profiles import selectors

    attempts = [
        ("budget widened by 25%", {"category": category, "city": city,
                                   "max_price": max_price * 1.25 if max_price else None}),
        ("searched nearby cities", {"category": category, "city": None,
                                    "max_price": max_price}),
        ("showing all categories", {"category": None, "city": city, "max_price": None}),
        ("showing top-rated photographers", {"category": None, "city": None,
                                             "max_price": None}),
    ]

    for label, params in attempts:
        qs = selectors.photographers_for_list().filter(is_accepting_bookings=True)
        if params["category"]:
            qs = qs.filter(categories__slug=params["category"])
        if params["city"]:
            qs = qs.filter(user__city__iexact=params["city"])
        if params["max_price"]:
            qs = qs.filter(base_price__lte=params["max_price"])

        rows = list(qs.distinct().order_by("-bayesian_rating")[:limit])
        if rows:
            for p in rows:
                p.score = round(float(p.bayesian_rating or 0) / 5.0, 4)
                p.content_score = p.score
                p.collab_score = 0.0
                p.business_score = _business_score(p)
                p.strategy = "POPULARITY"
                p.reason = _reason(p, p.score, 0.0, "POPULARITY")
            return {
                "photographers": rows,
                "strategy": "POPULARITY",
                "personalised": False,
                "model_mode": "none",
                "relaxed": label,
            }

    return {
        "photographers": [],
        "strategy": "POPULARITY",
        "personalised": False,
        "model_mode": "none",
        "relaxed": "no photographers available",
    }


# ═══════════════════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════════════════
def _cache_key(buyer_id, category, city, max_price, limit) -> str:
    payload = json.dumps(
        {"b": buyer_id, "c": category, "city": city, "p": max_price, "n": limit},
        sort_keys=True,
    )
    digest = hashlib.md5(payload.encode()).hexdigest()[:16]
    return f"rec:{buyer_id or 'anon'}:{digest}"


#: Score attributes attached to each photographer by recommend().
_SCORE_ATTRS = (
    "score", "content_score", "collab_score", "business_score", "strategy", "reason",
)


def _cache_set(key: str, value: dict) -> None:
    """
    Cache the IDS AND SCORES ONLY — never the model instances.

    Pickling ORM objects into Redis stores a snapshot of every column, so a
    photographer who raises their price or gets blocked keeps being served
    with stale data for the whole TTL. Worse, the pickle breaks outright the
    next time the model gains a field.

    Re-fetching by id on a hit costs one indexed query. What the cache is
    actually saving is the scoring pass — the feature frame, the ranker
    predict and the CF matrix multiply — which is the expensive part.
    """
    try:
        cache.set(
            key,
            {
                "ids": [p.pk for p in value["photographers"]],
                "scores": {
                    p.pk: {attr: getattr(p, attr, None) for attr in _SCORE_ATTRS}
                    for p in value["photographers"]
                },
                "strategy": value["strategy"],
                "personalised": value["personalised"],
                "model_mode": value["model_mode"],
                "relaxed": value["relaxed"],
            },
            settings.REC_CACHE_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recommendation cache write failed: %s", exc)


def _cache_get(key: str) -> dict | None:
    """Rehydrate a cached result from live rows. Returns None on any problem."""
    try:
        payload = cache.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recommendation cache read failed: %s", exc)
        return None

    if not payload:
        return None

    try:
        from apps.profiles import selectors

        ids = payload["ids"]
        if not ids:
            return None

        rows = {p.pk: p for p in selectors.photographers_for_list().filter(pk__in=ids)}

        ordered = []
        for pk in ids:
            photographer = rows.get(pk)
            if photographer is None:
                # Blocked, deleted or unapproved since we cached. Dropping it
                # is exactly why we re-fetch instead of pickling.
                continue
            for attr, val in payload["scores"].get(pk, {}).items():
                setattr(photographer, attr, val)
            ordered.append(photographer)

        if not ordered:
            return None

        return {
            "photographers": ordered,
            "strategy": payload["strategy"],
            "personalised": payload["personalised"],
            "model_mode": payload["model_mode"],
            "relaxed": payload["relaxed"],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recommendation cache rehydrate failed: %s", exc)
        return None
