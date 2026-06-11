"""High-Risk Geography detection.

Typology: transfers to or from jurisdictions on a configurable high-risk
watchlist. Each qualifying transaction raises an alert against the local
(domestic-side) account. The watchlist is loaded from
config/high_risk_countries.yaml.
"""

from __future__ import annotations

from sentinel.config import load_high_risk_countries
from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config

RULE_ID = Typology.HIGH_RISK_GEOGRAPHY


def detect(
    transactions: list[Transaction],
    config: dict,
    high_risk: set[str] | None = None,
) -> list[Alert]:
    cfg = config.get("rules", {}).get("high_risk_geography", {})
    if not cfg.get("enabled", False):
        return []

    watchlist = high_risk if high_risk is not None else load_high_risk_countries()
    min_amount = cfg.get("min_amount", 1000)
    severity = severity_from_config(cfg.get("severity"))

    alerts: list[Alert] = []
    for t in transactions:
        if t.amount < min_amount:
            continue
        sender_hit = t.sender_country in watchlist
        receiver_hit = t.receiver_country in watchlist
        if not (sender_hit or receiver_hit):
            continue
        # Attach the alert to the domestic side (the account we monitor).
        entity = t.receiver_account if sender_hit else t.sender_account
        flagged = t.sender_country if sender_hit else t.receiver_country
        alerts.append(
            build_alert(
                RULE_ID,
                entity,
                [t],
                severity,
                evidence={
                    "flagged_country": flagged,
                    "direction": "inbound" if sender_hit else "outbound",
                    "amount": round(t.amount, 2),
                    "counterparty_country": flagged,
                },
            )
        )
    return alerts
