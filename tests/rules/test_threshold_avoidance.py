"""Golden cases for the threshold-avoidance rule."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import Typology
from sentinel.rules import threshold_avoidance

CONFIG = {
    "reporting_threshold": 10000,
    "rules": {
        "threshold_avoidance": {
            "enabled": True,
            "proximity": 0.05,  # band 9500-9999
            "min_count": 2,
            "window_hours": 168,
            "severity": "medium",
        }
    },
}


def test_positive_two_just_below_threshold():
    txns = [
        txn("t1", "ACC1", "B", 9600, hours=0),
        txn("t2", "ACC1", "C", 9900, hours=24),
    ]
    alerts = threshold_avoidance.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert alerts[0].rule_id is Typology.THRESHOLD_AVOIDANCE
    assert alerts[0].entity_id == "ACC1"


def test_negative_below_band():
    txns = [
        txn("t1", "ACC1", "B", 8000, hours=0),
        txn("t2", "ACC1", "C", 8500, hours=24),
    ]
    assert threshold_avoidance.detect(txns, CONFIG) == []


def test_negative_at_or_above_threshold():
    txns = [
        txn("t1", "ACC1", "B", 10000, hours=0),
        txn("t2", "ACC1", "C", 11000, hours=24),
    ]
    assert threshold_avoidance.detect(txns, CONFIG) == []
