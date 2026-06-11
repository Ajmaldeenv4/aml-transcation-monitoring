"""Tests for ingestion + generator round-trip and rule integration."""

from __future__ import annotations

from sentinel.generator import generate_dataset
from sentinel.ingestion import load_transactions, normalise_frame
from sentinel.models import TransactionType, Typology
from sentinel.rules import run_rules

RUN_CONFIG = {
    "reporting_threshold": 10000,
    "rules": {
        "structuring": {"enabled": True, "band_lower": 9000, "band_upper": 9999, "min_count": 3, "window_hours": 72, "severity": "high"},
        "rapid_movement": {"enabled": True, "outflow_ratio": 0.90, "window_hours": 48, "min_amount": 5000, "severity": "high"},
        "round_amount": {"enabled": True, "round_multiple": 1000, "min_count": 3, "window_hours": 168, "severity": "medium"},
        "threshold_avoidance": {"enabled": True, "proximity": 0.05, "min_count": 2, "window_hours": 168, "severity": "medium"},
        "high_risk_geography": {"enabled": True, "min_amount": 1000, "severity": "high"},
        "velocity_spike": {"enabled": True, "multiplier": 3.0, "recent_window_hours": 24, "baseline_window_days": 30, "min_baseline_txns": 5, "severity": "medium"},
        "network_ring": {"enabled": True, "min_cycle_length": 3, "max_cycle_length": 6, "window_hours": 168, "severity": "high"},
    },
}


def test_generator_is_reproducible():
    a = generate_dataset(seed=7)
    b = generate_dataset(seed=7)
    assert a.equals(b)


def test_generator_has_ground_truth_labels():
    df = generate_dataset()
    assert df["is_laundering"].sum() > 0
    assert set(df["is_laundering"].unique()) <= {0, 1}


def test_ingestion_preserves_enum_txn_types():
    df = generate_dataset()
    txns = load_transactions(normalise_frame(df))
    # The structuring injections are cash deposits — must survive coercion.
    assert any(t.txn_type is TransactionType.CASH_DEPOSIT for t in txns)


def test_every_enabled_typology_fires_on_synthetic_data():
    df = generate_dataset()
    txns = load_transactions(normalise_frame(df))
    alerts = run_rules(txns, RUN_CONFIG)
    fired = {a.rule_id for a in alerts}
    for typ in Typology:
        assert typ in fired, f"no alert fired for {typ.value}"
