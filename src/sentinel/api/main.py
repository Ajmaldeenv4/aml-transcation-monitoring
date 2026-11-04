"""Sentinel FastAPI application.

Exposes the analyst alert-review workflow and MI metrics over HTTP. The two
Streamlit dashboards are thin clients over these endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from sentinel.api.auth import current_analyst
from sentinel.api.schemas import (
    AuditEntryResponse,
    DispositionRequest,
    MessageResponse,
    SARResponse,
)
from sentinel.casestore import CaseStore
from sentinel.casestore.errors import InvalidTransition
from sentinel.models import Alert, Disposition
from sentinel.sar import generate_sar_narrative

app = FastAPI(
    title="Sentinel AML",
    description="Transaction Monitoring & Alert Triage System (synthetic data only).",
    version="0.1.0",
)

# Single shared case store (creates tables on first use).
store = CaseStore()

Analyst = Annotated[str, Depends(current_analyst)]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "sentinel-aml"}


@app.get("/alerts", response_model=list[Alert])
def list_alerts(
    status: str | None = None,
    typology: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[Alert]:
    """Return the alert queue, ranked by ML risk score (desc), then severity."""
    return store.list_alerts(status=status, typology=typology, severity=severity, limit=limit)


@app.get("/alerts/{alert_id}", response_model=Alert)
def get_alert(alert_id: str) -> Alert:
    alert = store.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


@app.post("/alerts/{alert_id}/disposition", response_model=MessageResponse)
def disposition(alert_id: str, req: DispositionRequest, analyst: Analyst) -> MessageResponse:
    """Record a disposition on an open alert, audited against the caller's API key."""
    disp = Disposition(
        alert_id=alert_id,
        status=req.status,
        rationale=req.rationale,
        analyst=analyst,
        decided_at=datetime.now(UTC),
    )
    try:
        store.record_disposition(disp)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MessageResponse(message=f"alert {alert_id} dispositioned as {req.status.value}")


@app.post("/alerts/{alert_id}/sar", response_model=SARResponse)
def create_sar(alert_id: str, analyst: Analyst) -> SARResponse:
    """Generate (and persist) a SAR narrative draft for an escalated alert."""
    alert = store.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    draft = generate_sar_narrative(alert, reviewed_by=analyst)
    try:
        store.save_sar_draft(draft, analyst=analyst)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return SARResponse(alert_id=alert_id, typology=draft.typology.value, narrative=draft.narrative)


@app.get("/alerts/{alert_id}/sar", response_model=SARResponse)
def get_sar(alert_id: str) -> SARResponse:
    draft = store.get_sar_draft(alert_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="no SAR draft for this alert")
    return SARResponse(alert_id=alert_id, typology=draft.typology.value, narrative=draft.narrative)


@app.get("/alerts/{alert_id}/audit", response_model=list[AuditEntryResponse])
def get_audit(alert_id: str) -> list[AuditEntryResponse]:
    """Return the alert's audit trail, oldest first."""
    if store.get_alert(alert_id) is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return [
        AuditEntryResponse(actor=e.actor, action=e.action, detail=e.detail, at=e.at)
        for e in store.audit_trail(alert_id)
    ]


@app.get("/mi/summary")
def mi_summary() -> dict:
    """MI/KPI aggregate metrics for the manager dashboard."""
    return store.mi_summary()
