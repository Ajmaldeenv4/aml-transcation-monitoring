"""Reproducible synthetic AML transaction generator.

Each ``_inject_*`` helper plants a clear positive case for one typology and
labels those transactions ``is_laundering=1``. Benign background traffic is
labelled 0. Output is a normalised DataFrame consumable by
:func:`sentinel.ingestion.load_transactions`.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd

from sentinel.models import TransactionType

BASE = datetime(2026, 1, 1, 8, 0, 0)
HIGH_RISK = ["IR", "KP", "SY"]


def _row(
    rows: list[dict],
    sender: str,
    receiver: str,
    amount: float,
    offset_hours: float,
    txn_type: TransactionType = TransactionType.TRANSFER,
    sender_country: str = "US",
    receiver_country: str = "US",
    is_laundering: int = 0,
) -> None:
    rows.append(
        {
            "txn_id": f"GEN{len(rows):08d}",
            "timestamp": BASE + timedelta(hours=offset_hours),
            "sender_account": sender,
            "receiver_account": receiver,
            "amount": round(amount, 2),
            "currency": "USD",
            "txn_type": txn_type.value,
            "sender_country": sender_country,
            "receiver_country": receiver_country,
            "is_laundering": is_laundering,
        }
    )


def _inject_structuring(rows: list[dict], rng: random.Random, account: str) -> None:
    for i in range(4):
        _row(
            rows,
            sender="EXT",
            receiver=account,
            amount=rng.uniform(9000, 9999),
            offset_hours=i * 12,
            txn_type=TransactionType.CASH_DEPOSIT,
            is_laundering=1,
        )


def _inject_rapid_movement(rows: list[dict], account: str) -> None:
    _row(rows, "EXT", account, 30000, 0, is_laundering=1)
    _row(rows, account, "MULE1", 16000, 3, is_laundering=1)
    _row(rows, account, "MULE2", 12000, 6, is_laundering=1)


def _inject_round_amount(rows: list[dict], src: str, dst: str) -> None:
    for i in range(4):
        _row(rows, src, dst, (i + 5) * 1000, i * 24, is_laundering=1)


def _inject_threshold_avoidance(rows: list[dict], account: str) -> None:
    for i in range(3):
        _row(rows, account, "PAYEE", 9700 + i * 50, i * 48, is_laundering=1)


def _inject_high_risk_geo(rows: list[dict], account: str) -> None:
    _row(rows, account, "FOREIGN", 25000, 0, receiver_country=HIGH_RISK[0], is_laundering=1)
    _row(rows, "FOREIGN2", account, 18000, 12, sender_country=HIGH_RISK[1], is_laundering=1)


def _inject_velocity_spike(rows: list[dict], rng: random.Random, account: str) -> None:
    # Quiet baseline over ~25 days.
    for d in range(8):
        _row(rows, account, "REG", rng.uniform(100, 300), d * 24 * 3, is_laundering=0)
    # Sudden surge in the last day.
    for h in range(4):
        _row(rows, account, "REG", 8000, 24 * 25 + h, is_laundering=1)


def _inject_network_ring(rows: list[dict]) -> None:
    _row(rows, "RING_A", "RING_B", 5000, 0, is_laundering=1)
    _row(rows, "RING_B", "RING_C", 4900, 24, is_laundering=1)
    _row(rows, "RING_C", "RING_A", 4800, 48, is_laundering=1)


def _inject_hard_negative(rows: list[dict], rng: random.Random, account: str, kind: str) -> None:
    """Legitimate activity that nonetheless trips a rule (labelled is_laundering=0).

    These are the genuine false positives a TM team battles: a cash-intensive
    retailer that looks like structuring, a corporate treasury making round
    transfers, payroll causing a velocity spike. They overlap the laundering
    feature space, so the ML layer cannot perfectly separate — giving an honest,
    defensible false-positive-reduction metric rather than a too-perfect 100%.
    """
    if kind == "retailer_cash":  # structuring look-alike
        for i in range(4):
            _row(
                rows, "TILL", account, rng.uniform(9100, 9900), i * 14,
                txn_type=TransactionType.CASH_DEPOSIT, is_laundering=0,
            )
    elif kind == "treasury_round":  # round-amount look-alike
        for i in range(4):
            _row(rows, account, f"{account}_SUP", (i + 3) * 1000, i * 30, is_laundering=0)
    elif kind == "payroll_spike":  # velocity look-alike
        for d in range(8):
            _row(rows, account, "VENDOR", rng.uniform(150, 400), d * 24 * 3, is_laundering=0)
        for h in range(3):
            _row(rows, account, "VENDOR", rng.uniform(5000, 8000), 24 * 25 + h, is_laundering=0)
    elif kind == "invoice_threshold":  # threshold-avoidance look-alike
        for i in range(2):
            _row(rows, account, "CONTRACTOR", rng.uniform(9550, 9950), i * 40, is_laundering=0)


def _inject_benign(rows: list[dict], rng: random.Random, n: int) -> None:
    for _ in range(n):
        a = f"CUST{rng.randint(1, 50)}"
        b = f"CUST{rng.randint(1, 50)}"
        if a == b:
            b = f"CUST{rng.randint(51, 80)}"
        _row(
            rows,
            a,
            b,
            rng.uniform(20, 4000),
            rng.uniform(0, 24 * 30),
            txn_type=rng.choice(
                [TransactionType.TRANSFER, TransactionType.CARD, TransactionType.CHEQUE]
            ),
            is_laundering=0,
        )


def generate_dataset(
    seed: int = 42, benign: int = 400, scale: int = 1, hard_negative_ratio: float = 0.6
) -> pd.DataFrame:
    """Generate a reproducible synthetic dataset covering every typology.

    ``scale`` injects that many distinct laundering entities per typology.
    ``hard_negative_ratio`` controls how many *legitimate but rule-tripping*
    entities are injected relative to scale — these are the realistic false
    positives that give the ML layer an honest job. Set to 0 for a clean dataset.
    """
    rng = random.Random(seed)
    rows: list[dict] = []

    for i in range(scale):
        sfx = "" if i == 0 else f"_{i}"
        _inject_structuring(rows, rng, f"STRUCT_ACC{sfx}")
        _inject_rapid_movement(rows, f"PASS_ACC{sfx}")
        _inject_round_amount(rows, f"LAYER_SRC{sfx}", f"LAYER_DST{sfx}")
        _inject_threshold_avoidance(rows, f"THRESH_ACC{sfx}")
        _inject_high_risk_geo(rows, f"GEO_ACC{sfx}")
        _inject_velocity_spike(rows, rng, f"VELO_ACC{sfx}")
        if i == 0:
            _inject_network_ring(rows)

    hard = int(scale * hard_negative_ratio)
    for i in range(hard):
        _inject_hard_negative(rows, rng, f"RETAIL{i}", "retailer_cash")
        _inject_hard_negative(rows, rng, f"CORP{i}", "treasury_round")
        _inject_hard_negative(rows, rng, f"PAYROLL{i}", "payroll_spike")
        _inject_hard_negative(rows, rng, f"INVOICE{i}", "invoice_threshold")

    _inject_benign(rows, rng, benign)

    df = pd.DataFrame(rows)
    return df.sort_values("timestamp").reset_index(drop=True)
