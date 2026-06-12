"""Sentinel command-line entry point.

Subcommands:
  generate    Write a reproducible synthetic dataset to data/synthetic/.
  run-rules   Load data (SAML-D if present, else synthetic), run the rules
              engine, and print an alert summary. This is the Phase 1 deliverable.
  seed        Run the rules engine, score the alerts (if a model exists), and
              persist them to the case store so the API/dashboards have data.
"""

from __future__ import annotations

import argparse
from collections import Counter

from sentinel.config import REPO_ROOT, load_rules_config
from sentinel.generator import generate_dataset
from sentinel.ingestion import load_saml_d, load_transactions, normalise_frame
from sentinel.rules import run_rules

SAML_D_PATH = REPO_ROOT / "data" / "raw" / "SAML-D.csv"
SYNTHETIC_PATH = REPO_ROOT / "data" / "synthetic" / "transactions.csv"


def _cmd_generate(args: argparse.Namespace) -> int:
    df = generate_dataset(seed=args.seed, benign=args.benign)
    SYNTHETIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SYNTHETIC_PATH, index=False)
    laundering = int(df["is_laundering"].sum())
    print(f"Wrote {len(df)} transactions ({laundering} labelled laundering) -> {SYNTHETIC_PATH}")
    return 0


def _load_default_transactions(scale: int = 1, saml_sample_frac: float = 0.02):
    if SAML_D_PATH.exists():
        # The full SAML-D file is ~9.5M rows; stratified-sample normal rows while
        # keeping all labelled-laundering rows so the run stays tractable.
        print(
            f"Loading SAML-D from {SAML_D_PATH} "
            f"(sample_frac={saml_sample_frac}, all laundering rows kept)"
        )
        return load_saml_d(SAML_D_PATH, sample_frac=saml_sample_frac)
    print(f"SAML-D not found; using synthetic generator (seed=42, scale={scale}).")
    df = generate_dataset(seed=42, scale=scale)
    return load_transactions(normalise_frame(df))


def _cmd_run_rules(args: argparse.Namespace) -> int:
    txns = _load_default_transactions()
    config = load_rules_config()
    alerts = run_rules(txns, config)

    print(f"\nLoaded {len(txns)} transactions")
    print(f"Generated {len(alerts)} alerts\n")

    by_rule = Counter(a.rule_id.label for a in alerts)
    for label, count in sorted(by_rule.items()):
        print(f"  {label:<40} {count}")

    if args.show:
        print("\nSample alerts:")
        for a in alerts[: args.show]:
            print(
                f"  [{a.severity.value:<6}] {a.rule_id.value:<20} "
                f"entity={a.entity_id:<12} txns={len(a.triggering_txn_ids)} {a.evidence}"
            )
    return 0


def _cmd_train(args: argparse.Namespace) -> int:
    from sentinel.scoring import train_model

    txns = _load_default_transactions(scale=args.scale)
    alerts = run_rules(txns, load_rules_config())
    train_model(alerts, txns)
    print(f"Trained risk model on {len(alerts)} alerts and saved the artifact.")
    return 0


def _cmd_seed(args: argparse.Namespace) -> int:
    from sentinel.casestore import CaseStore

    txns = _load_default_transactions(scale=args.scale)
    alerts = run_rules(txns, load_rules_config())

    # Score alerts if a trained model artifact exists (Phase 3); otherwise persist
    # rules-only alerts so the API/dashboards still work.
    try:
        from sentinel.scoring import score_alerts

        alerts = score_alerts(alerts, txns)
        print("Applied ML risk scores.")
    except Exception as exc:  # noqa: BLE001 - scoring is optional at seed time
        print(f"Scoring skipped ({exc}); persisting rules-only alerts.")

    store = CaseStore()
    written = store.save_alerts(alerts)
    print(f"Persisted {written} alerts to the case store.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel", description="Sentinel AML CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="write a synthetic dataset")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--benign", type=int, default=400)
    g.set_defaults(func=_cmd_generate)

    r = sub.add_parser("run-rules", help="run the rules engine and summarise alerts")
    r.add_argument("--show", type=int, default=10, help="print N sample alerts")
    r.set_defaults(func=_cmd_run_rules)

    t = sub.add_parser("train", help="train the ML risk model and save the artifact")
    t.add_argument("--scale", type=int, default=8)
    t.set_defaults(func=_cmd_train)

    s = sub.add_parser("seed", help="persist (scored) alerts to the case store")
    s.add_argument("--scale", type=int, default=3)
    s.set_defaults(func=_cmd_seed)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
