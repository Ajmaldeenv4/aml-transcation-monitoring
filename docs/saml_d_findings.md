# Running Sentinel on the SAML-D benchmark

Sentinel's rules engine was run against the published **SAML-D** synthetic AML
dataset (Oztas et al., IEEE 2023) — 9,504,852 transactions, 0.104% labelled
laundering. This documents what Sentinel detects on real benchmark data, and is
**honest about the caveats**. Numbers are reproducible (see "Reproduce" below).

## Setup

- **Source:** `data/raw/SAML-D.csv` (downloaded from Kaggle; not committed — synthetic but large).
- **Sample:** stratified — **all 9,873 labelled-laundering rows kept** + a reproducible
  2% sample of normal rows (`seed=42`) → **199,774 transactions**. The full file is
  ~1 GB / 9.5M rows, impractical to validate row-by-row interactively.
- **Config:** default `config/rules.yaml` thresholds (untuned for SAML-D).

> **Stale results:** the alert counts below predate the rule fixes to velocity,
> rapid movement, structuring, round-amount and threshold avoidance, and have not
> been regenerated. Re-run on SAML-D before quoting them.

## Results — default config

| Typology rule | Alerts | Touching a labelled-laundering txn |
|---|---:|---:|
| Rapid Movement (pass-through) | 781 | 351 |
| Threshold Avoidance | 361 | 6 |
| Velocity Spike | 119 | 30 |
| **Total** | **1,261** | **387** |

`structuring`, `round_amount`, and `high_risk_geography` produced **0** under the
default config — see caveats.

## High-Risk Geography, aligned to SAML-D

SAML-D's high-laundering-rate destinations are **Albania, Morocco, Nigeria, UAE,
Mexico, Turkey, Pakistan** (25–36% of inflows to them are laundering), not the
default illustrative watchlist (IR/KP/SY/MM/AF). Pointing the rule at SAML-D's
geographies:

| Rule | Watchlist | Alerts | Touching laundering |
|---|---|---:|---:|
| High-Risk Geography | SAML-D countries | **8,439** | 1,344 |

This single rule alerting on **8,439** transactions is the headline AML problem in
miniature: geography is high-*recall* but low-*precision* — exactly the
false-positive burden Sentinel's ML risk-ranking layer exists to triage.

## Honest caveats (read before quoting any number)

1. **"Touching a labelled-laundering txn" is not precision.** SAML-D labels its own
   17 suspicious typologies, which do **not** map one-to-one onto Sentinel's 7
   rules. The overlap is co-incidence with ground-truth labels, not a like-for-like
   precision score.
2. **Stratified sampling breaks per-account temporal continuity.** Keeping only 2%
   of normal rows fragments each account's history, so account-/time-window
   scenarios (`structuring`, `round_amount`, and to a degree `velocity_spike`) are
   **understated**. A faithful run of those rules needs the full file or a much
   larger sample.
3. **Country mapping is table-driven.** SAML-D uses country *names*; the loader maps
   known names to ISO alpha-2 codes and passes unknown names through unchanged.
4. **The headline FP-reduction metric stays generator-based.** Sentinel's reproducible
   figures ([README](../README.md#measured-result-reproducible-synthetic-data)) are
   measured on the labelled synthetic generator with separate training, validation
   and test seeds, and depend on a signal the generator plants.
   SAML-D is used here to validate ingestion + rules on real benchmark data, **not**
   to restate that metric.

## Reproduce

```bash
# Place SAML-D.csv at data/raw/ (see data/README.md), then:
python -m sentinel.cli run-rules            # samples SAML-D, prints alert summary
```

The geography-with-SAML-D-watchlist figure is produced by calling
`sentinel.rules.high_risk_geography.detect(txns, cfg, high_risk={"AL","MA","NG","MX","TR","PK","AE"})`.
