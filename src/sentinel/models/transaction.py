"""The Transaction model — the atomic unit the rules engine reasons over."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TransactionType(str, Enum):
    """Payment instrument / channel. Cash vs. non-cash matters for structuring."""

    CASH_DEPOSIT = "cash_deposit"
    CASH_WITHDRAWAL = "cash_withdrawal"
    TRANSFER = "transfer"
    WIRE = "wire"
    CARD = "card"
    CHEQUE = "cheque"
    OTHER = "other"

    @property
    def is_cash(self) -> bool:
        return self in (TransactionType.CASH_DEPOSIT, TransactionType.CASH_WITHDRAWAL)


class Transaction(BaseModel):
    """A single validated, normalised transaction.

    ``is_laundering`` is the synthetic ground-truth label (from SAML-D or the
    generator). It exists ONLY to evaluate the ML layer honestly — it is never an
    input feature and never shown as a "true answer" in the analyst workflow.
    """

    model_config = {"frozen": True}

    txn_id: str
    timestamp: datetime
    sender_account: str
    receiver_account: str
    amount: float = Field(gt=0)
    currency: str = "USD"
    txn_type: TransactionType = TransactionType.TRANSFER
    sender_country: str = "US"
    receiver_country: str = "US"
    is_laundering: bool = False

    @field_validator("currency", "sender_country", "receiver_country")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def is_cross_border(self) -> bool:
        return self.sender_country != self.receiver_country
