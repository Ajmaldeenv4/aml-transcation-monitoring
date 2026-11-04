"""Tests for ingestion + generator round-trip and rule integration."""

from __future__ import annotations

import pandas as pd
import pytest

from sentinel.config import load_high_risk_countries
from sentinel.generator import generate_dataset
from sentinel.ingestion import load_transactions, normalise_frame, read_saml_d_frame
from sentinel.ingestion.loader import UNKNOWN_COUNTRY, _coerce_country
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


def _saml_d_shaped_csv(tmp_path):
    """A tiny CSV with SAML-D's columns: 4 laundering + 100 normal rows."""
    rows = []
    for i in range(4):
        rows.append(["10:00:00", "2022-10-07", f"S{i}", f"R{i}", 9000 + i,
                     "US dollar", "US dollar", "USA", "Nigeria", "Cross-border", 1, "Layered_Fan_Out"])
    for i in range(100):
        rows.append(["11:00:00", "2022-10-07", f"S{i}", f"R{i}", 100 + i,
                     "US dollar", "US dollar", "USA", "UK", "Cash Deposit", 0, "Normal"])
    cols = ["Time", "Date", "Sender_account", "Receiver_account", "Amount",
            "Payment_currency", "Received_currency", "Sender_bank_location",
            "Receiver_bank_location", "Payment_type", "Is_laundering", "Laundering_type"]
    path = tmp_path / "SAML-D.csv"
    pd.DataFrame(rows, columns=cols).to_csv(path, index=False)
    return path


def test_saml_d_sampling_keeps_all_laundering_rows(tmp_path):
    path = _saml_d_shaped_csv(tmp_path)
    # Sample 0% of normals but keep every laundering row -> exactly the 4 positives.
    frame = read_saml_d_frame(path, sample_frac=0.0, keep_laundering=True, seed=1)
    assert int(frame["Is_laundering"].sum()) == 4
    assert (frame["Is_laundering"] == 0).sum() == 0
    assert "timestamp" in frame.columns


def test_saml_d_sampling_is_reproducible(tmp_path):
    path = _saml_d_shaped_csv(tmp_path)
    a = read_saml_d_frame(path, sample_frac=0.3, seed=42)
    b = read_saml_d_frame(path, sample_frac=0.3, seed=42)
    assert len(a) == len(b)
    assert int(a["Is_laundering"].sum()) == 4  # all positives retained either way


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Turkey", "TR"),
        ("Morocco", "MA"),
        ("Nigeria", "NG"),
        ("Mexico", "MX"),
        ("Pakistan", "PK"),
        ("Germany", "DE"),
        ("Switzerland", "CH"),
        ("UAE", "AE"),
        ("UK", "GB"),
        ("Myanmar", "MM"),
        ("North Korea", "KP"),
    ],
)
def test_country_names_map_to_iso_codes(name, code):
    assert _coerce_country(name) == code


def test_country_names_do_not_collide_with_watchlist():
    watchlist = load_high_risk_countries()
    for name in ("Ireland", "Iraq", "Sweden", "Malaysia"):
        assert _coerce_country(name) not in watchlist


def test_unmapped_country_is_not_truncated():
    assert _coerce_country("Atlantis") == "ATLANTIS"
    assert _coerce_country("DE") == "DE"


def test_missing_country_is_marked_unknown():
    assert _coerce_country(float("nan")) == UNKNOWN_COUNTRY
    assert _coerce_country("  ") == UNKNOWN_COUNTRY
