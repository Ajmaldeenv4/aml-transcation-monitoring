"""Sentinel — MI / KPI Dashboard (manager view).

The metrics a transaction-monitoring team actually reports to management: alert
volume, false-positive rate, escalation rate, alerts by typology, and analyst
productivity — plus the ML layer's measured false-positive-reduction result.

Run with:  streamlit run dashboards/mi_app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import _client as api
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Sentinel — MI / KPI", page_icon="📊", layout="wide")

st.title("📊 Sentinel — MI / KPI Dashboard")
st.caption("Synthetic data only. Management information for an AML monitoring team.")

if not api.api_healthy():
    st.error("Cannot reach the Sentinel API. Start it with `uvicorn sentinel.api.main:app --port 8000`.")
    st.stop()

mi = api.get_mi_summary()

# ---- Headline KPIs -------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total alerts", mi["total_alerts"])
c2.metric("Open", mi["open"])
c3.metric("False-positive rate", f"{mi['false_positive_rate'] * 100:.0f}%")
c4.metric("Escalation rate", f"{mi['escalation_rate'] * 100:.0f}%")

st.divider()

# ---- Alerts by typology --------------------------------------------------
left, right = st.columns(2)
with left:
    st.subheader("Alerts by typology")
    by_typ = mi.get("alerts_by_typology", {})
    if by_typ:
        df = pd.DataFrame({"typology": list(by_typ), "alerts": list(by_typ.values())})
        st.bar_chart(df.set_index("typology"))
    else:
        st.info("No alerts yet — seed the case store.")

with right:
    st.subheader("Dispositions by analyst (productivity)")
    by_an = mi.get("dispositions_by_analyst", {})
    if by_an:
        df = pd.DataFrame({"analyst": list(by_an), "dispositions": list(by_an.values())})
        st.bar_chart(df.set_index("analyst"))
    else:
        st.info("No dispositions recorded yet.")

st.divider()

# ---- ML layer evaluation (the headline metric) --------------------------
st.subheader("ML layer — measured false-positive reduction")
metrics_path = Path(__file__).resolve().parents[1] / "artifacts" / "metrics.json"
if metrics_path.exists():
    m = json.loads(metrics_path.read_text(encoding="utf-8"))
    a, b, c = st.columns(3)
    a.metric("Recall preserved", f"{m['recall_preserved_pct']}%")
    b.metric("False-positive reduction", f"{m['false_positive_reduction_pct']}%")
    c.metric("Review-volume reduction", f"{m['review_volume_reduction_pct']}%")
    st.caption(
        f"Risk threshold {m['risk_threshold']}, fixed on validation data for a "
        f"{m['target_recall'] * 100:.0f}% recall target. Mean of {m['test_seeds']} synthetic "
        f"test seeds ({m['true_positive_alerts']} true-positive vs "
        f"{m['false_positive_alerts']} false-positive alerts). Recall ranged "
        f"{m['recall_preserved_min_pct']}-{m['recall_preserved_max_pct']}%. "
        "Reproduce with `python -m sentinel.scoring.evaluate`."
    )
else:
    st.info("Run `python -m sentinel.scoring.evaluate` to produce the FP-reduction metric.")
