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

# Marker for a missing country (ISO reserves "XX" for user-assigned use).
UNKNOWN_COUNTRY = "XX"

# Country-name -> ISO 3166-1 alpha-2. Covers SAML-D's bank locations plus the
# watchlist jurisdictions and the names most likely to be confused with them.
_COUNTRY_ALIASES = {
    "AFGHANISTAN": "AF",
    "ALBANIA": "AL",
    "AUSTRIA": "AT",
    "FRANCE": "FR",
    "GERMANY": "DE",
    "INDIA": "IN",
    "IRAN": "IR",
    "IRAQ": "IQ",
    "IRELAND": "IE",
    "ITALY": "IT",
    "JAPAN": "JP",
    "MALAYSIA": "MY",
    "MALI": "ML",
    "MEXICO": "MX",
    "MOROCCO": "MA",
    "MYANMAR": "MM",
    "NETHERLANDS": "NL",
    "NIGERIA": "NG",
    "NORTH KOREA": "KP",
    "PAKISTAN": "PK",
    "SOUTH KOREA": "KR",
    "SPAIN": "ES",
    "SWEDEN": "SE",
    "SWITZERLAND": "CH",
    "SYRIA": "SY",
    "TURKEY": "TR",
    "UAE": "AE",
    "UK": "GB",
    "UNITED ARAB EMIRATES": "AE",
    "UNITED KINGDOM": "GB",
    "UNITED STATES": "US",
    "USA": "US",
    "YEMEN": "YE",
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
    """Map a country name or code to ISO alpha-2.

    Unmapped values pass through unchanged rather than being guessed: a truncated
    name can collide with a real code, e.g. "Ireland" would read as Iran ("IR").
    """
    if pd.isna(value):
        return UNKNOWN_COUNTRY
    code = str(value).strip().upper()
    return _COUNTRY_ALIASES.get(code, code) if code else UNKNOWN_COUNTRY


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


def read_saml_d_frame(
    path: str | Path,
    *,
    sample_frac: float | None = None,
    keep_laundering: bool = True,
    seed: int = 42,
) -> pd.DataFrame:
    """Read SAML-D into a (optionally stratified-sampled) DataFrame.

    The full SAML-D file is ~9.5M rows / ~1 GB, which is impractical to validate
    row-by-row interactively. When ``sample_frac`` is set we read in chunks and
    keep a reproducible fraction of *normal* rows; with ``keep_laundering`` we
    retain **all** labelled-laundering rows so the rare positives are not lost.
    The combined sample is returned with a unified ``timestamp`` column.

    Caveat: stratified sampling preserves class balance but breaks per-account
    temporal continuity, so account-level scenarios (structuring, round-amount,
    velocity) are weakened on a sample. Use a larger ``sample_frac`` (or the full
    file) for a faithful run of those rules.
    """
    if sample_frac is None:
        raw = pd.read_csv(path)
    else:
        import numpy as np

        rs = np.random.RandomState(seed)
        parts: list[pd.DataFrame] = []
        for chunk in pd.read_csv(path, chunksize=500_000):
            normal = chunk[chunk["Is_laundering"] == 0].sample(
                frac=sample_frac, random_state=rs
            )
            if keep_laundering:
                parts.append(chunk[chunk["Is_laundering"] == 1])
            parts.append(normal)
        raw = pd.concat(parts).reset_index(drop=True)

    # SAML-D stores Date and Time separately; combine into one timestamp.
    if "Date" in raw.columns and "Time" in raw.columns:
        raw["timestamp"] = pd.to_datetime(
            raw["Date"].astype(str) + " " + raw["Time"].astype(str), errors="coerce"
        )
    elif "timestamp" not in raw.columns:
        raise ValueError("SAML-D file lacks Date/Time or timestamp columns")
    return raw


def load_saml_d(
    path: str | Path,
    *,
    sample_frac: float | None = None,
    keep_laundering: bool = True,
    seed: int = 42,
) -> list[Transaction]:
    """Load the SAML-D CSV from ``path`` into validated Transaction models.

    See :func:`read_saml_d_frame` for the sampling semantics and caveats.
    """
    raw = read_saml_d_frame(
        path, sample_frac=sample_frac, keep_laundering=keep_laundering, seed=seed
    )
    normalised = normalise_frame(raw, column_map=SAML_D_COLUMN_MAP)
    return load_transactions(normalised)
