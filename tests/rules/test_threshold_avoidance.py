"""Golden cases for the threshold-avoidance rule."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import TransactionType, Typology
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


def test_alert_covers_whole_burst_and_later_bursts():
    txns = [txn(f"a{i}", "ACC1", "B", 9600, hours=i) for i in range(4)]
    txns += [txn(f"b{i}", "ACC1", "B", 9600, days=30, hours=i) for i in range(2)]
    alerts = sorted(threshold_avoidance.detect(txns, CONFIG), key=lambda a: a.created_at)
    assert [a.evidence["count"] for a in alerts] == [4, 2]


def test_cash_deposits_attributed_to_the_customer_account():
    txns = [
        txn("t1", "TILL", "ACC1", 9600, hours=0, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t2", "TILL", "ACC1", 9700, hours=24, txn_type=TransactionType.CASH_DEPOSIT),
    ]
    assert [a.entity_id for a in threshold_avoidance.detect(txns, CONFIG)] == ["ACC1"]


def test_negative_unrelated_customers_paid_in_at_same_till():
    txns = [
        txn("t1", "TILL", "ACC1", 9600, hours=0, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t2", "TILL", "ACC2", 9700, hours=24, txn_type=TransactionType.CASH_DEPOSIT),
    ]
    assert threshold_avoidance.detect(txns, CONFIG) == []
