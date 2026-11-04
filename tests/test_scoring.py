"""Tests for the ML scoring layer: features, training, scoring, evaluation."""

from __future__ import annotations

import numpy as np
from tests.conftest import txn

from sentinel.config import load_rules_config
from sentinel.generator import generate_dataset
from sentinel.ingestion import load_transactions, normalise_frame
from sentinel.models import Alert, Severity, Typology
from sentinel.rules import run_rules
from sentinel.scoring import (
    DEFAULT_MODEL_PATH,
    FEATURE_NAMES,
    build_feature_row,
    score_alerts,
    train_model,
)
from sentinel.scoring import evaluate as evaluate_module
from sentinel.scoring.evaluate import (
    choose_threshold,
    evaluate,
    history_sensitivity,
    operating_point,
)
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
    m = evaluate(target_recall=0.95, n_test_seeds=2)
    assert m["test_seeds"] == 2
    assert 0 <= m["false_positive_reduction_pct"] <= 100
    assert m["recall_preserved_min_pct"] <= m["recall_preserved_pct"] <= m["recall_preserved_max_pct"]
    assert m["true_positive_alerts"] > 0
    assert m["false_positive_alerts"] > 0


def test_removing_the_planted_signal_removes_most_of_the_benefit():
    results = history_sensitivity(n_test_seeds=2)
    assert results["no_signal"]["fp_reduction_pct"] < results["planted_signal"]["fp_reduction_pct"]


def test_threshold_does_not_depend_on_test_data():
    one = evaluate(n_test_seeds=1)
    two = evaluate(n_test_seeds=2)
    assert one["risk_threshold"] == two["risk_threshold"]


def test_evaluation_never_writes_the_saved_model(monkeypatch):
    paths = []
    real_train = evaluate_module.train_model

    def spy(alerts, txns, path):
        paths.append(path)
        return real_train(alerts, txns, path=path)

    monkeypatch.setattr(evaluate_module, "train_model", spy)
    evaluate(n_test_seeds=1)
    assert paths
    assert DEFAULT_MODEL_PATH not in paths


def test_choose_threshold_keeps_target_recall():
    scores = np.array([90.0, 80.0, 70.0, 60.0, 50.0])
    labels = np.array([1, 1, 1, 1, 0])
    assert choose_threshold(scores, labels, 0.75) == 70.0
    assert choose_threshold(scores, labels, 1.0) == 60.0


def test_operating_point_percentages():
    scores = np.array([90.0, 80.0, 30.0, 20.0])
    labels = np.array([1, 0, 1, 0])
    point = operating_point(scores, labels, 50.0)
    assert point == {"recall": 50.0, "fp_reduction": 50.0, "review_reduction": 50.0}


def test_entity_history_excludes_later_transactions():
    earlier = txn("t1", "ACC1", "B", 100, days=0)
    trigger = txn("t2", "ACC1", "B", 200, days=1)
    later = txn("t3", "ACC1", "B", 900000, days=2)
    alert = Alert(
        alert_id="a",
        rule_id=Typology.VELOCITY_SPIKE,
        entity_id="ACC1",
        triggering_txn_ids=["t2"],
        severity=Severity.MEDIUM,
        created_at=trigger.timestamp,
    )
    txns = [earlier, trigger, later]
    row = build_feature_row(alert, {t.txn_id: t for t in txns}, _index_by_entity(txns), set())
    assert row[FEATURE_NAMES.index("entity_txn_count")] == 2
    assert row[FEATURE_NAMES.index("entity_total_volume")] == 300


def test_every_rule_can_produce_a_false_positive():
    txns, alerts = _data()
    by_id = {t.txn_id: t for t in txns}
    false_positive_rules = {a.rule_id for a in alerts if alert_label(a, by_id) == 0}
    enabled = {a.rule_id for a in alerts}
    assert false_positive_rules == enabled


def test_laundering_and_look_alikes_share_amount_ranges():
    df = generate_dataset(seed=1, scale=20, benign=0)
    outflows = df[df["sender_account"].str.startswith(("LAYER_ACC", "CORP"))]
    rounds = outflows[outflows["amount"] % 1000 == 0]
    assert set(rounds[rounds["is_laundering"] == 1]["amount"]) == set(
        rounds[rounds["is_laundering"] == 0]["amount"]
    )
