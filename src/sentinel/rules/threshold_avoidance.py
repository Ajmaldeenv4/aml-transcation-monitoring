"""Threshold Avoidance detection.

Typology: transactions repeatedly sized just below a KYC/EDD or reporting trigger
(any channel, not only cash — distinguishing it from structuring). We flag
accounts with repeated transactions in the narrow band just under the reporting
threshold within the window.
"""

from __future__ import annotations

from collections import defaultdict

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.THRESHOLD_AVOIDANCE


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("threshold_avoidance", {})
    if not cfg.get("enabled", False):
        return []

    threshold = config.get("reporting_threshold", 10000)
    proximity = cfg.get("proximity", 0.05)
    lower = threshold * (1 - proximity)
    min_count = cfg.get("min_count", 2)
    window = cfg.get("window_hours", 168) * 3600
    severity = severity_from_config(cfg.get("severity"))

    by_account: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if lower <= t.amount < threshold:
            by_account[t.sender_account].append(t)

    alerts: list[Alert] = []
    for account, txns in by_account.items():
        ordered = sort_by_time(txns)
        window_txns = _first_window(ordered, window, min_count)
        if window_txns:
            alerts.append(
                build_alert(
                    RULE_ID,
                    account,
                    window_txns,
                    severity,
                    evidence={
                        "count": len(window_txns),
                        "threshold": threshold,
                        "band": [round(lower, 2), threshold],
                        "amounts": [round(t.amount, 2) for t in window_txns],
                    },
                )
            )
    return alerts


def _first_window(
    ordered: list[Transaction], window_seconds: int, min_count: int
) -> list[Transaction]:
    start = 0
    for end in range(len(ordered)):
        while (
            ordered[end].timestamp - ordered[start].timestamp
        ).total_seconds() > window_seconds:
            start += 1
        if end - start + 1 >= min_count:
            return ordered[start : end + 1]
    return []
