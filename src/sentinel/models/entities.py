"""Account and Customer models — the entities an alert attaches to."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RiskRating(str, Enum):
    """Customer risk rating from KYC/CDD (Customer Due Diligence)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Customer(BaseModel):
    """A customer (natural person or entity) under KYC.

    ``pep`` = Politically Exposed Person — a key risk-based-approach signal.
    """

    customer_id: str
    name: str = ""
    country: str = "US"
    pep: bool = False
    risk_rating: RiskRating = RiskRating.LOW
    business_type: str | None = None


class Account(BaseModel):
    """An account, owned by a customer."""

    account_id: str
    customer_id: str
    country: str = "US"
    opened: str | None = None
    linked_accounts: list[str] = Field(default_factory=list)
