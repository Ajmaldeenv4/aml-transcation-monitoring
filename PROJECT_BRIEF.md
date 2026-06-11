# Project Brief — Sentinel AML: Transaction Monitoring & Alert Triage System

> **Hand this file to a fresh Claude Code session to build the project.**
> Codename: **Sentinel** · Owner: Mohamed Ajmaldeen S · Built: 2026
> Purpose: A genuine, portfolio-grade AML system to support a Deutsche Bank
> **AML Transaction Monitoring Apprentice** application — and to be defensible
> line-by-line in a compliance interview.

---

## 0. Read This First — Project Philosophy

This is **not** an ML show-off project. The audience is an **AML compliance manager**, not a machine-learning engineer. The project must prove the builder understands **what a transaction-monitoring analyst actually does all day**: review alerts, recognise money-laundering typologies, make risk-based decisions, document them, and escalate. The ML is a *differentiator layered on top* of that workflow — never a replacement for it.

**Three non-negotiables:**
1. **Synthetic data only.** Never use real customer/transaction data. This is itself a compliance-aware decision and should be stated explicitly in the README. Use a public synthetic AML dataset (see §5).
2. **Speak fluent AML.** Use the real vocabulary: typologies, scenarios, alerts, disposition, SAR/STR, risk-based approach, KYC/CDD context, escalation, MI. Every feature should map to a real analyst task.
3. **No slop, no fabrication.** Every metric on the resume must come from this system's real output. Build it for real.

---

## 1. What We're Building (One Paragraph)

A realistic, end-to-end **Anti-Money Laundering Transaction Monitoring System**. It ingests synthetic banking transactions, runs a **typology-based rules engine** that mirrors real AML detection scenarios, generates **alerts**, scores and prioritises them with an **ML risk model that reduces false positives** (with explainability so an analyst sees *why*), and presents everything in an **analyst alert-review dashboard** where a user triages each alert, records a disposition, and auto-drafts a **Suspicious Activity Report (SAR) narrative**. A secondary **MI / KPI dashboard** gives a manager-level view of alert volumes, false-positive rates, and team productivity.

---

## 2. Why This Wins the Interview

