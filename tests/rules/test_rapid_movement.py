"""Golden cases for the rapid-movement (pass-through) rule."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import Typology
from sentinel.rules import rapid_movement

CONFIG = {
    "rules": {
        "rapid_movement": {
            "enabled": True,
            "outflow_ratio": 0.90,
            "window_hours": 48,
            "min_amount": 5000,
            "severity": "high",
        }
    },
}


def test_positive_credit_then_mostly_out():
    txns = [
        txn("in", "EXT", "ACC1", 20000, hours=0),
        txn("out1", "ACC1", "B", 12000, hours=2),
        txn("out2", "ACC1", "C", 7000, hours=5),
    ]
    alerts = rapid_movement.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert alerts[0].rule_id is Typology.RAPID_MOVEMENT
    assert alerts[0].entity_id == "ACC1"
    assert alerts[0].evidence["outflow_ratio"] >= 0.90


def test_negative_funds_retained():
    txns = [
        txn("in", "EXT", "ACC1", 20000, hours=0),
        txn("out1", "ACC1", "B", 3000, hours=2),
    ]
    assert rapid_movement.detect(txns, CONFIG) == []


def test_negative_outflow_too_late():
    txns = [
        txn("in", "EXT", "ACC1", 20000, hours=0),
        txn("out1", "ACC1", "B", 19000, days=5),
    ]
    assert rapid_movement.detect(txns, CONFIG) == []


def test_negative_below_min_amount():
    txns = [
        txn("in", "EXT", "ACC1", 4000, hours=0),
        txn("out1", "ACC1", "B", 3900, hours=2),
    ]
    assert rapid_movement.detect(txns, CONFIG) == []
