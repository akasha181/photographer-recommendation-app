"""
Feature engineering for the photographer ranking model.

THE CENTRAL PROBLEM
-------------------
The raw columns cannot be fed to a model as they are:

  response_time_hours  1-48    LOW is good  → must be INVERTED, or the model
                                              learns to prefer slow replies
  portfolio_score      19-999  }
  reviews_count        6-499   }  wildly different scales — a distance-based
  avg_rating           2.5-5.0 }  or regularised model would be dominated by
  price_pkr            10k-199k}  whichever column happens to be largest

  avg_rating alone     a 5.00 from 6 reviews outranks a 4.85 from 499

Each of those is corrected below, and the reasoning is recorded next to the
code so the choice can be defended rather than merely asserted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# The order is a CONTRACT. apps/recommendations/models.py
# PhotographerFeature.as_vector() must produce exactly this sequence, or the
# live model silently scores garbage — the worst kind of ML bug, because
# nothing raises.
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

BAYESIAN_PRIOR_COUNT = 10.0   # m — how many "average" reviews to assume
BAYESIAN_PRIOR_RATING = 4.0   # C — the platform's assumed mean rating


def bayesian_rating(rating: pd.Series, count: pd.Series,
                    m: float = BAYESIAN_PRIOR_COUNT,
                    c: float = BAYESIAN_PRIOR_RATING) -> pd.Series:
    """
    Smooth a rating toward the platform mean, weighted by review count.

        score = (n / (n + m)) · R  +  (m / (n + m)) · C

    Why this matters concretely, using real rows from the dataset:

        raw 5.00 from   6 reviews  →  4.38   (barely above the prior)
        raw 4.85 from 499 reviews  →  4.83   (the evidence is overwhelming)

    Without smoothing the first outranks the second, and the top of every
    search result fills up with lucky one-review accounts.
    """
    n = count.astype(float)
    return (n / (n + m)) * rating.astype(float) + (m / (n + m)) * c


def response_speed(hours: pd.Series) -> pd.Series:
    """
    Invert response time into a 0-1 score where HIGHER IS BETTER.

        1 hour   → 0.50
        6 hours  → 0.14
        24 hours → 0.04
        48 hours → 0.02

    The 1/(1+x) shape is deliberate: it draws a sharp distinction between
    replying in 1 hour vs 6 hours (which buyers care about intensely) and
    almost none between 36 and 48 hours (by then the buyer has moved on).
    A linear inversion would spend most of its range on differences nobody
    notices.
    """
    return 1.0 / (1.0 + hours.astype(float))


def popularity(completed: pd.Series) -> pd.Series:
    """
    log1p-compress booking counts, then scale to 0-1.

    Raw counts are brutally long-tailed. Linearly, a photographer with 400
    bookings would score 20× one with 20 — swamping every quality signal.
    On a log scale the same gap is ~2×, which reflects how buyers actually
    perceive it ("very established" vs "established").
    """
    logged = np.log1p(completed.astype(float))
    span = logged.max() - logged.min()
    return (logged - logged.min()) / span if span > 0 else pd.Series(0.5, index=completed.index)


def build_photographer_features(
    photographers: pd.DataFrame,
    interactions: pd.DataFrame | None = None,
    sentiment_by_photographer: pd.Series | None = None,
) -> pd.DataFrame:
    """Turn the raw profile table into the model-ready feature matrix."""
    df = photographers.copy()

    # ─── Rating: smoothed ────────────────────────────────────────────────────
    df["bayesian_rating"] = bayesian_rating(df["avg_rating"], df["reviews_count"])

    # ─── Counts: compressed ──────────────────────────────────────────────────
    df["reviews_count_log"] = np.log1p(df["reviews_count"].astype(float))

    # ─── Response time: INVERTED ─────────────────────────────────────────────
    df["response_speed_score"] = response_speed(df["response_time_hours"])

    # ─── Portfolio score: 0-999 → 0-1 ────────────────────────────────────────
    df["portfolio_score_norm"] = df["portfolio_score"].astype(float) / 999.0

    # ─── Derived booking volume ──────────────────────────────────────────────
    # The CSV has no booking count, so it is estimated from reviews and the
    # success rate: reviews are left by completed bookings, and only a
    # fraction of completed bookings get reviewed.
    df["completed_bookings_est"] = (
        df["reviews_count"] / 0.72 * df["success_rate"]
    ).round()
    df["popularity_score"] = popularity(df["completed_bookings_est"])

    # ─── Engagement DEPTH (deliberately not conversion) ──────────────────────
    # An earlier version defined this as booked/views. That is booking
    # conversion — which is exactly the target the ranker predicts, so
    # including it was target leakage: the model could read the answer off
    # its own input and reported R² = 0.9997.
    #
    # This version measures how deeply buyers engage with the portfolio
    # BEFORE deciding, which is a genuine leading indicator and is
    # independent of whether they went on to book.
    if interactions is not None and len(interactions):
        grouped = interactions.groupby("photographer_id")
        depth = (
            grouped["portfolio_interactions"].sum() / grouped.size().clip(lower=1)
        ).rename("engagement_rate")
        df = df.merge(depth, left_on="photographer_id", right_index=True, how="left")
        df["engagement_rate"] = df["engagement_rate"].fillna(0.0)
        # Normalise to 0-1 so it sits on the same scale as its neighbours.
        span = df["engagement_rate"].max()
        if span > 0:
            df["engagement_rate"] = df["engagement_rate"] / span
    else:
        df["engagement_rate"] = 0.0

    # ─── Recency ─────────────────────────────────────────────────────────────
    # No last-activity column exists in the CSV, so success rate stands in as
    # the best available proxy. Live data replaces this via the feature store.
    df["recency_score"] = df["success_rate"]

    # ─── Price positioning ───────────────────────────────────────────────────
    # Percentile, not the raw price: "expensive relative to peers" is what
    # affects choice, and a percentile is already scale-free.
    df["price_percentile"] = df["price_pkr"].rank(pct=True)

    # ─── Sentiment ───────────────────────────────────────────────────────────
    if sentiment_by_photographer is not None:
        df = df.merge(
            sentiment_by_photographer.rename("sentiment_score"),
            left_on="photographer_id", right_index=True, how="left",
        )
        df["sentiment_score"] = df["sentiment_score"].fillna(0.5)
    else:
        # Derive from rating: 5★ → 1.0, 1★ → 0.0
        df["sentiment_score"] = ((df["avg_rating"] - 1.0) / 4.0).clip(0, 1)

    # ─── Portfolio size proxy ────────────────────────────────────────────────
    df["portfolio_image_count"] = (df["portfolio_score"] / 40).round().clip(0, 60)

    return df


def make_observed_target(
    photographers: pd.DataFrame, interactions: pd.DataFrame
) -> pd.Series:
    """
    The REAL target: observed booking conversion per photographer.

        target = (# interactions that ended in "Booked") / (# interactions)

    This is measured behaviour from buyer_interactions.csv, not a formula —
    so a model that predicts it well has learned something about the world.

    WHY THIS REPLACED THE EARLIER SYNTHETIC TARGET
    ----------------------------------------------
    The first version of this function returned a weighted sum of
    bayesian_rating, success_rate, popularity_score, response_speed_score and
    portfolio_score_norm — every one of which is also an input feature.
    Ridge regression recovered those five weights exactly and scored
    R² = 0.9997. That number measured nothing except that linear algebra
    works; the "model" was the formula, restated.

    The honest target is noisier and much harder to predict. That is the
    point: the reported metrics now mean something, and they establish a real
    baseline that future feature work has to beat.

    Photographers with no interaction history get NaN and are excluded from
    training (they are served by the cold-start path instead).
    """
    outcomes = interactions.groupby("photographer_id")["booking_status"]
    booked = outcomes.apply(lambda s: (s == "Booked").sum())
    total = outcomes.size()
    conversion = (booked / total).rename("target")

    return photographers["photographer_id"].map(conversion)


def make_prior_score(df: pd.DataFrame) -> pd.Series:
    """
    Hand-tuned composite score, used as the COLD-START FALLBACK only.

    This is the formula that was previously (and wrongly) used as a training
    target. It remains useful for photographers with no interaction history,
    where there is nothing for the model to learn from — but it is never fed
    to the model as a label.
    """
    return (
        0.35 * (df["bayesian_rating"] / 5.0)
        + 0.25 * df["success_rate"]
        + 0.15 * df["popularity_score"]
        + 0.15 * df["response_speed_score"]
        + 0.10 * df["portfolio_score_norm"]
    ).clip(0, 1)


def fit_scaler(X: pd.DataFrame) -> StandardScaler:
    """
    Fit on TRAIN ONLY, then persist.

    Fitting on the full dataset leaks test-set statistics into training and
    inflates every metric. The fitted scaler is saved alongside the model
    because inference must apply the exact same transformation.
    """
    scaler = StandardScaler()
    scaler.fit(X)
    return scaler


def to_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Select and order the feature columns per the FEATURE_ORDER contract."""
    missing = [c for c in FEATURE_ORDER if c not in df.columns]
    if missing:
        raise KeyError(f"Feature matrix is missing columns: {missing}")
    return df[FEATURE_ORDER].astype(float)
