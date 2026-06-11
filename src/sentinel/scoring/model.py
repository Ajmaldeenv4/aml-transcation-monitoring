"""Gradient-boosting risk model: train, persist, load, and score alerts."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier

from sentinel.config import REPO_ROOT
from sentinel.models import Alert, Transaction
from sentinel.scoring.explain import build_reasons
from sentinel.scoring.features import (
    FEATURE_NAMES,
    alert_label,
    build_feature_matrix,
)

DEFAULT_MODEL_PATH = REPO_ROOT / "artifacts" / "risk_model.pkl"
RANDOM_SEED = 42


def train_model(
    alerts: list[Alert],
    transactions: list[Transaction],
    path: str | Path = DEFAULT_MODEL_PATH,
) -> GradientBoostingClassifier:
    """Train the classifier on labelled alerts and persist the artifact."""
    matrix, txn_by_id, _ = build_feature_matrix(alerts, transactions)
    x = np.array(matrix, dtype=float)
    y = np.array([alert_label(a, txn_by_id) for a in alerts], dtype=int)

    if len(set(y.tolist())) < 2:
        raise ValueError("training data has only one class; need both TP and FP alerts")

    model = GradientBoostingClassifier(random_state=RANDOM_SEED)
    model.fit(x, y)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump({"model": model, "feature_names": FEATURE_NAMES}, fh)
    return model


def load_model(path: str | Path = DEFAULT_MODEL_PATH) -> dict:
    with open(path, "rb") as fh:
        return pickle.load(fh)  # noqa: S301 - our own artifact


def score_alerts(
    alerts: list[Alert],
    transactions: list[Transaction],
    path: str | Path = DEFAULT_MODEL_PATH,
) -> list[Alert]:
    """Return copies of alerts with risk_score (0-100) and SHAP-derived reasons.

    Raises FileNotFoundError if the model artifact is missing — callers (e.g. the
    seed CLI) decide whether to treat scoring as optional.
    """
    bundle = load_model(path)
    model = bundle["model"]
    matrix, _, _ = build_feature_matrix(alerts, transactions)
    x = np.array(matrix, dtype=float)
    probs = model.predict_proba(x)[:, 1]
    reasons = build_reasons(model, x, bundle["feature_names"])

    scored: list[Alert] = []
    for alert, prob, why in zip(alerts, probs, reasons, strict=True):
        scored.append(
            alert.model_copy(
                update={"risk_score": round(float(prob) * 100, 1), "risk_reasons": why}
            )
        )
    return scored
