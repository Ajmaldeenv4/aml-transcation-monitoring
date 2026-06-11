"""Request/response schemas for the API (separate from domain + DB models)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sentinel.models import DispositionStatus


class DispositionRequest(BaseModel):
    """An analyst's disposition. Rationale is mandatory (min length 1)."""

    status: DispositionStatus
    rationale: str = Field(min_length=1, description="Mandatory justification for the decision")
    analyst: str = Field(min_length=1)


class SARResponse(BaseModel):
    alert_id: str
    typology: str
    narrative: str


class MessageResponse(BaseModel):
    message: str
