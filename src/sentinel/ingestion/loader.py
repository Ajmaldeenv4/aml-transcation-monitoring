"""Load and normalise synthetic transaction data into validated models.

The primary source is SAML-D, but the normaliser is column-map driven so the
generator's output (and other synthetic sources) flow through the same path.
The ``is_laundering`` ground-truth label is preserved for honest ML evaluation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sentinel.models import Transaction, TransactionType

# SAML-D's column names -> Sentinel schema. SAML-D combines Date + Time, so we
# handle that in load_saml_d before normalising.
SAML_D_COLUMN_MAP = {
    "Sender_account": "sender_account",
    "Receiver_account": "receiver_account",
    "Amount": "amount",
    "Payment_currency": "currency",
    "Sender_bank_location": "sender_country",
    "Receiver_bank_location": "receiver_country",
    "Payment_type": "txn_type",
    "Is_laundering": "is_laundering",
}

# Map common payment-type strings onto our TransactionType enum.
_TYPE_ALIASES = {
    "cash deposit": TransactionType.CASH_DEPOSIT,
    "cash withdrawal": TransactionType.CASH_WITHDRAWAL,
    "cash": TransactionType.CASH_DEPOSIT,
    "cheque": TransactionType.CHEQUE,
    "credit card": TransactionType.CARD,
    "debit card": TransactionType.CARD,
    "card": TransactionType.CARD,
    "ach": TransactionType.TRANSFER,
    "transfer": TransactionType.TRANSFER,
    "cross-border": TransactionType.WIRE,
    "wire": TransactionType.WIRE,
}

# Common country-name -> ISO alpha-2 normalisation (SAML-D uses names).
_COUNTRY_ALIASES = {
    "UK": "GB",
    "UNITED KINGDOM": "GB",
    "USA": "US",
    "UNITED STATES": "US",
    "UAE": "AE",
}


def _coerce_type(value: object) -> TransactionType:
    if isinstance(value, TransactionType):
        return value
    key = str(value).strip().lower()
    # Canonical enum values (e.g. "cash_deposit") first, then human-text aliases.
    try:
        return TransactionType(key)
    except ValueError:
        return _TYPE_ALIASES.get(key, TransactionType.OTHER)


def _coerce_country(value: object) -> str:
    code = str(value).strip().upper()
    return _COUNTRY_ALIASES.get(code, code[:2] if len(code) >= 2 else "US")


def normalise_frame(df: pd.DataFrame, column_map: dict[str, str] | None = None) -> pd.DataFrame:
    """Rename columns to the Sentinel schema and coerce dtypes.

    Expects (after mapping) at least: txn_id, timestamp, sender_account,
    receiver_account, amount. Other fields fall back to model defaults.
    """
    out = df.rename(columns=column_map) if column_map else df.copy()

    if "txn_id" not in out.columns:
        out = out.reset_index(drop=True)
        out["txn_id"] = out.index.map(lambda i: f"T{i:08d}")

    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    out = out[out["amount"] > 0]
    return out


def _row_to_transaction(row: pd.Series) -> Transaction | None:
    try:
        return Transaction(
            txn_id=str(row["txn_id"]),
            timestamp=row["timestamp"].to_pydatetime(),
            sender_account=str(row["sender_account"]),
            receiver_account=str(row["receiver_account"]),
            amount=float(row["amount"]),
            currency=str(row.get("currency", "USD")),
            txn_type=_coerce_type(row.get("txn_type", "transfer")),
            sender_country=_coerce_country(row.get("sender_country", "US")),
            receiver_country=_coerce_country(row.get("receiver_country", "US")),
            is_laundering=bool(int(row.get("is_laundering", 0))),
        )
    except Exception:
        # Drop rows that fail validation rather than abort the whole load.
        return None


def load_transactions(df: pd.DataFrame) -> list[Transaction]:
    """Validate a normalised frame into a list of Transaction models."""
    txns = [_row_to_transaction(row) for _, row in df.iterrows()]
    return [t for t in txns if t is not None]


def load_saml_d(path: str | Path) -> list[Transaction]:
    """Load the SAML-D CSV from ``path`` into validated Transaction models."""
    raw = pd.read_csv(path)

    # SAML-D stores Date and Time separately; combine into one timestamp.
    if "Date" in raw.columns and "Time" in raw.columns:
        raw["timestamp"] = pd.to_datetime(
            raw["Date"].astype(str) + " " + raw["Time"].astype(str), errors="coerce"
        )
    elif "timestamp" not in raw.columns:
        raise ValueError("SAML-D file lacks Date/Time or timestamp columns")

    normalised = normalise_frame(raw, column_map=SAML_D_COLUMN_MAP)
    return load_transactions(normalised)
