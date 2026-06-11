"""Tests for the case store: persistence, disposition, audit-trail immutability."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sentinel.models import (
    Alert,
    Disposition,
    DispositionStatus,
    Severity,
    Typology,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A CaseStore backed by a throwaway SQLite file per test."""
    db = tmp_path / "test.db"
    monkeypatch.setenv("SENTINEL_DB_URL", f"sqlite:///{db.as_posix()}")
    # Re-import db module so it picks up the env var with a fresh engine.
    import importlib

    import sentinel.casestore.db as dbmod

    importlib.reload(dbmod)
    import sentinel.casestore.repository as repo

    importlib.reload(repo)
    return repo.CaseStore()


def _alert(alert_id: str = "structuring-abc", **kw) -> Alert:
    defaults = {
        "alert_id": alert_id,
        "rule_id": Typology.STRUCTURING,
        "entity_id": "ACC1",
        "triggering_txn_ids": ["t1", "t2", "t3"],
        "severity": Severity.HIGH,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "evidence": {"count": 3},
    }
    defaults.update(kw)
    return Alert(**defaults)


def test_save_and_get_roundtrip(store):
    store.save_alerts([_alert()])
    got = store.get_alert("structuring-abc")
    assert got is not None
    assert got.rule_id is Typology.STRUCTURING
    assert got.triggering_txn_ids == ["t1", "t2", "t3"]


def test_save_is_idempotent(store):
    store.save_alerts([_alert()])
    written = store.save_alerts([_alert()])  # same id again
    assert written == 0
    assert len(store.list_alerts()) == 1


def test_disposition_updates_status_and_audits(store):
    store.save_alerts([_alert()])
    store.record_disposition(
        Disposition(
            alert_id="structuring-abc",
            status=DispositionStatus.ESCALATED,
            rationale="Clear structuring pattern across 3 sub-threshold deposits.",
            analyst="ajmal",
            decided_at=datetime.now(UTC),
        )
    )
    assert store.get_status("structuring-abc") == "escalated"
    trail = store.audit_trail("structuring-abc")
    assert any(e.action == "disposition" and e.actor == "ajmal" for e in trail)


def test_disposition_requires_rationale():
    with pytest.raises(ValidationError):
        Disposition(
            alert_id="x",
            status=DispositionStatus.FALSE_POSITIVE,
            rationale="",  # empty -> must fail validation
            analyst="ajmal",
            decided_at=datetime.now(UTC),
        )


def test_disposition_unknown_alert_raises(store):
    with pytest.raises(KeyError):
        store.record_disposition(
            Disposition(
                alert_id="does-not-exist",
                status=DispositionStatus.FALSE_POSITIVE,
                rationale="n/a",
                analyst="ajmal",
                decided_at=datetime.now(UTC),
            )
        )


def test_ranking_puts_scored_high_risk_first(store):
    store.save_alerts(
        [
            _alert("a-low", risk_score=10.0),
            _alert("a-high", risk_score=95.0),
            _alert("a-unscored"),  # no score -> last
        ]
    )
    ranked = [a.alert_id for a in store.list_alerts()]
    assert ranked[0] == "a-high"
    assert ranked[-1] == "a-unscored"


def test_mi_summary_counts(store):
    store.save_alerts([_alert("a1"), _alert("a2"), _alert("a3")])
    store.record_disposition(
        Disposition(
            alert_id="a1",
            status=DispositionStatus.FALSE_POSITIVE,
            rationale="benign salary deposits",
            analyst="ajmal",
            decided_at=datetime.now(UTC),
        )
    )
    mi = store.mi_summary()
    assert mi["total_alerts"] == 3
    assert mi["false_positive"] == 1
    assert mi["open"] == 2
