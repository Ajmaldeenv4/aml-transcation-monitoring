"""Round-Amount Layering detection.

Typology: frequent, suspiciously round-number transfers between the same pair of
(often linked) accounts — a hallmark of layering, where launderers move value in
tidy chunks. We group transfers by (sender, receiver) pair and flag pairs with
enough round-amount transfers inside the window.
"""

from __future__ import annotations

from collections import defaultdict

from sentinel.models import Alert, Transaction, TransactionType, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.ROUND_AMOUNT


def _is_round(amount: float, multiple: int) -> bool:
    return multiple > 0 and amount % multiple == 0


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("round_amount", {})
    if not cfg.get("enabled", False):
        return []

    multiple = cfg.get("round_multiple", 1000)
    min_count = cfg.get("min_count", 3)
    window = cfg.get("window_hours", 168) * 3600
    severity = severity_from_config(cfg.get("severity"))

    by_pair: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.txn_type in (TransactionType.TRANSFER, TransactionType.WIRE) and _is_round(
            t.amount, multiple
        ):
            by_pair[(t.sender_account, t.receiver_account)].append(t)

    alerts: list[Alert] = []
    for (sender, _receiver), txns in by_pair.items():
        ordered = sort_by_time(txns)
        window_txns = _first_window(ordered, window, min_count)
        if window_txns:
            alerts.append(
                build_alert(
                    RULE_ID,
                    sender,
                    window_txns,
                    severity,
                    evidence={
                        "count": len(window_txns),
                        "total_amount": round(sum(t.amount for t in window_txns), 2),
                        "round_multiple": multiple,
                        "counterparty": window_txns[0].receiver_account,
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
