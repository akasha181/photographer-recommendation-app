"""
Collaborative filtering — item-item cosine similarity.

WHY ITEM-ITEM RATHER THAN USER-USER OR MATRIX FACTORISATION
-----------------------------------------------------------
The audit reports a matrix density of 1.10%: 500 interactions spread over
244 buyers × 186 photographers. That number drives every decision here.

  User-user CF   — needs users with overlapping histories. At 1% density most
                   buyer pairs share zero photographers, so similarity is
                   computed from nothing.
  SVD / ALS      — latent factors need far more signal than 2.7 interactions
                   per photographer. It would fit noise and look confident.
  Item-item      — photographers accumulate interactions from many buyers, so
                   photographer vectors are denser than buyer vectors. The
                   similarity matrix is 186×186, computed once nightly, and
                   scoring a buyer is one sparse dot product.

Item-item is also robust to the cold-start case that matters most: a brand-new
buyer with one interaction still gets meaningful neighbours, whereas a latent
model would have no factors for them at all.
"""

from __future__ import annotations

import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity

from ml.pipelines.ingest import load_interactions

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts"

# Implicit-feedback weights. A completed booking is far stronger evidence of
# preference than a profile view; treating them equally would let idle
# browsing drown out real intent. Mirrors INTERACTION_WEIGHTS in
# apps/recommendations/models.py.
WEIGHTS = {
    "search": 0.5,
    "view": 1.0,
    "click": 2.0,
    "portfolio": 3.0,
    "inquiry": 5.0,
    "booking_pending": 8.0,
    "booking_completed": 10.0,
    "cancelled": -2.0,   # negative: the buyer engaged, then backed out
}


def build_interaction_matrix(interactions: pd.DataFrame):
    """Collapse the session log into a weighted buyer × photographer matrix."""
    rows = []
    for _, r in interactions.iterrows():
        score = WEIGHTS["search"]
        if r["profile_view"]:
            score += WEIGHTS["view"]
        if r["clicks"] > 0:
            score += WEIGHTS["click"]
        if r["portfolio_interactions"] > 0:
            score += WEIGHTS["portfolio"]
        if r["inquiry_made"]:
            score += WEIGHTS["inquiry"]
        if r["booking_status"] == "Booked":
            score += WEIGHTS["booking_completed"]
        elif r["booking_status"] == "Pending":
            score += WEIGHTS["booking_pending"]
        elif r["booking_status"] == "Cancelled":
            score += WEIGHTS["cancelled"]
        rows.append((r["buyer_id"], r["photographer_id"], max(score, 0.0)))

    df = pd.DataFrame(rows, columns=["buyer_id", "photographer_id", "score"])
    df = df.groupby(["buyer_id", "photographer_id"], as_index=False)["score"].sum()

    buyers = sorted(df["buyer_id"].unique())
    photographers = sorted(df["photographer_id"].unique())
    buyer_index = {b: i for i, b in enumerate(buyers)}
    photog_index = {p: i for i, p in enumerate(photographers)}

    matrix = sparse.csr_matrix(
        (
            df["score"].values,
            (
                df["buyer_id"].map(buyer_index).values,
                df["photographer_id"].map(photog_index).values,
            ),
        ),
        shape=(len(buyers), len(photographers)),
    )
    return matrix, buyer_index, photog_index


