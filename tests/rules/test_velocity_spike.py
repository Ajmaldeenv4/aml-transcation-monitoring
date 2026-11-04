"""Golden cases for the velocity-spike rule."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import Typology
from sentinel.rules import velocity_spike

CONFIG = {
    "rules": {
        "velocity_spike": {
            "enabled": True,
            "multiplier": 3.0,
            "recent_window_hours": 24,
            "baseline_window_days": 30,
            "min_baseline_txns": 5,
            "severity": "medium",
        }
    },
}


def test_positive_recent_surge_over_baseline():
    # Quiet baseline: small daily transactions over ~28 days.
    txns = [
        txn(f"b{i}", "ACC1", "B", 200, days=i) for i in range(6)
    ]
    # Recent surge in the final 24h.
    txns += [
        txn("s1", "ACC1", "B", 9000, days=28, hours=1),
        txn("s2", "ACC1", "B", 9000, days=28, hours=5),
    ]
    alerts = velocity_spike.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert alerts[0].rule_id is Typology.VELOCITY_SPIKE
    assert alerts[0].entity_id == "ACC1"
    assert alerts[0].evidence["ratio"] >= 3.0


def test_negative_steady_activity():
    txns = [txn(f"b{i}", "ACC1", "B", 500, days=i) for i in range(10)]
    assert velocity_spike.detect(txns, CONFIG) == []


def test_negative_insufficient_baseline():
    txns = [
        txn("b0", "ACC1", "B", 200, days=0),
        txn("s1", "ACC1", "B", 9000, days=1),
    ]
    assert velocity_spike.detect(txns, CONFIG) == []


def test_negative_sparse_steady_activity():
    # Same $100 every five days: each payment dwarfs a calendar-day average, but
    # it is exactly what this account normally does.
    txns = [txn(f"b{i}", "ACC1", "B", 100, days=i * 5) for i in range(6)]
    assert velocity_spike.detect(txns, CONFIG) == []


def test_positive_spike_followed_by_normal_activity():
    txns = [txn(f"b{i}", "ACC1", "B", 100, days=i) for i in range(10)]
    txns += [txn(f"s{i}", "ACC1", "B", 50000, days=10, hours=i) for i in range(4)]
    txns.append(txn("later", "ACC1", "B", 100, days=13))
    alerts = velocity_spike.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert alerts[0].evidence["recent_txn_count"] == 4
    assert alerts[0].evidence["recent_total"] == 200000


def test_separate_spikes_alert_separately():
    txns = [txn(f"b{i}", "ACC1", "B", 100, days=i) for i in range(10)]
    txns.append(txn("s1", "ACC1", "B", 5000, days=10))
    txns.append(txn("s2", "ACC1", "B", 50000, days=14))
    assert len(velocity_spike.detect(txns, CONFIG)) == 2
