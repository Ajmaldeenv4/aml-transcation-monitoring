"""Golden cases for the structuring / smurfing rule."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import TransactionType, Typology
from sentinel.rules import structuring

CONFIG = {
    "reporting_threshold": 10000,
    "rules": {
        "structuring": {
            "enabled": True,
            "band_lower": 9000,
            "band_upper": 9999,
            "min_count": 3,
            "window_hours": 72,
            "severity": "high",
        }
    },
}


def test_positive_three_in_band_cash_deposits_within_window():
    txns = [
        txn("t1", "X", "ACC1", 9100, hours=0, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t2", "X", "ACC1", 9500, hours=10, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t3", "X", "ACC1", 9900, hours=20, txn_type=TransactionType.CASH_DEPOSIT),
    ]
    alerts = structuring.detect(txns, CONFIG)
    assert len(alerts) == 1
    assert alerts[0].rule_id is Typology.STRUCTURING
    assert alerts[0].entity_id == "ACC1"
    assert alerts[0].evidence["count"] == 3


def test_negative_only_two_in_band():
    txns = [
        txn("t1", "X", "ACC1", 9100, hours=0, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t2", "X", "ACC1", 9500, hours=10, txn_type=TransactionType.CASH_DEPOSIT),
    ]
    assert structuring.detect(txns, CONFIG) == []


def test_negative_outside_window():
    txns = [
        txn("t1", "X", "ACC1", 9100, hours=0, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t2", "X", "ACC1", 9500, hours=10, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t3", "X", "ACC1", 9900, days=10, txn_type=TransactionType.CASH_DEPOSIT),
    ]
    assert structuring.detect(txns, CONFIG) == []


def test_negative_non_cash_ignored():
    txns = [
        txn("t1", "X", "ACC1", 9100, hours=0, txn_type=TransactionType.TRANSFER),
        txn("t2", "X", "ACC1", 9500, hours=10, txn_type=TransactionType.TRANSFER),
        txn("t3", "X", "ACC1", 9900, hours=20, txn_type=TransactionType.TRANSFER),
    ]
    assert structuring.detect(txns, CONFIG) == []


def test_negative_amounts_above_band():
    txns = [
        txn("t1", "X", "ACC1", 10500, hours=0, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t2", "X", "ACC1", 11000, hours=10, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t3", "X", "ACC1", 12000, hours=20, txn_type=TransactionType.CASH_DEPOSIT),
    ]
    assert structuring.detect(txns, CONFIG) == []


def test_disabled_returns_nothing():
    cfg = {"rules": {"structuring": {"enabled": False}}}
    txns = [
        txn("t1", "X", "ACC1", 9100, hours=0, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t2", "X", "ACC1", 9500, hours=10, txn_type=TransactionType.CASH_DEPOSIT),
        txn("t3", "X", "ACC1", 9900, hours=20, txn_type=TransactionType.CASH_DEPOSIT),
    ]
    assert structuring.detect(txns, cfg) == []


def test_withdrawals_attributed_to_the_customer_account():
    txns = [
        txn(f"t{i}", "ACC1", "TELLER", 9500, hours=i, txn_type=TransactionType.CASH_WITHDRAWAL)
        for i in range(3)
    ]
    alerts = structuring.detect(txns, CONFIG)
    assert [a.entity_id for a in alerts] == ["ACC1"]


def test_negative_unrelated_customers_at_same_atm():
    txns = [
        txn(f"t{i}", f"CUST{i}", "ATM", 9500, hours=i, txn_type=TransactionType.CASH_WITHDRAWAL)
        for i in range(3)
    ]
    assert structuring.detect(txns, CONFIG) == []


def test_alert_covers_whole_burst_and_later_bursts():
    txns = [
        txn(f"a{i}", "X", "ACC1", 9500, hours=i, txn_type=TransactionType.CASH_DEPOSIT)
        for i in range(10)
    ]
    txns += [
        txn(f"b{i}", "X", "ACC1", 9500, days=30, hours=i, txn_type=TransactionType.CASH_DEPOSIT)
        for i in range(5)
    ]
    alerts = sorted(structuring.detect(txns, CONFIG), key=lambda a: a.created_at)
    assert [a.evidence["count"] for a in alerts] == [10, 5]
    assert alerts[0].evidence["total_amount"] == 95000
