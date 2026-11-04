"""Request/response schemas for the API (separate from domain + DB models)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from sentinel.models import DispositionStatus


class DispositionRequest(BaseModel):
    """An analyst's disposition. The analyst is taken from the API key, never from this body."""

    model_config = {"str_strip_whitespace": True}

    status: DispositionStatus
    rationale: str = Field(min_length=1, description="Mandatory justification for the decision")


class SARResponse(BaseModel):
    alert_id: str
    typology: str
    narrative: str


class MessageResponse(BaseModel):
    message: str


class AuditEntryResponse(BaseModel):
    actor: str
    action: str
    detail: dict
    at: datetime
