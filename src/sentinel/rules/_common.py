"""Shared helpers for rule modules."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import datetime

from sentinel.models import Alert, Severity, Transaction, Typology

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


def earliest_timestamp(txns: Iterable[Transaction]) -> datetime:
    return min(t.timestamp for t in txns)


def sort_by_time(txns: Iterable[Transaction]) -> list[Transaction]:
    return sorted(txns, key=lambda t: t.timestamp)


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
