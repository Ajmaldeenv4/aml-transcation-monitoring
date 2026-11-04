"""Tests for the case store: persistence, disposition, audit-trail immutability."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session

from sentinel.casestore.errors import AuditImmutableError, InvalidTransition
from sentinel.models import (
    Alert,
    Disposition,
    DispositionStatus,
    SARDraft,
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


def _decide(store, status=DispositionStatus.ESCALATED, alert_id="structuring-abc"):
    store.record_disposition(
        Disposition(
            alert_id=alert_id,
            status=status,
            rationale="Reviewed the activity.",
            analyst="ajmal",
            decided_at=datetime.now(UTC),
        )
    )


def _sar(alert_id="structuring-abc"):
    return SARDraft(
        alert_id=alert_id,
        narrative="draft",
        typology=Typology.STRUCTURING,
        generated_at=datetime.now(UTC),
    )


def _engine():
    import sentinel.casestore.repository as repo

    return repo.engine


def test_closed_alert_cannot_be_redecided(store):
    store.save_alerts([_alert()])
    _decide(store)
    with pytest.raises(InvalidTransition):
        _decide(store, DispositionStatus.FALSE_POSITIVE)
    assert store.get_status("structuring-abc") == "escalated"
    assert len([e for e in store.audit_trail("structuring-abc") if e.action == "disposition"]) == 1


def test_alert_status_is_exposed_on_the_domain_model(store):
    store.save_alerts([_alert()])
    _decide(store)
    assert store.get_alert("structuring-abc").status is DispositionStatus.ESCALATED


def test_failed_audit_write_rolls_back_the_disposition(store, monkeypatch):
    import sentinel.casestore.repository as repo

    store.save_alerts([_alert()])

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(repo, "_add_audit", boom)
    with pytest.raises(RuntimeError):
        _decide(store)
    monkeypatch.undo()
    assert store.get_status("structuring-abc") == "open"


def test_failed_audit_write_rolls_back_the_sar(store, monkeypatch):
    import sentinel.casestore.repository as repo

    store.save_alerts([_alert()])
    _decide(store)

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(repo, "_add_audit", boom)
    with pytest.raises(RuntimeError):
        store.save_sar_draft(_sar(), analyst="ajmal")
    monkeypatch.undo()
    assert store.get_sar_draft("structuring-abc") is None


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_trail SET actor = 'mallory'", "DELETE FROM audit_trail"]
)
def test_database_refuses_raw_changes_to_the_audit_trail(store, statement):
    store.save_alerts([_alert()])
    with pytest.raises(DBAPIError, match="append-only"), _engine().begin() as conn:
        conn.execute(text(statement))
    assert store.audit_trail("alerts")[0].actor == "system"


def test_orm_refuses_changes_to_the_audit_trail(store):
    store.save_alerts([_alert()])
    with Session(_engine()) as s:
        entry = s.merge(store.audit_trail("alerts")[0])
        entry.actor = "mallory"
        s.add(entry)
        with pytest.raises(AuditImmutableError):
            s.commit()


def test_append_only_protection_is_added_to_an_existing_database(store):
    store.save_alerts([_alert()])
    with _engine().begin() as conn:
        conn.execute(text("DROP TRIGGER audit_trail_no_delete"))
    type(store)()  # startup re-applies the protection
    with pytest.raises(DBAPIError, match="append-only"), _engine().begin() as conn:
        conn.execute(text("DELETE FROM audit_trail"))


def test_unscored_reseed_keeps_the_existing_score(store):
    store.save_alerts([_alert(risk_score=88.0, risk_reasons=["x"])])
    store.save_alerts([_alert()])
    kept = store.get_alert("structuring-abc")
    assert kept.risk_score == 88.0
    assert kept.risk_reasons == ["x"]
    assert not [e for e in store.audit_trail("structuring-abc") if e.action == "rescore"]


def test_score_changes_are_audited(store):
    store.save_alerts([_alert(risk_score=88.0)])
    store.save_alerts([_alert(risk_score=40.0)])
    store.save_alerts([_alert(risk_score=40.0)])  # unchanged, so no new entry
    entries = [e for e in store.audit_trail("structuring-abc") if e.action == "rescore"]
    assert [e.detail for e in entries] == [{"from": 88.0, "to": 40.0}]


def test_sar_draft_requires_escalated_alert(store):
    store.save_alerts([_alert()])
    with pytest.raises(InvalidTransition):
        store.save_sar_draft(_sar(), analyst="ajmal")
    assert store.get_sar_draft("structuring-abc") is None


def test_sar_draft_unknown_alert_raises(store):
    with pytest.raises(KeyError):
        store.save_sar_draft(_sar("missing"), analyst="ajmal")
