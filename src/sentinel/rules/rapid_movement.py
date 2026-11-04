"""Rapid Movement of Funds (in-out / pass-through) detection.

Typology: an account receives a credit and then moves most of it out again
within a short window — the account is used as a conduit rather than to hold
value. For each sizeable inbound credit we check whether the account's outflow
in the following window covers a high fraction of it. Credits are matched to
outflows oldest-first and each unit of outflow is matched once, so one payment
cannot explain several credits. Self-transfers are ignored.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import timedelta

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.RAPID_MOVEMENT


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("rapid_movement", {})
    if not cfg.get("enabled", False):
        return []

    outflow_ratio = cfg.get("outflow_ratio", 0.90)
    window = timedelta(hours=cfg.get("window_hours", 48))
    min_amount = cfg.get("min_amount", 5000)
    severity = severity_from_config(cfg.get("severity"))

    inflows: dict[str, list[Transaction]] = defaultdict(list)
    outflows: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.sender_account == t.receiver_account:
            continue
        outflows[t.sender_account].append(t)
        inflows[t.receiver_account].append(t)

    alerts: list[Alert] = []
    for account, credits in inflows.items():
        outs = sort_by_time(outflows.get(account, []))
        out_times = [o.timestamp for o in outs]
        unmatched = [o.amount for o in outs]  # outflow value not yet tied to a credit
        for credit in sort_by_time(credits):
            if credit.amount < min_amount:
                continue
            candidates = range(
                bisect_left(out_times, credit.timestamp),
                bisect_right(out_times, credit.timestamp + window),
            )
            if sum(unmatched[i] for i in candidates) < outflow_ratio * credit.amount:
                continue

            remaining = credit.amount
            matched_outs: list[Transaction] = []
            for i in candidates:
                taken = min(unmatched[i], remaining)
                if taken <= 0:
                    continue
                unmatched[i] -= taken
                remaining -= taken
                matched_outs.append(outs[i])

            matched_total = credit.amount - remaining
            alerts.append(
                build_alert(
                    RULE_ID,
                    account,
                    [credit, *matched_outs],
                    severity,
                    evidence={
                        "inbound_amount": round(credit.amount, 2),
                        "outbound_amount": round(matched_total, 2),
                        "outflow_ratio": round(matched_total / credit.amount, 3),
                        "window_hours": cfg.get("window_hours", 48),
                    },
                )
            )
    return alerts
