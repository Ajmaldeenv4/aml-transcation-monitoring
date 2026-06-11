"""Sentinel FastAPI application.

Exposes the analyst alert-review workflow and MI metrics over HTTP. The two
Streamlit dashboards are thin clients over these endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException

from sentinel.api.schemas import DispositionRequest, MessageResponse, SARResponse
from sentinel.casestore import CaseStore
from sentinel.models import Alert, Disposition
from sentinel.sar import generate_sar_narrative

app = FastAPI(
    title="Sentinel AML",
    description="Transaction Monitoring & Alert Triage System (synthetic data only).",
    version="0.1.0",
)

# Single shared case store (creates tables on first use).
store = CaseStore()


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
def disposition(alert_id: str, req: DispositionRequest) -> MessageResponse:
    """Record a disposition. Rationale is mandatory and the action is audited."""
    disp = Disposition(
        alert_id=alert_id,
        status=req.status,
        rationale=req.rationale,
        analyst=req.analyst,
        decided_at=datetime.now(UTC),
    )
    try:
        store.record_disposition(disp)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MessageResponse(message=f"alert {alert_id} dispositioned as {req.status.value}")


@app.post("/alerts/{alert_id}/sar", response_model=SARResponse)
def create_sar(alert_id: str) -> SARResponse:
    """Generate (and persist) a SAR narrative draft for an alert."""
    alert = store.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    draft = generate_sar_narrative(alert)
    store.save_sar_draft(draft)
    return SARResponse(alert_id=alert_id, typology=draft.typology.value, narrative=draft.narrative)


@app.get("/alerts/{alert_id}/sar", response_model=SARResponse)
def get_sar(alert_id: str) -> SARResponse:
    draft = store.get_sar_draft(alert_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="no SAR draft for this alert")
    return SARResponse(alert_id=alert_id, typology=draft.typology.value, narrative=draft.narrative)


@app.get("/mi/summary")
def mi_summary() -> dict:
    """MI/KPI aggregate metrics for the manager dashboard."""
    return store.mi_summary()
