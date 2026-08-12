"""
Train every model and write a metrics report.

    python -m ml.train                # all models
    python -m ml.train --only ranker  # one model

Called by apps.recommendations.tasks.retrain_models on the nightly schedule.
Each trainer returns a metrics dict; they are collected into
ml/artifacts/metrics.json, which is what the ModelVersion registry records and
what makes a rollback decision possible.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

TRAINERS = {
    "sentiment": "ml.pipelines.train_sentiment",
    "ranker": "ml.pipelines.train_ranker",
    "cf": "ml.pipelines.train_cf",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Train SnapSphere models")
    parser.add_argument("--only", choices=list(TRAINERS), help="Train one model only")
    args = parser.parse_args()

    selected = [args.only] if args.only else list(TRAINERS)
    results, failures = {}, []

    for name in selected:
        module_path = TRAINERS[name]
        try:
            module = __import__(module_path, fromlist=["train"])
            results[name] = module.train()
        except Exception as exc:  # noqa: BLE001
            # One model failing must not prevent the others from being
            # retrained — the live model for that name simply stays in place.
            print(f"\n  ✗ {name} training FAILED: {exc.__class__.__name__}: {exc}")
            failures.append(name)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(results, indent=2, default=str))

    print("\n" + "=" * 74)
    print("TRAINING SUMMARY")
    print("=" * 74)
    for name, info in results.items():
        metrics = ", ".join(f"{k}={v}" for k, v in info["metrics"].items())
        print(f"  {name:<12} {info['algorithm'][:38]:<40}")
        print(f"  {'':<12} {metrics}")
    if failures:
        print(f"\n  FAILED: {', '.join(failures)}")
    print(f"\n  metrics written to {ARTIFACT_DIR / 'metrics.json'}")
    print("=" * 74 + "\n")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
