"""Minimal HTTP client the Streamlit dashboards use to talk to the Sentinel API."""

from __future__ import annotations

import os

import httpx

API_BASE = os.environ.get("SENTINEL_API_URL", "http://localhost:8000")
_TIMEOUT = 10.0


def _url(path: str) -> str:
    return f"{API_BASE.rstrip('/')}{path}"


def get_alerts(**filters) -> list[dict]:
    params = {k: v for k, v in filters.items() if v}
    return httpx.get(_url("/alerts"), params=params, timeout=_TIMEOUT).json()


def get_alert(alert_id: str) -> dict:
    return httpx.get(_url(f"/alerts/{alert_id}"), timeout=_TIMEOUT).json()


def post_disposition(alert_id: str, status: str, rationale: str, api_key: str) -> httpx.Response:
    return httpx.post(
        _url(f"/alerts/{alert_id}/disposition"),
        json={"status": status, "rationale": rationale},
        headers={"X-API-Key": api_key},
        timeout=_TIMEOUT,
    )


def create_sar(alert_id: str, api_key: str) -> httpx.Response:
    return httpx.post(
        _url(f"/alerts/{alert_id}/sar"), headers={"X-API-Key": api_key}, timeout=_TIMEOUT
    )


def get_sar(alert_id: str) -> dict | None:
    resp = httpx.get(_url(f"/alerts/{alert_id}/sar"), timeout=_TIMEOUT)
    return resp.json() if resp.status_code == 200 else None


def get_audit(alert_id: str) -> list[dict]:
    return httpx.get(_url(f"/alerts/{alert_id}/audit"), timeout=_TIMEOUT).json()


def get_mi_summary() -> dict:
    return httpx.get(_url("/mi/summary"), timeout=_TIMEOUT).json()


def api_healthy() -> bool:
    try:
        return httpx.get(_url("/health"), timeout=3.0).json().get("status") == "ok"
    except Exception:
        return False
