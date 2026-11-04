"""Feature engineering for alert risk scoring.

Each alert becomes one feature row built from the alert itself plus the history
of its entity (the account the alert concerns), up to the alert's last triggering
transaction so no feature can see the future. Features are deliberately
interpretable so SHAP explanations read like analyst reasoning.

The ground-truth label (``alert_label``) marks an alert as a true positive when
any of its triggering transactions is a labelled laundering transaction. This is
used ONLY for training/evaluation — never as a model input.
"""

from __future__ import annotations

from collections import defaultdict

from sentinel.config import load_high_risk_countries
from sentinel.models import Alert, Severity, Transaction, Typology

_SEVERITY_ORD = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}
_TYPOLOGIES = list(Typology)

# Stable, human-readable feature order (also used for SHAP labelling).
FEATURE_NAMES: list[str] = [
    "severity_ord",
    "num_triggering_txns",
    "total_amount",
    "max_amount",
    "mean_amount",
    "entity_txn_count",
    "entity_total_volume",
    "entity_cross_border_ratio",
    "high_risk_geo_hits",
    "cash_ratio",
    "round_amount_ratio",
    "first_txn_hour",
    *[f"typology_{t.value}" for t in _TYPOLOGIES],
]


def _index_by_entity(transactions: list[Transaction]) -> dict[str, list[Transaction]]:
    idx: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        idx[t.sender_account].append(t)
        idx[t.receiver_account].append(t)
    return idx


def build_feature_row(
    alert: Alert,
    txn_by_id: dict[str, Transaction],
    entity_index: dict[str, list[Transaction]],
    high_risk: set[str],
) -> list[float]:
    trig = [txn_by_id[i] for i in alert.triggering_txn_ids if i in txn_by_id]
    amounts = [t.amount for t in trig] or [0.0]
    history = entity_index.get(alert.entity_id, [])
    if trig:
        cutoff = max(t.timestamp for t in trig)
        history = [t for t in history if t.timestamp <= cutoff]

    cross_border = sum(1 for t in history if t.is_cross_border)
    geo_hits = sum(
        1 for t in trig if t.sender_country in high_risk or t.receiver_country in high_risk
    )
    cash = sum(1 for t in trig if t.txn_type.is_cash)
    round_amt = sum(1 for t in trig if t.amount % 1000 == 0)
    first_hour = trig[0].timestamp.hour if trig else 0

    row = [
        float(_SEVERITY_ORD[alert.severity]),
        float(len(trig)),
        float(sum(amounts)),
        float(max(amounts)),
        float(sum(amounts) / len(amounts)),
        float(len(history)),
        float(sum(t.amount for t in history)),
        float(cross_border / len(history)) if history else 0.0,
        float(geo_hits),
        float(cash / len(trig)) if trig else 0.0,
        float(round_amt / len(trig)) if trig else 0.0,
        float(first_hour),
    ]
    row.extend(1.0 if alert.rule_id is t else 0.0 for t in _TYPOLOGIES)
    return row


def build_feature_matrix(
    alerts: list[Alert], transactions: list[Transaction]
) -> tuple[list[list[float]], dict[str, Transaction], dict[str, list[Transaction]]]:
    txn_by_id = {t.txn_id: t for t in transactions}
    entity_index = _index_by_entity(transactions)
    high_risk = load_high_risk_countries()
    matrix = [
        build_feature_row(a, txn_by_id, entity_index, high_risk) for a in alerts
    ]
    return matrix, txn_by_id, entity_index


def alert_label(alert: Alert, txn_by_id: dict[str, Transaction]) -> int:
    """1 if any triggering transaction is a labelled laundering transaction."""
    return int(
        any(
            txn_by_id[i].is_laundering
            for i in alert.triggering_txn_ids
            if i in txn_by_id
        )
    )
