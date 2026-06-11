"""API contract tests using FastAPI's TestClient."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from sentinel.models import Alert, Severity, Typology


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    monkeypatch.setenv("SENTINEL_DB_URL", f"sqlite:///{db.as_posix()}")
    import sentinel.casestore.db as dbmod

    importlib.reload(dbmod)
    import sentinel.casestore.repository as repo

    importlib.reload(repo)
    import sentinel.api.main as apimod

    importlib.reload(apimod)

    apimod.store.save_alerts(
        [
            Alert(
                alert_id="structuring-abc",
                rule_id=Typology.STRUCTURING,
                entity_id="ACC1",
                triggering_txn_ids=["t1", "t2", "t3"],
                severity=Severity.HIGH,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                evidence={"count": 3},
                risk_score=88.0,
                risk_reasons=["3 sub-threshold cash deposits"],
            )
        ]
    )
    return TestClient(apimod.app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_list_alerts(client):
    resp = client.get("/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["alert_id"] == "structuring-abc"
    assert data[0]["risk_score"] == 88.0


def test_get_alert_detail(client):
    resp = client.get("/alerts/structuring-abc")
    assert resp.status_code == 200
    assert resp.json()["rule_id"] == "structuring"


def test_get_missing_alert_404(client):
    assert client.get("/alerts/nope").status_code == 404


def test_disposition_requires_rationale(client):
    resp = client.post(
        "/alerts/structuring-abc/disposition",
        json={"status": "false_positive", "rationale": "", "analyst": "ajmal"},
    )
    assert resp.status_code == 422  # pydantic validation rejects empty rationale


def test_disposition_success(client):
    resp = client.post(
        "/alerts/structuring-abc/disposition",
        json={
            "status": "escalated",
            "rationale": "Clear structuring across three sub-threshold deposits.",
            "analyst": "ajmal",
        },
    )
    assert resp.status_code == 200
    # status now reflected in the queue
    alert = client.get("/alerts/structuring-abc").json()
    assert client.get("/alerts?status=escalated").json()[0]["alert_id"] == "structuring-abc"
    assert alert["alert_id"] == "structuring-abc"


def test_sar_generation_and_fetch(client):
    created = client.post("/alerts/structuring-abc/sar")
    assert created.status_code == 200
    assert "SUSPICIOUS ACTIVITY REPORT" in created.json()["narrative"]
    fetched = client.get("/alerts/structuring-abc/sar")
    assert fetched.status_code == 200


def test_mi_summary(client):
    resp = client.get("/mi/summary")
    assert resp.status_code == 200
    assert resp.json()["total_alerts"] == 1
