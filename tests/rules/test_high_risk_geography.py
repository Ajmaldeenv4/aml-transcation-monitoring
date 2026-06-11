"""Golden cases for the high-risk-geography rule."""

from __future__ import annotations

from tests.conftest import txn

from sentinel.models import Typology
from sentinel.rules import high_risk_geography

CONFIG = {
    "rules": {
        "high_risk_geography": {
            "enabled": True,
            "min_amount": 1000,
            "severity": "high",
        }
    },
}
WATCHLIST = {"IR", "KP", "SY"}


def test_positive_outbound_to_high_risk():
    txns = [txn("t1", "ACC1", "FOR", 5000, receiver_country="IR")]
    alerts = high_risk_geography.detect(txns, CONFIG, high_risk=WATCHLIST)
    assert len(alerts) == 1
    assert alerts[0].rule_id is Typology.HIGH_RISK_GEOGRAPHY
    assert alerts[0].entity_id == "ACC1"
    assert alerts[0].evidence["flagged_country"] == "IR"
    assert alerts[0].evidence["direction"] == "outbound"


def test_positive_inbound_from_high_risk():
    txns = [txn("t1", "FOR", "ACC1", 5000, sender_country="KP")]
    alerts = high_risk_geography.detect(txns, CONFIG, high_risk=WATCHLIST)
    assert len(alerts) == 1
    assert alerts[0].entity_id == "ACC1"
    assert alerts[0].evidence["direction"] == "inbound"


def test_negative_domestic():
    txns = [txn("t1", "ACC1", "ACC2", 5000)]
    assert high_risk_geography.detect(txns, CONFIG, high_risk=WATCHLIST) == []


def test_negative_below_min_amount():
    txns = [txn("t1", "ACC1", "FOR", 500, receiver_country="IR")]
    assert high_risk_geography.detect(txns, CONFIG, high_risk=WATCHLIST) == []
