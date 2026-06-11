"""Tests for the ML scoring layer: features, training, scoring, evaluation."""

from __future__ import annotations

import numpy as np

from sentinel.config import load_rules_config
from sentinel.generator import generate_dataset
from sentinel.ingestion import load_transactions, normalise_frame
from sentinel.rules import run_rules
from sentinel.scoring import FEATURE_NAMES, build_feature_row, score_alerts, train_model
from sentinel.scoring.evaluate import evaluate
from sentinel.scoring.features import _index_by_entity, alert_label


def _data(seed=42, scale=4):
    df = generate_dataset(seed=seed, scale=scale, benign=300)
    txns = load_transactions(normalise_frame(df))
    alerts = run_rules(txns, load_rules_config())
    return txns, alerts


def test_feature_row_length_matches_names():
    txns, alerts = _data()
    txn_by_id = {t.txn_id: t for t in txns}
    idx = _index_by_entity(txns)
    row = build_feature_row(alerts[0], txn_by_id, idx, set())
    assert len(row) == len(FEATURE_NAMES)


def test_labels_contain_both_classes():
    txns, alerts = _data()
    txn_by_id = {t.txn_id: t for t in txns}
    labels = {alert_label(a, txn_by_id) for a in alerts}
    assert labels == {0, 1}


def test_train_and_score_bounds(tmp_path):
    txns, alerts = _data()
    path = tmp_path / "m.pkl"
    train_model(alerts, txns, path=path)
    scored = score_alerts(alerts, txns, path=path)
    scores = np.array([a.risk_score for a in scored])
    assert scores.min() >= 0.0
    assert scores.max() <= 100.0
    assert all(isinstance(a.risk_reasons, list) and a.risk_reasons for a in scored)


def test_scoring_is_deterministic(tmp_path):
    txns, alerts = _data()
    path = tmp_path / "m.pkl"
    train_model(alerts, txns, path=path)
    s1 = [a.risk_score for a in score_alerts(alerts, txns, path=path)]
    s2 = [a.risk_score for a in score_alerts(alerts, txns, path=path)]
    assert s1 == s2


def test_evaluation_produces_sane_metrics():
    m = evaluate(target_recall=0.95)
    assert 0 <= m["false_positive_reduction_pct"] <= 100
    assert m["recall_preserved_pct"] >= 95.0
    assert m["true_positive_alerts"] > 0
    assert m["false_positive_alerts"] > 0
