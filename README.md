# Sentinel AML — Transaction Monitoring & Alert Triage System

An end-to-end, **portfolio-grade Anti-Money Laundering (AML) transaction-monitoring
system**. It ingests synthetic banking transactions, runs a typology-based rules
engine that mirrors real AML detection scenarios, generates alerts, ranks them with
an explainable ML risk model that reduces false-positive review volume, and presents
everything in an **analyst alert-review dashboard** where a user triages each alert,
records a disposition, and auto-drafts a **Suspicious Activity Report (SAR)** narrative.
A secondary **MI / KPI dashboard** gives the manager-level view.

> ### Synthetic data only — by design
> Sentinel **never** uses real customer or transaction data. It runs on the
> public **SAML-D** synthetic dataset (typology-labelled) and a documented,
> reproducible synthetic generator. Handling data responsibly is where AML
> compliance starts, so this is a deliberate, stated design decision — not an
> afterthought. See [`data/README.md`](data/README.md).

---

## Demo

![Sentinel analyst triage workflow](docs/demo.gif)

*Ranked queue → explainable ML risk score → analyst disposition with mandatory rationale → auto-drafted SAR narrative → manager MI/KPI view.*

| Analyst review (queue + SHAP explanation) | Auto-drafted SAR narrative |
|---|---|
| ![Analyst review](docs/screenshots/analyst-overview.png) | ![SAR draft](docs/screenshots/analyst-sar.png) |
| **Disposition (mandatory rationale)** | **MI / KPI dashboard** |
| ![Disposition](docs/screenshots/analyst-disposition.png) | ![MI dashboard](docs/screenshots/mi-dashboard.png) |

---

## What it does (the analyst's workflow, in code)

1. **Ingest & validate** synthetic transactions into typed Pydantic models.
2. **Detect** money-laundering typologies with a config-driven **rules engine**.
3. **Rank** the alert queue with an **explainable ML risk model** (gradient
   boosting + SHAP), surfacing *why* each alert scores as it does.
4. **Triage** each alert in the analyst dashboard → record a disposition with a
   **mandatory rationale** → escalations auto-draft a **SAR narrative**.
5. **Report** team metrics on the **MI/KPI dashboard**, and persist every action
   to an **immutable audit trail**.

## Typologies detected (rules engine)

Structuring / smurfing · rapid movement (pass-through) · round-amount layering ·
threshold avoidance · high-risk geography · velocity spike · (optional) network /
mule ring. Each is a pure, config-tunable function with **golden-case unit tests**.
Thresholds live in [`config/rules.yaml`](config/rules.yaml) so they tune like a real
analyst's scenario parameters.

## Measured result (reproducible, synthetic data)

The model is trained on one generated dataset, its risk threshold is fixed on a second
for a 95% recall target, and that threshold is measured on 30 independent test seeds
(1,997 true-positive vs. 17,689 false-positive alerts). Ranges are min–max across seeds.

| Ranking | Recall | False-positive reduction |
|---|---:|---:|
| ML risk model | 95.7% (87.9–100%) | 90.3% (86.3–94.0%) |
| ML, with laundering amounts lowered 40% | 94.7% | 90.3% |
| No-ML baseline: total amount | 95.5% | 29.3% |

The ML ranking cuts review volume by 81.6% (77.7–86.2%).

**Read this before quoting those figures.** Laundering and legitimate look-alikes in the
generator share the same activity shapes, so the only signal to learn is the one the
generator plants: laundering accounts tend to have a shorter history. The result
measures that assumption, not real-world skill, as narrowing the difference shows
(10 test seeds per row):

| Laundering vs. legitimate history (payments) | ML FP reduction | Baseline FP reduction |
|---|---:|---:|
| 0–12 vs. 8–40 (as generated) | 90.5% | 28.8% |
| 4–24 vs. 8–40 | 61.9% | 25.0% |
| 8–40 vs. 8–40 (no signal) | 30.2% | 29.2% |

