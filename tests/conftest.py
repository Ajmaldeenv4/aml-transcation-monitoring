"""Shared test helpers: a small transaction factory for golden cases."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sentinel.models import Transaction, TransactionType

BASE = datetime(2026, 1, 1, 9, 0, 0)


def txn(
    txn_id: str,
    sender: str,
    receiver: str,
    amount: float,
    *,
    hours: float = 0.0,
    days: float = 0.0,
    txn_type: TransactionType = TransactionType.TRANSFER,
    sender_country: str = "US",
    receiver_country: str = "US",
    is_laundering: bool = False,
) -> Transaction:
    """Build a Transaction at BASE + offset. Keeps golden cases terse and readable."""
    return Transaction(
        txn_id=txn_id,
        timestamp=BASE + timedelta(hours=hours, days=days),
        sender_account=sender,
        receiver_account=receiver,
        amount=amount,
        txn_type=txn_type,
        sender_country=sender_country,
        receiver_country=receiver_country,
        is_laundering=is_laundering,
    )


@pytest.fixture
def make_txn():
    return txn
