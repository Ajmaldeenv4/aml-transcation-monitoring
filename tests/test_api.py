"""API contract tests using FastAPI's TestClient."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from sentinel.config import load_rules_config
from sentinel.generator import generate_dataset
from sentinel.ingestion import load_transactions, normalise_frame
from sentinel.models import Alert, Severity, Typology
from sentinel.rules import run_rules

AUTH = {"X-API-Key": "alice-key"}


def _dispose(client, status="escalated", rationale="Reviewed the deposits.", headers=AUTH):
    return client.post(
        "/alerts/structuring-abc/disposition",
        json={"status": status, "rationale": rationale},
        headers=headers,
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    monkeypatch.setenv("SENTINEL_DB_URL", f"sqlite:///{db.as_posix()}")
    monkeypatch.setenv("SENTINEL_API_KEYS", "alice:alice-key,bob:bob-key")
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
    assert _dispose(client, rationale="").status_code == 422
    assert _dispose(client, rationale="   ").status_code == 422


def test_disposition_success(client):
    assert _dispose(client).status_code == 200
    # status now reflected in the queue
    alert = client.get("/alerts/structuring-abc").json()
    assert client.get("/alerts?status=escalated").json()[0]["alert_id"] == "structuring-abc"
    assert alert["alert_id"] == "structuring-abc"


def test_sar_generation_and_fetch(client):
    _dispose(client)
    created = client.post("/alerts/structuring-abc/sar", headers=AUTH)
    assert created.status_code == 200
    assert "SUSPICIOUS ACTIVITY REPORT" in created.json()["narrative"]
    fetched = client.get("/alerts/structuring-abc/sar")
    assert fetched.status_code == 200


def test_mi_summary(client):
    resp = client.get("/mi/summary")
    assert resp.status_code == 200
    assert resp.json()["total_alerts"] == 1


def test_rule_generated_alerts_persist_and_round_trip(client):
    # The real pipeline yields naive timestamps; the store must accept them.
    import sentinel.api.main as apimod

    txns = load_transactions(normalise_frame(generate_dataset()))
    alerts = run_rules(txns, load_rules_config())
    assert apimod.store.save_alerts(alerts) == len({a.alert_id for a in alerts})

    fetched = client.get(f"/alerts/{alerts[0].alert_id}").json()
    assert fetched["created_at"].startswith(
        alerts[0].created_at.strftime("%Y-%m-%dT%H:%M:%S")
    )


def test_naive_alert_timestamp_is_treated_as_utc():
    alert = Alert(
        alert_id="a",
        rule_id=Typology.STRUCTURING,
        entity_id="ACC1",
        triggering_txn_ids=["t1"],
        severity=Severity.HIGH,
        created_at=datetime(2026, 1, 1, 9, 30),
    )
    assert alert.created_at == datetime(2026, 1, 1, 9, 30, tzinfo=UTC)


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_writes_require_a_valid_api_key(client, headers):
    assert _dispose(client, headers=headers).status_code == 401
    assert client.post("/alerts/structuring-abc/sar", headers=headers).status_code == 401
    assert client.get("/alerts/structuring-abc").json()["status"] == "open"


def test_writes_fail_closed_with_no_keys_configured(client, monkeypatch):
    monkeypatch.delenv("SENTINEL_API_KEYS")
    assert _dispose(client).status_code == 401


def test_actor_comes_from_the_key_not_the_body(client):
    client.post(
        "/alerts/structuring-abc/disposition",
        json={"status": "escalated", "rationale": "Reviewed.", "analyst": "mallory"},
        headers={"X-API-Key": "bob-key"},
    )
    trail = client.get("/alerts/structuring-abc/audit").json()
    assert [e["actor"] for e in trail if e["action"] == "disposition"] == ["bob"]


def test_decided_alert_cannot_be_changed(client):
    assert _dispose(client).status_code == 200
    assert _dispose(client, status="false_positive").status_code == 409
    assert _dispose(client, status="open").status_code == 409
    assert client.get("/alerts/structuring-abc").json()["status"] == "escalated"


def test_open_is_not_a_decision(client):
    assert _dispose(client, status="open").status_code == 409


def test_sar_requires_escalated_alert(client):
    assert client.post("/alerts/structuring-abc/sar", headers=AUTH).status_code == 409
    _dispose(client, status="false_positive")
    assert client.post("/alerts/structuring-abc/sar", headers=AUTH).status_code == 409


def test_sar_names_and_audits_the_analyst(client):
    _dispose(client)
    created = client.post("/alerts/structuring-abc/sar", headers=AUTH).json()
    assert "alice recommends" in created["narrative"]
    assert "were reviewed" not in created["narrative"]
    trail = client.get("/alerts/structuring-abc/audit").json()
    assert [e["actor"] for e in trail if e["action"] == "sar_draft"] == ["alice"]


def test_audit_trail_for_missing_alert_is_404(client):
    assert client.get("/alerts/nope/audit").status_code == 404
