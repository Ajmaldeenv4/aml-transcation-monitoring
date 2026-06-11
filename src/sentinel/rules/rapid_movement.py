"""Rapid Movement of Funds (in-out / pass-through) detection.

Typology: an account receives a credit and then moves most of it out again
within a short window — the account is used as a conduit rather than to hold
value. For each sizeable inbound credit we check whether the account's outflow
in the following window covers a high fraction of it.
"""

from __future__ import annotations

from collections import defaultdict

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.RAPID_MOVEMENT


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("rapid_movement", {})
    if not cfg.get("enabled", False):
        return []

    outflow_ratio = cfg.get("outflow_ratio", 0.90)
    window = cfg.get("window_hours", 48) * 3600
    min_amount = cfg.get("min_amount", 5000)
    severity = severity_from_config(cfg.get("severity"))

    inflows: dict[str, list[Transaction]] = defaultdict(list)
    outflows: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        outflows[t.sender_account].append(t)
        inflows[t.receiver_account].append(t)

    alerts: list[Alert] = []
    seen_alert_ids: set[str] = set()
    for account, credits in inflows.items():
        outs = sort_by_time(outflows.get(account, []))
        for credit in credits:
            if credit.amount < min_amount:
                continue
            following = [
                o
                for o in outs
                if 0 <= (o.timestamp - credit.timestamp).total_seconds() <= window
            ]
            out_total = sum(o.amount for o in following)
            if out_total >= outflow_ratio * credit.amount and following:
                txns = [credit, *following]
                alert = build_alert(
                    RULE_ID,
                    account,
                    txns,
                    severity,
                    evidence={
                        "inbound_amount": round(credit.amount, 2),
                        "outbound_amount": round(out_total, 2),
                        "outflow_ratio": round(out_total / credit.amount, 3),
                        "window_hours": cfg.get("window_hours", 48),
                    },
                )
                if alert.alert_id not in seen_alert_ids:
                    seen_alert_ids.add(alert.alert_id)
                    alerts.append(alert)
    return alerts
