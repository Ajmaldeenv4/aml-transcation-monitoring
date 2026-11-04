"""Structuring / Smurfing detection.

Typology: multiple cash transactions deliberately sized just under a reporting
threshold (e.g. 9,000-9,999 when the threshold is 10,000) within a short window,
to avoid triggering a Currency Transaction Report. We group by the customer's
account (the receiver of a deposit, the sender of a withdrawal) and slide a time
window over its in-band cash transactions.
"""

from __future__ import annotations

from collections import defaultdict

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import (
    build_alert,
    customer_account,
    find_bursts,
    severity_from_config,
    sort_by_time,
)

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
            by_account[customer_account(t)].append(t)

    alerts: list[Alert] = []
    for account, txns in by_account.items():
        for burst in find_bursts(sort_by_time(txns), window, min_count):
            alerts.append(
                build_alert(
                    RULE_ID,
                    account,
                    burst,
                    severity,
                    evidence={
                        "count": len(burst),
                        "total_amount": round(sum(t.amount for t in burst), 2),
                        "band": [band_lower, band_upper],
                        "window_hours": cfg.get("window_hours", 72),
                    },
                )
            )
    return alerts
