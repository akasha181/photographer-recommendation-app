"""
Sentiment classifier — trained on yelp.csv, NOT on reviews_feedback.csv.

WHY THE SUBSTITUTION
--------------------
`python -m ml.pipelines.ingest --audit` shows reviews_feedback.csv contains
5 distinct sentences across 300 rows, and each sentence carries all three
labels. "Amazing service and very professional." is labelled Positive 24
times, Neutral 24 times and Negative 15 times. There is no learnable signal:
the best achievable accuracy is the majority-class base rate.

yelp.csv gives 44,610 genuine reviews whose star ratings are a trustworthy
label. Star → sentiment mapping:

    1-2★ → NEGATIVE       3★ → NEUTRAL       4-5★ → POSITIVE

The domain differs (restaurants, not photographers) but the linguistic
signal — "disappointing", "exceeded expectations", "would not recommend" —
transfers directly, and 44k labelled examples of it beats 300 mislabelled
ones by an enormous margin.
"""

from __future__ import annotations

import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from ml.pipelines.ingest import load_yelp_reviews

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts"


def train(max_rows: int = 40000, random_state: int = 42) -> dict:
    print("\n" + "=" * 74)
    print("TRAINING: sentiment classifier  (TF-IDF + Logistic Regression)")
    print("=" * 74)

    started = time.perf_counter()
    df = load_yelp_reviews(limit=max_rows)
    print(f"  corpus                 {len(df):,} reviews from yelp.csv")
    print(f"  class balance          {df.sentiment.value_counts().to_dict()}")

    X, y = df["text"].values, df["sentiment"].astype(str).values

    # Stratify: POSITIVE outnumbers NEUTRAL ~5:1, and an unstratified split
    # can leave the test set with too few minority examples to measure.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state, stratify=y
    )
    print(f"  train / test           {len(X_train):,} / {len(X_test):,}")

    pipeline = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    max_features=30_000,
                    # Bigrams matter enormously here: "not good" and "good"
                    # are opposites, and a unigram model sees them as similar.
                    ngram_range=(1, 2),
                    min_df=3,
                    max_df=0.85,
                    sublinear_tf=True,
                    strip_accents="unicode",
                    lowercase=True,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    # Counteracts the 5:1 imbalance so NEUTRAL and NEGATIVE
                    # are not simply ignored in favour of the majority class.
                    class_weight="balanced",
                    C=2.0,
                    random_state=random_state,
                ),
            ),
        ]
    )

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    accuracy = float((y_pred == y_test).mean())
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    print(f"\n  accuracy               {accuracy:.4f}")
    print(f"  macro F1               {report['macro avg']['f1-score']:.4f}")
    print(f"  weighted F1            {report['weighted avg']['f1-score']:.4f}")
    print("\n  per-class:")
    for label in ("NEGATIVE", "NEUTRAL", "POSITIVE"):
        if label in report:
            r = report[label]
            print(f"    {label:<9} precision {r['precision']:.3f}  "
                  f"recall {r['recall']:.3f}  f1 {r['f1-score']:.3f}  "
                  f"support {int(r['support'])}")

    print("\n  confusion matrix (rows = true, cols = predicted):")
    labels = ["NEGATIVE", "NEUTRAL", "POSITIVE"]
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    print(f"    {'':<10}" + "".join(f"{l[:4]:>8}" for l in labels))
    for label, row in zip(labels, cm):
        print(f"    {label:<10}" + "".join(f"{v:>8}" for v in row))

    # Sanity check on real photography-style sentences.
    print("\n  spot check on photography reviews:")
    samples = [
        "Absolutely stunning photos, the team was professional and punctual.",
        "The photos were okay but they arrived late and seemed unprepared.",
        "Terrible experience. Blurry images and he never replied to my messages.",
        "Good but response was a bit late.",
    ]
    for text, pred in zip(samples, pipeline.predict(samples)):
        proba = pipeline.predict_proba([text])[0].max()
        print(f"    {pred:<9} ({proba:.2f})  \"{text[:56]}…\"")

    duration = time.perf_counter() - started
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / "sentiment.joblib"
    joblib.dump(pipeline, path, compress=3)
    print(f"\n  saved                  {path.name} "
          f"({path.stat().st_size / 1024:.0f} KB, {duration:.1f}s)")

    return {
        "name": "sentiment",
        "algorithm": "TfidfVectorizer(1,2) + LogisticRegression(balanced)",
        "artifact_path": str(path),
        "training_rows": len(X_train),
        "training_duration_seconds": round(duration, 2),
        "metrics": {
            "accuracy": round(accuracy, 4),
            "macro_f1": round(report["macro avg"]["f1-score"], 4),
            "weighted_f1": round(report["weighted avg"]["f1-score"], 4),
        },
    }


if __name__ == "__main__":
    train()