def train() -> dict:
    print("\n" + "=" * 74)
    print("TRAINING: collaborative filter  (item-item cosine similarity)")
    print("=" * 74)

    started = time.perf_counter()
    interactions = load_interactions()
    matrix, buyer_index, photog_index = build_interaction_matrix(interactions)

    n_buyers, n_photogs = matrix.shape
    density = matrix.nnz / (n_buyers * n_photogs)
    print(f"  matrix                 {n_buyers} buyers × {n_photogs} photographers")
    print(f"  non-zero cells         {matrix.nnz}")
    print(f"  density                {density * 100:.2f}%")
    print(f"  interactions/buyer     mean {matrix.getnnz(axis=1).mean():.2f}, "
          f"max {matrix.getnnz(axis=1).max()}")

    # Cosine on the TRANSPOSE gives photographer×photographer similarity.
    similarity = cosine_similarity(matrix.T.tocsr(), dense_output=True)
    np.fill_diagonal(similarity, 0.0)  # never recommend the item itself

    nonzero_sims = similarity[similarity > 0]
    print(f"\n  similarity matrix      {similarity.shape}")
    print(f"  non-zero pairs         {len(nonzero_sims):,} "
          f"({len(nonzero_sims) / similarity.size * 100:.1f}%)")
    if len(nonzero_sims):
        print(f"  similarity mean/max    {nonzero_sims.mean():.4f} / {nonzero_sims.max():.4f}")

    # ═══════════════════════════════════════════════════════════════════════
    # LEAVE-ONE-OUT EVALUATION — WITHOUT LEAKAGE
    #
    # The first version of this evaluation scored HitRate@10 = 0.97, which was
    # wrong. It held out one interaction from the BUYER'S PROFILE but scored
    # against a similarity matrix that had been computed from the full data —
    # including the very interaction being predicted. The model was being
    # asked to recall something it had already been shown.
    #
    # The fix: for each trial, zero the held-out cell in the matrix, RECOMPUTE
    # the similarity matrix from that reduced data, and only then score. The
    # matrix is 244×186, so recomputing per trial is cheap and correctness is
    # worth far more than the seconds it costs.
    # ═══════════════════════════════════════════════════════════════════════
    hits_at_10, hits_at_20, trials, ranks = 0, 0, 0, []
    dense = matrix.toarray()

    for buyer_row in range(n_buyers):
        seen = matrix[buyer_row].indices
        if len(seen) < 2:
            continue  # nothing to hold out
        held_out = int(seen[-1])

        # Remove the interaction entirely, then rebuild similarity from what
        # is left. This is what "the model has never seen it" actually means.
        reduced = dense.copy()
        reduced[buyer_row, held_out] = 0.0
        sim = cosine_similarity(reduced.T)
        np.fill_diagonal(sim, 0.0)

        profile = reduced[buyer_row]
        scores = profile @ sim
        scores[profile > 0] = -np.inf  # never re-recommend a seen item

        # Rank of the held-out item among all candidates.
        order = np.argsort(-scores)
        rank = int(np.where(order == held_out)[0][0]) + 1
        ranks.append(rank)
        hits_at_10 += int(rank <= 10)
        hits_at_20 += int(rank <= 20)
        trials += 1

    hit_rate = hits_at_10 / trials if trials else 0.0
    hit_rate_20 = hits_at_20 / trials if trials else 0.0
    mean_rank = float(np.mean(ranks)) if ranks else 0.0
    random_baseline = 10 / n_photogs

    print(f"\n  leave-one-out trials   {trials}   "
          f"(similarity recomputed per trial — no leakage)")
    print(f"  HitRate@10             {hit_rate:.4f}")
    print(f"  HitRate@20             {hit_rate_20:.4f}")
    print(f"  mean rank of held-out  {mean_rank:.1f} of {n_photogs}")
    print(f"  random baseline@10     {random_baseline:.4f}")
    if random_baseline:
        print(f"  lift over random       {hit_rate / random_baseline:.2f}×")
    if hit_rate < 0.15:
        print("\n  READ THIS: this is the honest number at 1.1% density. With a")
        print("  mean of 2.04 interactions per buyer, removing one leaves almost")
        print("  no signal to generalise from. CF is therefore weighted at only")
        print("  0.30 in the hybrid blend and is skipped entirely for buyers")
        print("  with fewer than 3 interactions (REC_MIN_INTERACTIONS_FOR_CF).")

    duration = time.perf_counter() - started
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "similarity": similarity.astype(np.float32),
        "buyer_index": buyer_index,
        "photographer_index": photog_index,
        "photographer_ids": list(photog_index.keys()),
    }
    path = ARTIFACT_DIR / "cf.joblib"
    joblib.dump(artifact, path, compress=3)
    sparse.save_npz(ARTIFACT_DIR / "interaction_matrix.npz", matrix)
    print(f"\n  saved                  cf.joblib + interaction_matrix.npz "
          f"({path.stat().st_size / 1024:.0f} KB, {duration:.1f}s)")

    return {
        "name": "cf",
        "algorithm": "item-item cosine similarity on weighted implicit feedback",
        "artifact_path": str(path),
        "training_rows": int(matrix.nnz),
        "training_duration_seconds": round(duration, 2),
        "metrics": {
            "density_percent": round(density * 100, 3),
            "hit_rate_at_10": round(hit_rate, 4),
            "hit_rate_at_20": round(hit_rate_20, 4),
            "mean_rank_of_held_out": round(mean_rank, 1),
            "random_baseline": round(random_baseline, 4),
            "lift": round(hit_rate / random_baseline, 2) if random_baseline else 0,
            "n_buyers": n_buyers,
            "n_photographers": n_photogs,
            "evaluation": "leave-one-out, similarity recomputed per trial",
        },
    }


if __name__ == "__main__":
    train()
