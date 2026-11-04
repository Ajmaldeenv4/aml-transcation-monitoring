"""Golden cases for the network/mule-ring rule (advanced)."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import Typology
from sentinel.rules import network_ring

CONFIG = {
    "rules": {
        "network_ring": {
            "enabled": True,
            "min_cycle_length": 3,
            "max_cycle_length": 6,
            "window_hours": 168,
            "severity": "high",
        }
    },
}


def test_positive_three_account_cycle():
    txns = [
        txn("t1", "A", "B", 5000, hours=0),
        txn("t2", "B", "C", 4800, hours=10),
        txn("t3", "C", "A", 4700, hours=20),
    ]
    alerts = network_ring.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert alerts[0].rule_id is Typology.NETWORK_RING
    assert alerts[0].evidence["cycle_length"] == 3


def test_negative_no_cycle():
    txns = [
        txn("t1", "A", "B", 5000, hours=0),
        txn("t2", "B", "C", 4800, hours=10),
    ]
    assert network_ring.detect(txns, CONFIG) == []


def test_negative_disabled_by_default():
    txns = [
        txn("t1", "A", "B", 5000, hours=0),
        txn("t2", "B", "C", 4800, hours=10),
        txn("t3", "C", "A", 4700, hours=20),
    ]
    assert network_ring.detect(txns, {"rules": {"network_ring": {"enabled": False}}}) == []


def test_positive_recent_ring_on_an_old_relationship():
    txns = [
        txn("old", "A", "B", 50, days=0),
        txn("t1", "A", "B", 5000, days=100),
        txn("t2", "B", "C", 4900, days=101),
        txn("t3", "C", "A", 4800, days=102),
    ]
    alerts = network_ring.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert sorted(alerts[0].triggering_txn_ids) == ["t1", "t2", "t3"]


def test_negative_legs_never_share_a_window():
    txns = [
        txn("t1", "A", "B", 5000, days=0),
        txn("t2", "B", "C", 4900, days=30),
        txn("t3", "C", "A", 4800, days=60),
    ]
    assert network_ring.detect(txns, CONFIG) == []
