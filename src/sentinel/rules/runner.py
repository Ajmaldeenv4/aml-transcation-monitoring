"""Run all enabled typology rules and aggregate their alerts."""

from __future__ import annotations

from collections.abc import Callable

from sentinel.config import load_rules_config
from sentinel.models import Alert, Transaction
from sentinel.rules import (
    high_risk_geography,
    network_ring,
    rapid_movement,
    round_amount,
    structuring,
    threshold_avoidance,
    velocity_spike,
)

# Registry of detectors. Each is (transactions, config) -> list[Alert].
DETECTORS: list[Callable[[list[Transaction], dict], list[Alert]]] = [
    structuring.detect,
    rapid_movement.detect,
    round_amount.detect,
    threshold_avoidance.detect,
    high_risk_geography.detect,
    velocity_spike.detect,
    network_ring.detect,
]


def run_rules(
    transactions: list[Transaction], config: dict | None = None
) -> list[Alert]:
    """Run every enabled rule and return all alerts, sorted by severity then time."""
    cfg = config if config is not None else load_rules_config()
    alerts: list[Alert] = []
    for detect in DETECTORS:
        alerts.extend(detect(transactions, cfg))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: (severity_rank[a.severity.value], a.created_at))
    return alerts
