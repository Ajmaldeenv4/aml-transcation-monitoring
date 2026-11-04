"""Alert, Disposition, and SARDraft — the case-management vocabulary."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from sentinel.models.enums import Typology


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DispositionStatus(str, Enum):
    """Outcome an analyst records when triaging an alert."""

    OPEN = "open"
    FALSE_POSITIVE = "false_positive"
    ESCALATED = "escalated"  # escalated to SAR/STR


class Alert(BaseModel):
    """An alert raised by one rule against one entity (account/customer).

    ``evidence`` carries rule-specific detail (counts, amounts, windows) that the
    analyst sees and the SAR narrative quotes. ``risk_score`` and ``risk_reasons``
    are populated by the ML scoring layer (Phase 3); they are ``None`` for
    rules-only output.
    """

    alert_id: str
    rule_id: Typology
    entity_id: str  # the account or customer the alert concerns
    triggering_txn_ids: list[str]
    severity: Severity
    created_at: datetime
    evidence: dict = Field(default_factory=dict)
    status: DispositionStatus = DispositionStatus.OPEN

    # Populated by the scoring layer.
    risk_score: float | None = None  # 0-100
    risk_reasons: list[str] = Field(default_factory=list)

    @field_validator("created_at")
    @classmethod
    def _assume_utc(cls, v: datetime) -> datetime:
        """Source timestamps carry no zone; treat them as UTC so storage is unambiguous."""
        return v.replace(tzinfo=UTC) if v.utcoffset() is None else v

    @property
    def typology_label(self) -> str:
        return self.rule_id.label


class Disposition(BaseModel):
    """An analyst's decision on an alert, with mandatory rationale."""

    alert_id: str
    status: DispositionStatus
    rationale: str = Field(min_length=1)  # mandatory free-text justification
    analyst: str
    decided_at: datetime


class SARDraft(BaseModel):
    """A generated Suspicious Activity Report narrative draft."""

    alert_id: str
    narrative: str
    typology: Typology
    generated_at: datetime
