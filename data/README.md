# Data

**Sentinel uses synthetic data only.** No real customer or transaction data is ever
used, stored, or implied. This is a deliberate compliance-aware decision: AML work
begins with how you handle data.

## Primary dataset — SAML-D

[SAML-D](https://www.kaggle.com/datasets/berkanoztas/synthetic-transaction-monitoring-dataset-aml)
is a **synthetic** transaction-monitoring dataset whose transactions are labelled by
laundering typology, which makes it suitable for honestly measuring the ML layer's
false-positive reduction against ground truth.

### How to obtain it

1. Download the SAML-D CSV from Kaggle (account required).
2. Place it at `data/raw/SAML-D.csv`.
3. `data/raw/` is git-ignored — the raw file is **not** committed.

The ingestion layer (`src/sentinel/ingestion/`) normalises SAML-D's columns onto the
Sentinel schema (`Transaction` / `Account` / `Customer`) and preserves the
`is_laundering` ground-truth label.

## Supplementary synthetic generator

Where SAML-D under-represents a typology from `PROJECT_BRIEF.md` §3, the generator at
`src/sentinel/generator/` produces documented supplementary transactions so every rule
has positive cases. Generated data is written to `data/synthetic/` with retained
ground-truth labels. The generator is fully reproducible (fixed seed).

## Directory layout

- `raw/` — downloaded SAML-D (git-ignored).
- `synthetic/` — generator output (git-ignored).
