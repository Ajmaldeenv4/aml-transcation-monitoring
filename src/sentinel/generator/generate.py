"""Reproducible synthetic AML transaction generator.

Every typology has one randomised activity shape. Laundering entities and
legitimate look-alikes use the *same* shape, so amounts and timing alone cannot
separate them: the difference a model can learn is context. Legitimate entities
tend to have a longer established history, with deliberate overlap between the
two groups. Benign background traffic is labelled 0.

Output is a normalised DataFrame consumable by
:func:`sentinel.ingestion.load_transactions`.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd

from sentinel.models import TransactionType

BASE = datetime(2026, 1, 1, 8, 0, 0)
HIGH_RISK = ["IR", "KP", "SY"]
HISTORY_DAYS = 60  # established activity precedes every episode
EPISODE_SPREAD_DAYS = 30  # episodes start at a random time after that
LAUNDERING_HISTORY_TXNS = (0, 12)
LEGITIMATE_HISTORY_TXNS = (8, 40)


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


def _inject_history(rows: list[dict], rng: random.Random, account: str, count: int) -> None:
    """Ordinary small payments before the episode, labelled 0 for every entity."""
    for _ in range(count):
        _row(
            rows,
            account,
            f"{account}_CP{rng.randint(1, 5)}",
            rng.uniform(50, 900),
            rng.uniform(0, 24 * HISTORY_DAYS),
        )


def _structuring(
    rows: list[dict], rng: random.Random, account: str, t0: float, label: int, _factor: float
) -> None:
    for i in range(rng.randint(3, 5)):
        _row(
            rows,
            f"{account}_CASH",
            account,
            rng.uniform(9000, 9999),
            t0 + i * rng.uniform(8, 16),
            txn_type=TransactionType.CASH_DEPOSIT,
            is_laundering=label,
        )


def _rapid_movement(
    rows: list[dict], rng: random.Random, account: str, t0: float, label: int, factor: float
) -> None:
    inbound = rng.uniform(10000, 40000) * factor
    outbound = inbound * rng.uniform(0.92, 1.0)
    first_share = rng.uniform(0.4, 0.6)
    _row(rows, f"{account}_SRC", account, inbound, t0, is_laundering=label)
    _row(rows, account, f"{account}_OUT1", outbound * first_share,
         t0 + rng.uniform(1, 12), is_laundering=label)
    _row(rows, account, f"{account}_OUT2", outbound * (1 - first_share),
         t0 + rng.uniform(12, 30), is_laundering=label)


def _round_amount(
    rows: list[dict], rng: random.Random, account: str, t0: float, label: int, factor: float
) -> None:
    for i in range(rng.randint(3, 5)):
        amount = max(1000.0, round(rng.randint(3, 9) * 1000 * factor, -3))
        _row(rows, account, f"{account}_DST", amount, t0 + i * rng.uniform(20, 36),
             is_laundering=label)


def _threshold_avoidance(
    rows: list[dict], rng: random.Random, account: str, t0: float, label: int, _factor: float
) -> None:
    for i in range(rng.randint(2, 4)):
        _row(rows, account, f"{account}_PAYEE", rng.uniform(9550, 9950),
             t0 + i * rng.uniform(24, 48), is_laundering=label)


def _high_risk_geography(
    rows: list[dict], rng: random.Random, account: str, t0: float, label: int, factor: float
) -> None:
    _row(rows, account, f"{account}_ABROAD", rng.uniform(2000, 30000) * factor, t0,
         receiver_country=rng.choice(HIGH_RISK), is_laundering=label)
    _row(rows, f"{account}_ABROAD2", account, rng.uniform(2000, 30000) * factor,
         t0 + rng.uniform(6, 48), sender_country=rng.choice(HIGH_RISK), is_laundering=label)


def _velocity_spike(
    rows: list[dict], rng: random.Random, account: str, t0: float, label: int, _factor: float
) -> None:
    for _ in range(8):  # quiet baseline in the weeks before the surge
        _row(rows, account, f"{account}_REG", rng.uniform(100, 300), t0 - rng.uniform(24, 24 * 25))
    for h in range(rng.randint(3, 5)):
        _row(rows, account, f"{account}_REG", rng.uniform(3000, 9000), t0 + h, is_laundering=label)


def _inject_network_ring(rows: list[dict]) -> None:
    _row(rows, "RING_A", "RING_B", 5000, 0, is_laundering=1)
    _row(rows, "RING_B", "RING_C", 4900, 24, is_laundering=1)
    _row(rows, "RING_C", "RING_A", 4800, 48, is_laundering=1)


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
            rng.uniform(0, 24 * (HISTORY_DAYS + EPISODE_SPREAD_DAYS)),
            txn_type=rng.choice(
                [TransactionType.TRANSFER, TransactionType.CARD, TransactionType.CHEQUE]
            ),
            is_laundering=0,
        )


_Shape = Callable[[list[dict], random.Random, str, float, int, float], None]

# (laundering prefix, legitimate look-alike prefix, activity shape)
_TYPOLOGIES: list[tuple[str, str, _Shape]] = [
    ("STRUCT_ACC", "RETAIL", _structuring),  # cash-intensive retailer
    ("PASS_ACC", "SWEEP", _rapid_movement),  # treasury sweep account
    ("LAYER_ACC", "CORP", _round_amount),  # corporate supplier payments
    ("THRESH_ACC", "INVOICE", _threshold_avoidance),  # regular contractor invoices
    ("GEO_ACC", "TRADE", _high_risk_geography),  # licensed trade or aid payments
    ("VELO_ACC", "PAYROLL", _velocity_spike),  # payroll run
]


def _episode_start(rng: random.Random) -> float:
    return 24 * (HISTORY_DAYS + rng.uniform(0, EPISODE_SPREAD_DAYS))


def generate_dataset(
    seed: int = 42,
    benign: int = 400,
    scale: int = 1,
    hard_negative_ratio: float = 5.0,
    laundering_amount_factor: float = 1.0,
    laundering_history_txns: tuple[int, int] = LAUNDERING_HISTORY_TXNS,
) -> pd.DataFrame:
    """Generate a reproducible synthetic dataset covering every typology.

    ``scale`` injects that many distinct laundering entities per typology.
    ``hard_negative_ratio`` sets how many *legitimate but rule-tripping* entities
    are injected per laundering entity. Set to 0 for a clean dataset.
    ``laundering_amount_factor`` shifts laundering amounts for rapid movement,
    round-amount and geography, to test whether a model survives changed amounts.
    ``laundering_history_txns`` sets the laundering history range. Matching
    ``LEGITIMATE_HISTORY_TXNS`` removes the only signal the generator plants.
    """
    rng = random.Random(seed)
    rows: list[dict] = []

    for i in range(scale):
        sfx = "" if i == 0 else f"_{i}"
        for prefix, _, shape in _TYPOLOGIES:
            account = f"{prefix}{sfx}"
            _inject_history(rows, rng, account, rng.randint(*laundering_history_txns))
            shape(rows, rng, account, _episode_start(rng), 1, laundering_amount_factor)
        if i == 0:
            _inject_network_ring(rows)

    for i in range(int(scale * hard_negative_ratio)):
        for _, prefix, shape in _TYPOLOGIES:
            account = f"{prefix}{i}"
            _inject_history(rows, rng, account, rng.randint(*LEGITIMATE_HISTORY_TXNS))
            shape(rows, rng, account, _episode_start(rng), 0, 1.0)

    _inject_benign(rows, rng, benign)

    df = pd.DataFrame(rows)
    return df.sort_values("timestamp").reset_index(drop=True)
