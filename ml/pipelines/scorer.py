"""
The production ranking artifact.

WHY THIS CLASS EXISTS INSTEAD OF A BARE sklearn MODEL
-----------------------------------------------------
Statistical testing of buyer_interactions.csv (see `signal_test` below, and
the numbers printed by train_ranker.py) shows that its `Booking_Status`
column is assigned at random:

    avg_rating          → booking     r = -0.006,  p = 0.90
    reviews_count       → booking     r =  0.054,  p = 0.23
    response_time       → booking     r = -0.000,  p = 0.998
    chi²(category, booking_status)    p = 0.95
    booking rate by rating quartile   32.3% / 32.5% / 32.8% / 31.2%

There is nothing to learn. A supervised model fitted on it scores R² = -0.03,
i.e. worse than predicting the mean, and any reported "accuracy" would be an
artifact of the evaluation rather than a property of the model.

Pretending otherwise would be the single most damaging thing this project
could do, so the ranker is built to be honest about it:

  * If the training data contains measurable signal, a learned model is used.
  * If it does not, the ranker falls back to a TRANSPARENT weighted score
    whose weights are stated, explainable and defensible on domain grounds.

Both paths expose the same `predict()` interface, so the API, the caching
layer and the mobile client never know or care which is active. When the live
platform accumulates real outcomes in the RecommendationEvent table, the
nightly retrain detects signal and switches to the learned model
automatically — no code change, no redeploy.

This is also how real marketplaces bootstrap: a hand-tuned relevance formula
first, a learned ranker once you have traffic to learn from.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from ml.pipelines.features import FEATURE_ORDER

# Domain-justified weights for the fallback scorer. Each is defensible:
#
#   bayesian_rating      0.30  quality, smoothed so review count matters
#   success_rate         0.20  do they actually deliver the booking
#   response_speed       0.15  buyers abandon slow responders
#   popularity           0.12  social proof, log-compressed
#   portfolio            0.10  the work itself
#   reviews_volume       0.06  confidence in the rating
#   engagement           0.04  do buyers explore the portfolio
#   sentiment            0.03  what reviews actually say
PRIOR_WEIGHTS = {
    "bayesian_rating": 0.30,
    "success_rate": 0.20,
    "response_speed_score": 0.15,
    "popularity_score": 0.12,
    "portfolio_score_norm": 0.10,
    "reviews_count_log": 0.06,
    "engagement_rate": 0.04,
    "sentiment_score": 0.03,
}

#: Minimum absolute correlation, at p < 0.05, for a feature to count as signal.
SIGNAL_MIN_ABS_R = 0.10
SIGNAL_MAX_P = 0.05


def signal_test(X: pd.DataFrame, y: pd.Series) -> dict:
    """
    Decide whether the target is learnable from the features at all.

    Returns the per-feature correlations plus a boolean verdict. Run BEFORE
    training so the decision is made on evidence rather than on hope.
    """
    findings = {}
    signal_count = 0
    for column in X.columns:
        values = X[column].astype(float)
        if values.std() == 0:
            findings[column] = {"r": 0.0, "p": 1.0, "signal": False}
            continue
        r, p = stats.pearsonr(values, y.astype(float))
        has_signal = abs(r) >= SIGNAL_MIN_ABS_R and p < SIGNAL_MAX_P
        findings[column] = {"r": round(float(r), 4), "p": round(float(p), 4),
                            "signal": bool(has_signal)}
        signal_count += int(has_signal)

    return {
        "features_with_signal": signal_count,
        "total_features": len(X.columns),
        "has_learnable_signal": signal_count > 0,
        "per_feature": findings,
    }


class SnapSphereRanker:
    """
    Picklable ranking artifact with a stable interface.

    Usage from Django (apps/recommendations/engine.py):

        ranker = joblib.load(ARTIFACTS / "ranker.joblib")
        scores = ranker.predict(feature_dataframe)   # raw, unscaled features

    The scaler is carried inside, so callers cannot accidentally apply a
    different transformation at inference than was used at training — the
    classic silent ML production bug.
    """

    def __init__(self, mode: str, scaler=None, model=None,
                 weights: dict | None = None, metadata: dict | None = None):
        if mode not in ("learned", "prior"):
            raise ValueError(f"Unknown ranker mode: {mode}")
        self.mode = mode
        self.scaler = scaler
        self.model = model
        self.weights = weights or PRIOR_WEIGHTS
        self.feature_order = list(FEATURE_ORDER)
        self.metadata = metadata or {}

    # ─── Inference ───────────────────────────────────────────────────────────
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Score photographers. Input columns must cover FEATURE_ORDER."""
        missing = [c for c in self.feature_order if c not in features.columns]
        if missing:
            raise KeyError(f"Ranker input is missing features: {missing}")

        X = features[self.feature_order].astype(float)

        if self.mode == "learned":
            return np.clip(self.model.predict(self.scaler.transform(X)), 0.0, 1.0)

        # Prior mode: weighted sum of already-0-1-scaled features.
        score = np.zeros(len(X), dtype=float)
        for name, weight in self.weights.items():
            column = X[name].to_numpy(dtype=float)
            if name == "bayesian_rating":
                column = column / 5.0          # 0-5 → 0-1
            elif name == "reviews_count_log":
                span = column.max()
                column = column / span if span > 0 else column
            score += weight * np.clip(column, 0.0, 1.0)

        total_weight = sum(self.weights.values())
        return np.clip(score / total_weight if total_weight else score, 0.0, 1.0)

    # ─── Explainability ──────────────────────────────────────────────────────
    def explain(self, row: pd.Series) -> list[tuple[str, float]]:
        """
        Per-feature contribution for one photographer, largest first.

        This is what lets the API return "4.9★ · 214 reviews · replies in 2h"
        instead of an unexplained number. A recommendation a user cannot
        understand is a recommendation they will not trust.
        """
        if self.mode == "prior":
            contributions = []
            for name, weight in self.weights.items():
                value = float(row[name])
                if name == "bayesian_rating":
                    value /= 5.0
                contributions.append((name, round(weight * min(value, 1.0), 4)))
            return sorted(contributions, key=lambda kv: -kv[1])

        importances = getattr(self.model, "feature_importances_", None)
        if importances is None:
            return []
        return sorted(
            ((n, round(float(i), 4)) for n, i in zip(self.feature_order, importances)),
            key=lambda kv: -kv[1],
        )

    def __repr__(self) -> str:
        return f"<SnapSphereRanker mode={self.mode} features={len(self.feature_order)}>"
