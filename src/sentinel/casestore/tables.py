"""SQLModel table definitions for the case store.

These persistence tables are distinct from the domain Pydantic models in
``sentinel.models``; the repository maps between them. The ``AuditEntry`` table
is append-only: the ORM refuses changes to its rows on every backend, and on
SQLite database triggers also refuse them for raw SQL (see ``db.init_db``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, event
from sqlmodel import Field, SQLModel

from sentinel.casestore.errors import AuditImmutableError


class AlertRecord(SQLModel, table=True):
    __tablename__ = "alerts"

    alert_id: str = Field(primary_key=True)
    rule_id: str = Field(index=True)
    entity_id: str = Field(index=True)
    severity: str = Field(index=True)
    created_at: datetime
    triggering_txn_ids: list = Field(default_factory=list, sa_column=Column(JSON))
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON))
    risk_score: float | None = Field(default=None, index=True)
    risk_reasons: list = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="open", index=True)  # open | false_positive | escalated


class DispositionRecord(SQLModel, table=True):
    __tablename__ = "dispositions"

    id: int | None = Field(default=None, primary_key=True)
    alert_id: str = Field(index=True)
    status: str
    rationale: str
    analyst: str
    decided_at: datetime


class SARDraftRecord(SQLModel, table=True):
    __tablename__ = "sar_drafts"

    id: int | None = Field(default=None, primary_key=True)
    alert_id: str = Field(index=True)
    typology: str
    narrative: str
    generated_at: datetime


class AuditEntry(SQLModel, table=True):
    """Append-only audit trail. Never updated or deleted."""

    __tablename__ = "audit_trail"

    id: int | None = Field(default=None, primary_key=True)
    actor: str
    action: str = Field(index=True)
    entity_type: str
    entity_id: str = Field(index=True)
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON))
    at: datetime


def _refuse_audit_change(_mapper, _connection, target: AuditEntry) -> None:
    raise AuditImmutableError(f"audit entry {target.id} cannot be changed or deleted")


event.listen(AuditEntry, "before_update", _refuse_audit_change)
event.listen(AuditEntry, "before_delete", _refuse_audit_change)
