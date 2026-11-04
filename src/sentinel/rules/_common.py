"""Shared helpers for rule modules."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import datetime

from sentinel.models import Alert, Severity, Transaction, TransactionType, Typology

_SEVERITY_MAP = {"low": Severity.LOW, "medium": Severity.MEDIUM, "high": Severity.HIGH}


def severity_from_config(value: str | None, default: Severity = Severity.MEDIUM) -> Severity:
    if value is None:
        return default
    return _SEVERITY_MAP.get(str(value).lower(), default)


def make_alert_id(rule_id: Typology, entity_id: str, txn_ids: Sequence[str]) -> str:
    """Deterministic alert id so re-running the engine is idempotent and testable."""
    digest = hashlib.sha1(  # noqa: S324 - non-cryptographic, just a stable id
        "|".join([rule_id.value, entity_id, *sorted(txn_ids)]).encode()
    ).hexdigest()[:12]
    return f"{rule_id.value}-{digest}"


def customer_account(t: Transaction) -> str:
    """The account whose behaviour this transaction shows: a deposit's receiver, else the sender."""
    return t.receiver_account if t.txn_type is TransactionType.CASH_DEPOSIT else t.sender_account


def earliest_timestamp(txns: Iterable[Transaction]) -> datetime:
    return min(t.timestamp for t in txns)


def sort_by_time(txns: Iterable[Transaction]) -> list[Transaction]:
    return sorted(txns, key=lambda t: t.timestamp)


def find_bursts(
    ordered: Sequence[Transaction], window_seconds: float, min_count: int
) -> list[list[Transaction]]:
    """Return every non-overlapping burst of >= min_count txns inside the window.

    ``ordered`` must be time-sorted. Each burst keeps all transactions that fall
    within the window of its first transaction, so evidence reflects the full
    activity. Scanning resumes after a burst, so later episodes also alert.
    """
    bursts: list[list[Transaction]] = []
    start = 0
    end = 0
    while end < len(ordered):
        while (ordered[end].timestamp - ordered[start].timestamp).total_seconds() > window_seconds:
            start += 1
        if end - start + 1 >= min_count:
            while (
                end + 1 < len(ordered)
                and (ordered[end + 1].timestamp - ordered[start].timestamp).total_seconds()
                <= window_seconds
            ):
                end += 1
            bursts.append(list(ordered[start : end + 1]))
            start = end + 1
        end += 1
    return bursts


def build_alert(
    rule_id: Typology,
    entity_id: str,
    txns: Sequence[Transaction],
    severity: Severity,
    evidence: dict,
) -> Alert:
    txn_ids = [t.txn_id for t in txns]
    return Alert(
        alert_id=make_alert_id(rule_id, entity_id, txn_ids),
        rule_id=rule_id,
        entity_id=entity_id,
        triggering_txn_ids=txn_ids,
        severity=severity,
        created_at=earliest_timestamp(txns),
        evidence=evidence,
    )
