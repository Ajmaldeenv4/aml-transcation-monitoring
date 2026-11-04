"""Repository layer: the single place that reads/writes the case store.

Every state change appends an :class:`AuditEntry` in the same transaction, so a
change and its audit record either both commit or both roll back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update
from sqlmodel import Session, select

from sentinel.casestore.db import engine, init_db
from sentinel.casestore.errors import InvalidTransition
from sentinel.casestore.tables import (
    AlertRecord,
    AuditEntry,
    DispositionRecord,
    SARDraftRecord,
)
from sentinel.models import Alert, Disposition, DispositionStatus, SARDraft, Severity, Typology

# An alert is decided once. Closed alerts have no onward transitions.
_ALLOWED_TRANSITIONS = {
    DispositionStatus.OPEN.value: {
        DispositionStatus.FALSE_POSITIVE.value,
        DispositionStatus.ESCALATED.value,
    },
}


def _now() -> datetime:
    return datetime.now(UTC)


def _add_audit(
    s: Session, actor: str, action: str, entity_type: str, entity_id: str, detail: dict
) -> None:
    """Queue an audit entry on the caller's session, so it commits with the change."""
    s.add(
        AuditEntry(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            at=_now(),
        )
    )


def _to_domain_alert(rec: AlertRecord) -> Alert:
    return Alert(
        alert_id=rec.alert_id,
        rule_id=Typology(rec.rule_id),
        entity_id=rec.entity_id,
        triggering_txn_ids=list(rec.triggering_txn_ids),
        severity=Severity(rec.severity),
        created_at=rec.created_at,
        evidence=dict(rec.evidence),
        status=DispositionStatus(rec.status),
        risk_score=rec.risk_score,
        risk_reasons=list(rec.risk_reasons),
    )