With no planted signal, the model adds almost nothing over ranking by amount. What this
demonstrates is the method: a sound evaluation pipeline and a model that can find a
behavioural signal when one exists. Validating real performance needs labelled data
this project does not use.

Every figure is reproducible — regenerate it with:

```bash
python -m sentinel.scoring.evaluate   # writes artifacts/metrics.json
```

## Architecture

```
synthetic txns → ingestion (Pydantic) → rules engine (typologies) →
   ML risk scoring (GBM + SHAP) → case store (SQLite + audit trail) →
      ├─ Analyst dashboard (review → disposition → SAR draft)
      └─ MI/KPI dashboard (volumes, FP rate, productivity)
```

- **Backend:** FastAPI + Pydantic v2 · **ML:** scikit-learn + SHAP
- **Storage:** SQLite (default), Postgres optional via `SENTINEL_DB_URL`
- **Frontend:** Streamlit (analyst + MI dashboards) · **Infra:** Docker Compose

## Quick start

```bash
pip install -r requirements.lock # exact, tested dependency versions
pip install -e . --no-deps

python -m sentinel.cli run-rules # Phase 1: ingest → typed alerts
python -m sentinel.cli train     # train the risk model artifact
python -m sentinel.cli seed      # persist scored alerts to the case store

export SENTINEL_API_KEYS="ajmal:choose-a-key"      # analyst:key pairs; writes are rejected without them
uvicorn sentinel.api.main:app --port 8000          # API
streamlit run dashboards/analyst_app.py            # analyst dashboard (8501)
streamlit run dashboards/mi_app.py                 # MI dashboard (8502)
```

Or the whole stack in one command:

```bash
docker compose up --build        # API :8000 · analyst :8501 · MI :8502
```

By default Sentinel uses the synthetic generator. To use **SAML-D** (9.5M
transactions), place the CSV at `data/raw/SAML-D.csv` (see
[`data/README.md`](data/README.md)) — `run-rules` then stratified-samples it
automatically. Sentinel has been validated end-to-end on SAML-D; see
[`docs/saml_d_findings.md`](docs/saml_d_findings.md) for what it detects and the
honest caveats.

## Audit guarantees

- **Who:** write endpoints take an `X-API-Key` header and record the analyst that key
  belongs to. Keys come from `SENTINEL_API_KEYS`, and with none set every write is
  rejected. The analyst dashboard asks for the key in its sidebar.
- **What:** dispositions, SAR drafts, score changes and ingest runs are each recorded
  in the same transaction as the change, so neither can exist without the other.
- **Final decisions:** an open alert is decided once, and later attempts return `409`.
  Only an escalated alert can have a SAR draft.
- **Append-only:** the ORM refuses to change audit rows, and on SQLite database
  triggers also refuse raw `UPDATE` and `DELETE`.

Limits: read endpoints are not authenticated, Postgres has the ORM check but no
trigger, and someone with admin access to the database can still drop a trigger.
Read an alert's trail at `GET /alerts/{alert_id}/audit`.

## Testing & quality

```bash
pytest          # golden-case rule tests, case store, API, scoring
ruff check src tests
```

## Project layout

| Path | Purpose |
|------|---------|
| `src/sentinel/models/` | Pydantic domain models |
| `src/sentinel/ingestion/` | load + normalise + validate transactions |
| `src/sentinel/generator/` | reproducible synthetic generator (incl. hard negatives) |
| `src/sentinel/rules/` | one module per typology + runner |
| `src/sentinel/scoring/` | features, GBM model, SHAP, honest evaluation |
| `src/sentinel/casestore/` | SQLite persistence + immutable audit trail |
| `src/sentinel/sar/` | template-first SAR narrative generator |
| `src/sentinel/api/` | FastAPI app |
| `dashboards/` | Streamlit analyst + MI apps |
| `tests/` | golden-case + integration tests |

## Honesty guardrails

- Every metric here is **reproducible from this repo's output** on synthetic data.
- No real customer/bank data is ever used or implied.
- This is a learning project that mirrors the real TM workflow — not a certified
  production system.
