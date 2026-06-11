"""Velocity Spike detection.

Typology: a sudden, anomalous jump in a customer's (here, an account's)
transaction value relative to that account's own historical baseline. We compute
a baseline mean over an earlier window and flag when a recent window's total
exceeds the baseline by a configured multiplier. This is a per-entity,
behaviour-relative scenario — the essence of a risk-based approach.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.VELOCITY_SPIKE


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("velocity_spike", {})
    if not cfg.get("enabled", False):
        return []

    multiplier = cfg.get("multiplier", 3.0)
    recent_window = timedelta(hours=cfg.get("recent_window_hours", 24))
    baseline_days = cfg.get("baseline_window_days", 30)
    min_baseline_txns = cfg.get("min_baseline_txns", 5)
    severity = severity_from_config(cfg.get("severity"))

    by_account: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        by_account[t.sender_account].append(t)

    alerts: list[Alert] = []
    for account, txns in by_account.items():
        ordered = sort_by_time(txns)
        if len(ordered) <= min_baseline_txns:
            continue
        latest = ordered[-1].timestamp
        recent_start = latest - recent_window
        baseline_start = latest - timedelta(days=baseline_days)

        recent = [t for t in ordered if t.timestamp >= recent_start]
        baseline = [t for t in ordered if baseline_start <= t.timestamp < recent_start]
        if len(baseline) < min_baseline_txns or not recent:
            continue

        # Average the baseline total over its *observed* span (first baseline txn to
        # the start of the recent window), measured in recent-window units. Using the
        # observed span rather than the full configured window avoids treating sparse
        # but steady activity as a spike.
        baseline_span_windows = max(
            (recent_start - baseline[0].timestamp) / recent_window, 1.0
        )
        baseline_total = sum(t.amount for t in baseline)
        baseline_per_window = baseline_total / baseline_span_windows
        recent_total = sum(t.amount for t in recent)

        if baseline_per_window > 0 and recent_total >= multiplier * baseline_per_window:
            alerts.append(
                build_alert(
                    RULE_ID,
                    account,
                    recent,
                    severity,
                    evidence={
                        "recent_total": round(recent_total, 2),
                        "baseline_per_window": round(baseline_per_window, 2),
                        "ratio": round(recent_total / baseline_per_window, 2),
                        "recent_txn_count": len(recent),
                    },
                )
            )
    return alerts
