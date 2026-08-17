"""
Sentiment inference for review text — the serving half of Module 10's
sentiment model.

WHY THIS LIVES IN `core` AND NOT IN `reviews` OR `recommendations`
-----------------------------------------------------------------
`reviews` needs it when a review is written, `recommendations` needs it to
compute a photographer's mean sentiment feature, and `analytics` could
reasonably want it too. Putting it in either consumer would make the other one
import sideways, and the dependency graph in docs/01 §5.1 has to stay acyclic.
`core` imports nothing and is imported by everything, so it is the only honest
home.

WHY IT NEVER RAISES
-------------------
The artifact is a build product, not a source file. A fresh clone that has not
run `python -m ml.pipelines.train_sentiment` has no `sentiment.joblib`, and a
missing model must not stop a buyer from posting a review — the label is
decoration on the review, not part of it. Every failure path returns
`(None, None)` and logs once.

WHY SHORT COMMENTS ARE NOT CLASSIFIED
-------------------------------------
The model is TF-IDF over 1–2 grams. Given "ok" it still returns a label with a
confident-looking probability, because softmax always sums to one. Displaying
"NEGATIVE 0.71" against a two-character comment is worse than displaying
nothing, so anything under `MIN_CHARS` is left unlabelled.
"""

import logging
import threading
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("snapsphere")

#: Below this there is not enough text for a bag-of-words model to say anything
#: meaningful. See the module docstring.
MIN_CHARS = 12

#: The three labels ml/pipelines/train_sentiment.py trains on. Kept here so a
#: retrain that changes the label set fails loudly instead of writing values
#: the `Review.sentiment` choices do not contain.
LABELS = frozenset({"POSITIVE", "NEUTRAL", "NEGATIVE"})

_model = None
_loaded = False
_lock = threading.Lock()


def _load():
    """Load the pipeline once per process. Thread-safe; failures are sticky."""
    global _model, _loaded

    if _loaded:
        return _model

    with _lock:
        if _loaded:  # another thread won the race while we waited
            return _model
        _loaded = True

        path = Path(settings.ML_ARTIFACTS_DIR) / "sentiment.joblib"
        if not path.exists():
            logger.info(
                "Sentiment artifact absent — reviews will be stored unlabelled "
                "(run: python -m ml.pipelines.train_sentiment)"
            )
            return None
        try:
            import joblib

            _model = joblib.load(path)
            logger.info("Sentiment model loaded from %s", path.name)
        except Exception as exc:  # noqa: BLE001 — corrupt pickle, missing sklearn
            logger.warning("Sentiment model failed to load: %s", exc)
            _model = None
        return _model


def classify(text: str) -> tuple[str | None, float | None]:
    """
    Predict (label, confidence) for one review comment.

    Returns `(None, None)` when the text is too short to judge, the artifact is
    missing, or inference fails. Callers store whatever they get without
    branching.
    """
    comment = (text or "").strip()
    if len(comment) < MIN_CHARS:
        return None, None

    model = _load()
    if model is None:
        return None, None

    try:
        label = str(model.predict([comment])[0]).upper()
        if label not in LABELS:
            logger.warning("Sentiment model returned unknown label %r", label)
            return None, None
        confidence = float(max(model.predict_proba([comment])[0]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sentiment inference failed: %s", exc)
        return None, None

    return label, round(confidence, 3)


def reset_cache() -> None:
    """Force the next `classify()` to reload. Used by tests."""
    global _model, _loaded
    with _lock:
        _model, _loaded = None, False
