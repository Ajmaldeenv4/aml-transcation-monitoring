"""SQLModel table definitions for the case store.

These persistence tables are distinct from the domain Pydantic models in
``sentinel.models``; the repository maps between them. The ``AuditEntry`` table
is append-only — the repository never updates or deletes rows, giving an
immutable audit trail of who did what, when.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


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
