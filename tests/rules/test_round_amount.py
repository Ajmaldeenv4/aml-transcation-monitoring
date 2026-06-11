"""Golden cases for the round-amount layering rule."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import Typology
from sentinel.rules import round_amount

CONFIG = {
    "rules": {
        "round_amount": {
            "enabled": True,
            "round_multiple": 1000,
            "min_count": 3,
            "window_hours": 168,
            "severity": "medium",
        }
    },
}


def test_positive_three_round_transfers_same_pair():
    txns = [
        txn("t1", "ACC1", "ACC2", 5000, hours=0),
        txn("t2", "ACC1", "ACC2", 3000, hours=24),
        txn("t3", "ACC1", "ACC2", 8000, hours=48),
    ]
    alerts = round_amount.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert alerts[0].rule_id is Typology.ROUND_AMOUNT
    assert alerts[0].evidence["counterparty"] == "ACC2"


def test_negative_non_round_amounts():
    txns = [
        txn("t1", "ACC1", "ACC2", 5050, hours=0),
        txn("t2", "ACC1", "ACC2", 3025, hours=24),
        txn("t3", "ACC1", "ACC2", 8123, hours=48),
    ]
    assert round_amount.detect(txns, CONFIG) == []


def test_negative_spread_across_different_counterparties():
    txns = [
        txn("t1", "ACC1", "ACC2", 5000, hours=0),
        txn("t2", "ACC1", "ACC3", 3000, hours=24),
        txn("t3", "ACC1", "ACC4", 8000, hours=48),
    ]
    assert round_amount.detect(txns, CONFIG) == []