| Interviewer concern | How this project answers it |
|---|---|
| "Why is a CS grad applying to compliance?" | Built a working TM system → genuine domain interest, not opportunistic |
| "Do you understand the analyst's job?" | The whole UI *is* the analyst's alert-review workflow |
| "Model vs. human judgment?" (the audit's killer Q) | Literally built both halves — rules + ML + human disposition step |
| "Risk-based approach?" | The ML layer *ranks* the alert queue by risk; explainable scores |
| "MI preparation / KPI delivery?" (JD line) | Dedicated MI dashboard with the exact metrics a TM team reports |
| "Process automation / RPA benefit?" (JD line) | Auto-drafted SAR narratives + auto-triage of obvious false positives |

---

## 3. AML Domain Primer (Build the Rules From These)

The rules engine must implement detection **scenarios** based on real laundering **typologies**. Implement at least these (each becomes one rule + generates alerts):

1. **Structuring / Smurfing** — multiple cash transactions just under a reporting threshold (e.g., many deposits of 9,000–9,900 when the threshold is 10,000) within a short window.
2. **Rapid Movement of Funds (in-out / pass-through)** — funds credited and almost fully withdrawn/transferred within a short period (account used as a conduit).
3. **Round-Amount Layering** — frequent suspiciously round-number transfers between linked accounts.
4. **Threshold Avoidance** — transactions repeatedly sized just below KYC/EDD or reporting triggers.
5. **High-Risk Geography** — transfers to/from jurisdictions flagged high-risk (use a configurable watchlist of country codes).
6. **Velocity Spike** — sudden anomalous jump in a customer's transaction count/value vs. their own historical baseline.
7. **(Optional, advanced) Network / Mule Ring** — a cluster of accounts cycling funds among themselves (graph-based).

**Concepts the README and code comments should use correctly:** placement, layering, integration; alert *disposition* (false positive / escalate to SAR); risk-based approach; PEP & high-risk customer rating; SAR/STR; case management; MI (Management Information).

---

## 4. Architecture

```
                ┌─────────────────────────────────────────────┐
 Synthetic      │  INGESTION                                  │
 transaction ──▶│  load + normalise + validate (Pydantic)     │
 dataset        └───────────────────┬─────────────────────────┘
                                     ▼
                ┌─────────────────────────────────────────────┐
                │  RULES ENGINE (typology scenarios §3)       │
                │  each rule emits Alert(rule_id, entity, …)  │
                └───────────────────┬─────────────────────────┘
                                     ▼
                ┌─────────────────────────────────────────────┐
                │  ML RISK-SCORING LAYER                      │
                │  score each alert 0–100, rank queue,        │
                │  SHAP explanation per alert                 │
                └───────────────────┬─────────────────────────┘
                                     ▼
                ┌─────────────────────────────────────────────┐
                │  CASE STORE (SQLite/Postgres)               │
                │  alerts, dispositions, SAR drafts, audit    │
                └──────────┬───────────────────┬──────────────┘
                           ▼                   ▼
        ┌──────────────────────────┐  ┌──────────────────────────┐
        │ ANALYST DASHBOARD (main) │  │ MI / KPI DASHBOARD (2nd) │
        │ review → disposition →   │  │ volumes, FP rate,        │
        │ SAR narrative draft      │  │ productivity, SLA        │
        └──────────────────────────┘  └──────────────────────────┘

 Backend: FastAPI  ·  Frontend: React (or Streamlit for speed)  ·  Docker
```

---

## 5. Data

**Use a public synthetic AML dataset** (pick one, state choice in README):
- **SAML-D** (synthetic AML dataset, transactions labelled by typology) — good labels for the ML layer.
- **IBM AMLSim / AMLworld** — agent-based simulated bank transactions with laundering patterns.
- **PaySim** — mobile-money simulation, has fraud labels (lighter on AML typology variety).

If a dataset lacks a needed typology, **generate supplementary synthetic transactions** with a small Python generator so every rule in §3 has positive cases. Document the generator. Keep a clear **labelled "ground truth"** so you can measure the ML layer honestly.

---

## 6. Components (each independently testable)

1. **`ingestion/`** — load dataset, normalise schema, validate with Pydantic models (`Transaction`, `Account`, `Customer`).
2. **`rules/`** — one module per typology scenario in §3. Each rule is a pure function `(transactions, config) -> list[Alert]`. Config-driven thresholds (YAML) so you can tune like a real analyst.
3. **`scoring/`** — feature engineering from alert + entity history; an ML classifier (start: gradient boosting / RandomForest) that outputs a 0–100 risk score; **SHAP** values per alert for explainability. Trained on the labelled data.
4. **`casestore/`** — persistence for alerts, analyst dispositions, SAR drafts, and an **immutable audit trail** (who did what, when). SQLite first, Postgres optional.
5. **`sar/`** — template-based SAR/STR **narrative generator**: given an alert + transactions, produce a structured draft (what triggered it, what was reviewed, the typology, the recommendation). Optional: LLM-assisted phrasing, but template-first so it works offline.
6. **`api/`** — FastAPI: list/queue alerts (ranked), get alert detail + explanation, submit disposition, generate SAR draft, MI metrics endpoints.
7. **`dashboard_analyst/`** — **centerpiece.** Alert queue sorted by risk; click an alert → see entity profile, triggering transactions, the typology, the ML risk score + SHAP reasons; buttons to **Close as False Positive** or **Escalate to SAR** (with mandatory rationale text); generates the SAR draft.
8. **`dashboard_mi/`** — manager view: alert volume over time, false-positive rate, escalation rate, average handling time, alerts by typology, analyst productivity. These are real TM team MI metrics.

---

## 7. Tech Stack

- **Language:** Python 3.11+
- **Backend:** FastAPI + Pydantic v2
- **ML:** scikit-learn (gradient boosting), SHAP for explainability, pandas/numpy
- **Storage:** SQLite (default) → Postgres optional via Docker
- **Frontend:** React + a charting lib (Recharts) for the polished version; **Streamlit acceptable** if time-pressured (faster to build, still demo-able)
- **Infra:** Docker + docker-compose; Makefile for `setup / run / test`
- **Testing:** pytest — unit tests per rule (golden cases), scoring sanity tests, API tests
- **Quality:** ruff, type hints, structured logging

---

## 8. Build Phases (suggested 2–3 week plan)

**Phase 1 — Data + Rules (the credibility core).** Ingest dataset, build Pydantic models, implement all §3 rules with config-driven thresholds, write golden-case unit tests per rule. *Deliverable: a script that turns transactions into a list of typed alerts.*

**Phase 2 — Case store + API.** Persist alerts + dispositions + audit trail. FastAPI endpoints for the queue, alert detail, and disposition. *Deliverable: you can list and disposition alerts via API.*

**Phase 3 — ML scoring + explainability.** Feature-engineer from alerts + history, train the classifier on labelled data, expose risk score + SHAP reasons per alert; rank the queue by risk. **Measure the false-positive reduction honestly** vs. rules-only — this number goes on the resume. *Deliverable: a real metric.*

**Phase 4 — Analyst dashboard (centerpiece).** The review screen: ranked queue → alert detail + explanation → disposition buttons + mandatory rationale → SAR draft generation.

**Phase 5 — MI/KPI dashboard + SAR generator polish.** Manager metrics view; refine SAR narrative templates.

**Phase 6 — Docker, README, tests, demo.** Compose stack, thorough README (state the synthetic-data decision prominently), record a short demo GIF/video for the interview.

---

## 9. Resume Lines (fill metrics from REAL output — do not invent)

Use after the build. Replace bracketed values with measured numbers.

```
Sentinel AML — Transaction Monitoring & Alert Triage System | 2026
Tech: Python, FastAPI, scikit-learn, SHAP, Docker, React/Streamlit, SQLite

• Built an end-to-end AML transaction monitoring system that detects [N]
  laundering typologies (structuring, rapid movement, layering, threshold
  avoidance, high-risk geography) via a configurable rules engine, generating
  prioritised alerts from synthetic banking data.
• Layered an explainable ML risk-scoring model (gradient boosting + SHAP) over
  rule alerts to rank the review queue, reducing false-positive review volume
  by [MEASURED]% while preserving [MEASURED]% recall on labelled cases.
• Designed an analyst alert-review workflow with disposition, mandatory
  rationale capture, an immutable audit trail, and auto-drafted SAR narratives
  — modelling real case-management and escalation processes.
• Developed an MI/KPI dashboard tracking alert volume, false-positive rate,
  escalation rate, and average handling time for management reporting.
```

---

## 10. Interview Talking Points (prepare these)

- **Risk-based approach:** "My ML layer ranks the queue so high-risk alerts (PEP, high-risk jurisdiction, large value) surface first — that's the risk-based approach in code."
- **Model vs. human:** "The model flags statistical anomalies; the human verifies context — business type, history, counterparty. I built the model *and* the mandatory human-disposition step on purpose."
- **False positives:** "Rules alone over-alert. I measured rules-only vs. rules+ML and cut FP review volume by [X]% — exactly the problem real TM teams face."
- **Why synthetic data:** "You never touch real customer data for a side project — so I used SAML-D / a synthetic generator. Compliance starts with how you handle data."
- **SAR narrative:** "Each escalation auto-drafts a structured SAR narrative — what triggered it, what I reviewed, the typology, the recommendation — the document an analyst actually writes."

---

## 11. Honesty Guardrails

- Every resume metric must be **reproducible from this repo's output.** If you didn't measure it, don't claim it.
- The system uses **synthetic data** — say so; never imply real bank data.
- Don't claim certifications (CAMS, ISTQB, etc.) you haven't earned.
- It's fine and honest to say in interview: "It's a learning project on synthetic data, but it mirrors the real TM workflow — here's what I'd do differently with production controls."

---

## 12. First Prompt for the New Session

Paste this to kick off the build:

> "I'm building **Sentinel**, an AML Transaction Monitoring & Alert Triage System described in `PROJECT_BRIEF.md` in this folder. Read the brief, then let's start **Phase 1 (Data + Rules)**. First, help me pick and download a synthetic AML dataset (SAML-D or IBM AMLSim), set up the Python project structure (FastAPI, pydantic, pytest, ruff, Docker), and define the `Transaction`/`Account`/`Customer` Pydantic models. Use TDD for the rules engine. Do not slop — every typology rule gets golden-case tests."
