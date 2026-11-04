"""Sentinel — Analyst Alert-Review Dashboard (centerpiece).

This IS the transaction-monitoring analyst's workflow: a risk-ranked alert queue,
an alert detail view explaining *why* the alert fired (rule evidence + ML risk
score + SHAP reasons), and a disposition step requiring a mandatory rationale,
which on escalation auto-drafts a SAR narrative.

Run with:  streamlit run dashboards/analyst_app.py
Requires the API:  uvicorn sentinel.api.main:app --port 8000
"""

from __future__ import annotations

import os

import _client as api
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Sentinel — Analyst Review", page_icon="🛡️", layout="wide")

TYPOLOGIES = [
    "structuring",
    "rapid_movement",
    "round_amount",
    "threshold_avoidance",
    "high_risk_geography",
    "velocity_spike",
    "network_ring",
]

st.title("🛡️ Sentinel — Alert Review")
st.caption("Synthetic data only. AML transaction-monitoring alert triage workflow.")

if not api.api_healthy():
    st.error(
        "Cannot reach the Sentinel API. Start it with "
        "`uvicorn sentinel.api.main:app --port 8000` and seed data with "
        "`python -m sentinel.cli seed`."
    )
    st.stop()

# ---- Sidebar: queue filters + analyst identity ---------------------------
with st.sidebar:
    st.header("Queue filters")
    f_status = st.selectbox("Status", ["open", "", "escalated", "false_positive"], index=0)
    f_typology = st.selectbox("Typology", ["", *TYPOLOGIES], index=0)
    f_severity = st.selectbox("Severity", ["", "high", "medium", "low"], index=0)
    st.header("Analyst sign-in")
    api_key = st.text_input(
        "API key", type="password", value=os.environ.get("SENTINEL_API_KEY", "")
    )

alerts = api.get_alerts(status=f_status, typology=f_typology, severity=f_severity, limit=200)

# ---- Ranked queue --------------------------------------------------------
left, right = st.columns([1, 1.4])

with left:
    st.subheader(f"Ranked queue ({len(alerts)})")
    if not alerts:
        st.info("No alerts match these filters. Seed data with `python -m sentinel.cli seed`.")
        st.stop()
    table = pd.DataFrame(
        [
            {
                "alert_id": a["alert_id"],
                "risk": a.get("risk_score"),
                "typology": a["rule_id"],
                "severity": a["severity"],
                "entity": a["entity_id"],
            }
            for a in alerts
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True, height=460)
    selected_id = st.selectbox("Select an alert to review", [a["alert_id"] for a in alerts])

# ---- Alert detail + disposition -----------------------------------------
with right:
    alert = api.get_alert(selected_id)
    score = alert.get("risk_score")
    st.subheader(f"Alert {alert['alert_id']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Risk score", f"{score:.0f}/100" if score is not None else "—")
    c2.metric("Severity", alert["severity"].upper())
    c3.metric("Typology", alert["rule_id"])
    st.caption(f"Status: {alert['status']}")

    if alert.get("risk_reasons"):
        st.markdown("**Why this alert is risk-ranked here:**")
        for reason in alert["risk_reasons"]:
            st.markdown(f"- {reason}")

    st.markdown("**Rule evidence:**")
    st.json(alert["evidence"])

    st.markdown(f"**Triggering transactions ({len(alert['triggering_txn_ids'])}):**")
    st.write(", ".join(alert["triggering_txn_ids"]))

    st.divider()
    st.markdown("### Disposition")
    if alert["status"] != "open":
        st.info(f"This alert is closed as {alert['status']}. Decisions are final.")
        existing_sar = api.get_sar(selected_id)
        if existing_sar:
            st.markdown("### SAR narrative")
            st.code(existing_sar["narrative"], language="text")
    else:
        decision = st.radio(
            "Decision", ["Close as False Positive", "Escalate to SAR"], horizontal=True
        )
        rationale = st.text_area(
            "Rationale (required)",
            placeholder="Document what you reviewed and your risk-based judgement…",
        )

        if st.button("Submit disposition", type="primary"):
            if not rationale.strip():
                st.error("Rationale is mandatory — an analyst must document the decision.")
            else:
                status = "false_positive" if decision.startswith("Close") else "escalated"
                resp = api.post_disposition(selected_id, status, rationale.strip(), api_key)
                if resp.status_code == 200:
                    st.success(f"Recorded: {status}. Audit trail updated.")
                    if status == "escalated":
                        sar = api.create_sar(selected_id, api_key)
                        if sar.status_code == 200:
                            st.markdown("### Auto-drafted SAR narrative")
                            st.code(sar.json()["narrative"], language="text")
                        else:
                            st.error(f"SAR error {sar.status_code}: {sar.text}")
                else:
                    st.error(f"API error {resp.status_code}: {resp.text}")

    with st.expander("Audit trail"):
        st.dataframe(pd.DataFrame(api.get_audit(selected_id)), hide_index=True)
