"""Structuring / Smurfing detection.

Typology: multiple cash transactions deliberately sized just under a reporting
threshold (e.g. 9,000-9,999 when the threshold is 10,000) within a short window,
to avoid triggering a Currency Transaction Report. We group by the depositing
account and slide a time window over its in-band cash transactions.
"""

from __future__ import annotations

from collections import defaultdict

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.STRUCTURING


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("structuring", {})
    if not cfg.get("enabled", False):
        return []

    band_lower = cfg.get("band_lower", 9000)
    band_upper = cfg.get("band_upper", 9999)
    min_count = cfg.get("min_count", 3)
    window = cfg.get("window_hours", 72) * 3600
    severity = severity_from_config(cfg.get("severity"))

    # Cash transactions whose amount sits in the just-under-threshold band.
    by_account: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.txn_type.is_cash and band_lower <= t.amount <= band_upper:
            by_account[t.receiver_account or t.sender_account].append(t)

    alerts: list[Alert] = []
    for account, txns in by_account.items():
        ordered = sort_by_time(txns)
        window_txns = _sliding_window(ordered, window, min_count)
        if window_txns:
            alerts.append(
                build_alert(
                    RULE_ID,
                    account,
                    window_txns,
                    severity,
                    evidence={
                        "count": len(window_txns),
                        "total_amount": round(sum(t.amount for t in window_txns), 2),
                        "band": [band_lower, band_upper],
                        "window_hours": cfg.get("window_hours", 72),
                    },
                )
            )
    return alerts


def _sliding_window(
    ordered: list[Transaction], window_seconds: int, min_count: int
) -> list[Transaction]:
    """Return the first set of >= min_count txns falling within window_seconds."""
    start = 0
    for end in range(len(ordered)):
        while (
            ordered[end].timestamp - ordered[start].timestamp
        ).total_seconds() > window_seconds:
            start += 1
        if end - start + 1 >= min_count:
            return ordered[start : end + 1]
    return []