class CaseStore:
    """Thin façade over the DB. Construct once and reuse."""

    def __init__(self, *, create: bool = True) -> None:
        if create:
            init_db()

    # ---- writes -----------------------------------------------------------
    def save_alerts(self, alerts: list[Alert]) -> int:
        """Upsert alerts (idempotent on alert_id). Returns count written.

        A new score replaces the old one and is audited. Unscored input never
        erases an existing score.
        """
        written = rescored = 0
        with Session(engine) as s:
            for a in alerts:
                existing = s.get(AlertRecord, a.alert_id)
                if existing is None:
                    s.add(_alert_to_record(a))
                    written += 1
                elif a.risk_score is not None and a.risk_score != existing.risk_score:
                    _add_audit(
                        s,
                        "system",
                        "rescore",
                        "alert",
                        a.alert_id,
                        {"from": existing.risk_score, "to": a.risk_score},
                    )
                    existing.risk_score = a.risk_score
                    existing.risk_reasons = list(a.risk_reasons)
                    s.add(existing)
                    rescored += 1
            _add_audit(
                s, "system", "ingest_alerts", "batch", "alerts",
                {"count": written, "rescored": rescored},
            )
            s.commit()
        return written

    def record_disposition(self, disp: Disposition) -> None:
        with Session(engine) as s:
            alert = s.get(AlertRecord, disp.alert_id)
            if alert is None:
                raise KeyError(f"unknown alert_id {disp.alert_id}")
            prev = alert.status
            new = disp.status.value
            if new not in _ALLOWED_TRANSITIONS.get(prev, set()):
                raise InvalidTransition(f"alert {disp.alert_id} cannot go from {prev} to {new}")
            # Conditional update: of two concurrent decisions, only one can win.
            claimed = s.connection().execute(
                update(AlertRecord)
                .where(AlertRecord.alert_id == disp.alert_id, AlertRecord.status == prev)
                .values(status=new)
            )
            if claimed.rowcount != 1:
                raise InvalidTransition(f"alert {disp.alert_id} was decided by someone else")
            s.add(
                DispositionRecord(
                    alert_id=disp.alert_id,
                    status=disp.status.value,
                    rationale=disp.rationale,
                    analyst=disp.analyst,
                    decided_at=disp.decided_at,
                )
            )
            _add_audit(
                s,
                disp.analyst,
                "disposition",
                "alert",
                disp.alert_id,
                {"from": prev, "to": new, "rationale": disp.rationale},
            )
            s.commit()

    def save_sar_draft(self, draft: SARDraft, analyst: str) -> None:
        """Persist a SAR draft. Only an escalated alert can have one."""
        with Session(engine) as s:
            alert = s.get(AlertRecord, draft.alert_id)
            if alert is None:
                raise KeyError(f"unknown alert_id {draft.alert_id}")
            if alert.status != DispositionStatus.ESCALATED.value:
                raise InvalidTransition(
                    f"alert {draft.alert_id} is {alert.status}; only escalated alerts get a SAR"
                )
            s.add(
                SARDraftRecord(
                    alert_id=draft.alert_id,
                    typology=draft.typology.value,
                    narrative=draft.narrative,
                    generated_at=draft.generated_at,
                )
            )
            _add_audit(
                s, analyst, "sar_draft", "alert", draft.alert_id,
                {"typology": draft.typology.value},
            )
            s.commit()

    # ---- reads ------------------------------------------------------------
    def list_alerts(
        self,
        *,
        status: str | None = None,
        typology: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """Return the alert queue, ranked by risk_score desc (nulls last), then severity."""
        with Session(engine) as s:
            stmt = select(AlertRecord)
            if status:
                stmt = stmt.where(AlertRecord.status == status)
            if typology:
                stmt = stmt.where(AlertRecord.rule_id == typology)
            if severity:
                stmt = stmt.where(AlertRecord.severity == severity)
            records = s.exec(stmt).all()

        severity_rank = {"high": 0, "medium": 1, "low": 2}
        records.sort(
            key=lambda r: (
                r.risk_score is None,  # scored alerts first
                -(r.risk_score or 0),  # higher risk first
                severity_rank.get(r.severity, 3),
                r.created_at,
            )
        )
        return [_to_domain_alert(r) for r in records[:limit]]

    def get_alert(self, alert_id: str) -> Alert | None:
        with Session(engine) as s:
            rec = s.get(AlertRecord, alert_id)
            return _to_domain_alert(rec) if rec else None

    def get_status(self, alert_id: str) -> str | None:
        with Session(engine) as s:
            rec = s.get(AlertRecord, alert_id)
            return rec.status if rec else None

    def get_sar_draft(self, alert_id: str) -> SARDraft | None:
        with Session(engine) as s:
            stmt = (
                select(SARDraftRecord)
                .where(SARDraftRecord.alert_id == alert_id)
                .order_by(SARDraftRecord.generated_at.desc())
            )
            rec = s.exec(stmt).first()
        if not rec:
            return None
        return SARDraft(
            alert_id=rec.alert_id,
            narrative=rec.narrative,
            typology=Typology(rec.typology),
            generated_at=rec.generated_at,
        )

    def audit_trail(self, entity_id: str | None = None) -> list[AuditEntry]:
        with Session(engine) as s:
            stmt = select(AuditEntry)
            if entity_id:
                stmt = stmt.where(AuditEntry.entity_id == entity_id)
            stmt = stmt.order_by(AuditEntry.at)
            return list(s.exec(stmt).all())

    # ---- MI metrics -------------------------------------------------------
    def mi_summary(self) -> dict:
        """Aggregate metrics for the MI/KPI dashboard."""
        with Session(engine) as s:
            alerts = s.exec(select(AlertRecord)).all()
            disps = s.exec(select(DispositionRecord)).all()

        total = len(alerts)
        fp = sum(1 for a in alerts if a.status == DispositionStatus.FALSE_POSITIVE.value)
        esc = sum(1 for a in alerts if a.status == DispositionStatus.ESCALATED.value)
        open_ = sum(1 for a in alerts if a.status == DispositionStatus.OPEN.value)
        dispositioned = fp + esc

        by_typology: dict[str, int] = {}
        for a in alerts:
            by_typology[a.rule_id] = by_typology.get(a.rule_id, 0) + 1

        by_analyst: dict[str, int] = {}
        for d in disps:
            by_analyst[d.analyst] = by_analyst.get(d.analyst, 0) + 1

        return {
            "total_alerts": total,
            "open": open_,
            "false_positive": fp,
            "escalated": esc,
            "false_positive_rate": round(fp / dispositioned, 3) if dispositioned else 0.0,
            "escalation_rate": round(esc / dispositioned, 3) if dispositioned else 0.0,
            "alerts_by_typology": by_typology,
            "dispositions_by_analyst": by_analyst,
        }


def _alert_to_record(a: Alert) -> AlertRecord:
    return AlertRecord(
        alert_id=a.alert_id,
        rule_id=a.rule_id.value,
        entity_id=a.entity_id,
        severity=a.severity.value,
        created_at=a.created_at,
        triggering_txn_ids=list(a.triggering_txn_ids),
        evidence=dict(a.evidence),
        risk_score=a.risk_score,
        risk_reasons=list(a.risk_reasons),
        status="open",
    )
