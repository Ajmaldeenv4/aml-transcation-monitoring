"""Honest evaluation of the ML layer: false-positive reduction vs. rules-only.

Three independently generated datasets keep each decision away from the data
that scores it:

* a **training** set fits the model;
* a **validation** set picks the risk threshold that meets the target recall;
* **test** sets, one per seed, measure that fixed threshold. Results are
  reported as a mean with the min-max range across seeds.

Three checks put the result in context. A no-ML baseline ranks alerts by total
amount, using the same procedure. A shifted test set lowers laundering amounts,
to show whether the model has learned behaviour or just a price range. A
sensitivity run narrows the one difference the generator plants, shorter
laundering history: the result measures that assumption, not real-world skill.

The saved production model is never touched. Every number printed here is
reproducible from this module. No fabricated metrics.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from statistics import mean

import numpy as np

from sentinel.config import REPO_ROOT, load_rules_config
from sentinel.generator import generate_dataset
from sentinel.generator.generate import LAUNDERING_HISTORY_TXNS, LEGITIMATE_HISTORY_TXNS
from sentinel.ingestion import load_transactions, normalise_frame
from sentinel.rules import run_rules
from sentinel.scoring.features import FEATURE_NAMES, alert_label, build_feature_matrix
from sentinel.scoring.model import train_model

METRICS_PATH = REPO_ROOT / "artifacts" / "metrics.json"

TRAIN_SEED = 42
VALIDATION_SEED = 7
FIRST_TEST_SEED = 100
FIT_SCALE = 40  # training and validation entities per typology
TEST_SCALE = 8
BENIGN_TXNS = 600
SHIFTED_AMOUNT_FACTOR = 0.6
SENSITIVITY_TEST_SEEDS = 10
HISTORY_SCENARIOS = {
    "planted_signal": LAUNDERING_HISTORY_TXNS,
    "half_overlap": (4, 24),
    "no_signal": LEGITIMATE_HISTORY_TXNS,
}


def _prepare(seed: int, scale: int, **generator_args):
    df = generate_dataset(seed=seed, scale=scale, benign=BENIGN_TXNS, **generator_args)
    txns = load_transactions(normalise_frame(df))
    alerts = run_rules(txns, load_rules_config())
    txn_by_id = {t.txn_id: t for t in txns}
    labels = np.array([alert_label(a, txn_by_id) for a in alerts])
    features = np.array(build_feature_matrix(alerts, txns)[0], dtype=float)
    return txns, alerts, labels, features


def choose_threshold(scores: np.ndarray, labels: np.ndarray, target_recall: float) -> float:
    """Return the highest threshold that still keeps >= target_recall of positives."""
    positives = np.sort(scores[labels == 1])[::-1]
    needed = int(np.ceil(target_recall * len(positives)))
    return float(positives[needed - 1])


def operating_point(scores: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, float]:
    """Percentage outcomes when only alerts scoring >= threshold are reviewed."""
    reviewed = scores >= threshold
    negatives = labels == 0
    return {
        "recall": float(100 * labels[reviewed].sum() / labels.sum()),
        "fp_reduction": float(100 * (~reviewed & negatives).sum() / negatives.sum()),
        "review_reduction": float(100 * (~reviewed).mean()),
    }


def _spread(points: list[dict[str, float]], key: str, name: str) -> dict[str, float]:
    values = [p[key] for p in points]
    return {
        f"{name}_pct": round(mean(values), 1),
        f"{name}_min_pct": round(min(values), 1),
        f"{name}_max_pct": round(max(values), 1),
    }


def evaluate(
    target_recall: float = 0.95,
    n_test_seeds: int = 30,
    laundering_history_txns: tuple[int, int] = LAUNDERING_HISTORY_TXNS,
) -> dict:
    history = {"laundering_history_txns": laundering_history_txns}
    train_txns, train_alerts, _, _ = _prepare(TRAIN_SEED, FIT_SCALE, **history)
    _, val_alerts, val_labels, val_x = _prepare(VALIDATION_SEED, FIT_SCALE, **history)

    with tempfile.TemporaryDirectory() as tmp:
        model = train_model(train_alerts, train_txns, path=Path(tmp) / "evaluation_model.pkl")

    def risk(x: np.ndarray) -> np.ndarray:
        return model.predict_proba(x)[:, 1] * 100

    amount_col = FEATURE_NAMES.index("total_amount")
    threshold = choose_threshold(risk(val_x), val_labels, target_recall)
    baseline_threshold = choose_threshold(val_x[:, amount_col], val_labels, target_recall)

    ml, baseline, shifted = [], [], []
    total_pos = total_neg = 0
    for seed in range(FIRST_TEST_SEED, FIRST_TEST_SEED + n_test_seeds):
        _, _, labels, x = _prepare(seed, TEST_SCALE, **history)
        ml.append(operating_point(risk(x), labels, threshold))
        baseline.append(operating_point(x[:, amount_col], labels, baseline_threshold))
        total_pos += int(labels.sum())
        total_neg += int((labels == 0).sum())

        _, _, s_labels, s_x = _prepare(
            seed, TEST_SCALE, laundering_amount_factor=SHIFTED_AMOUNT_FACTOR, **history
        )
        shifted.append(operating_point(risk(s_x), s_labels, threshold))

    return {
        "test_seeds": n_test_seeds,
        "test_alerts_total": total_pos + total_neg,
        "true_positive_alerts": total_pos,
        "false_positive_alerts": total_neg,
        "training_alerts": len(train_alerts),
        "validation_alerts": len(val_alerts),
        "target_recall": target_recall,
        "risk_threshold": round(threshold, 2),
        **_spread(ml, "recall", "recall_preserved"),
        **_spread(ml, "fp_reduction", "false_positive_reduction"),
        **_spread(ml, "review_reduction", "review_volume_reduction"),
        "baseline_amount_recall_pct": round(mean(p["recall"] for p in baseline), 1),
        "baseline_amount_fp_reduction_pct": round(mean(p["fp_reduction"] for p in baseline), 1),
        "shifted_amounts_recall_pct": round(mean(p["recall"] for p in shifted), 1),
        "shifted_amounts_fp_reduction_pct": round(mean(p["fp_reduction"] for p in shifted), 1),
    }


def history_sensitivity(n_test_seeds: int = SENSITIVITY_TEST_SEEDS) -> dict[str, dict[str, float]]:
    """Re-run the evaluation as the planted history difference shrinks to nothing."""
    results = {}
    for name, history in HISTORY_SCENARIOS.items():
        m = evaluate(n_test_seeds=n_test_seeds, laundering_history_txns=history)
        results[name] = {
            "recall_pct": m["recall_preserved_pct"],
            "fp_reduction_pct": m["false_positive_reduction_pct"],
            "baseline_fp_reduction_pct": m["baseline_amount_fp_reduction_pct"],
        }
    return results


def main() -> int:
    metrics = evaluate()
    metrics["history_sensitivity"] = history_sensitivity()
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("Sentinel AML - ML layer evaluation (synthetic data)\n")
    for k, v in metrics.items():
        print(f"  {k:<40} {v}")
    print(f"\nMetrics written to {METRICS_PATH}")
    print(
        "\nHeadline: at a threshold fixed on validation data, "
        f"{metrics['recall_preserved_pct']}% recall and "
        f"{metrics['false_positive_reduction_pct']}% fewer false positives "
        f"across {metrics['test_seeds']} test seeds."
    )
    no_signal = metrics["history_sensitivity"]["no_signal"]
    print(
        f"Without the planted history signal: {no_signal['fp_reduction_pct']}% fewer false "
        f"positives, against {no_signal['baseline_fp_reduction_pct']}% for the amount baseline."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
