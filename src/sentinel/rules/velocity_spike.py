"""Velocity Spike detection.

Typology: a sudden, anomalous jump in a customer's (here, an account's)
transaction value relative to that account's own historical baseline. Every
transaction ends a candidate recent window, so a spike is found wherever it sits
in the account's history. The baseline is the mean total of the earlier windows
in which the account was active, so quiet days do not dilute it and sparse but
steady activity is not mistaken for a spike. Overlapping hits form one episode,
reported once at its peak. This is a per-entity, behaviour-relative scenario —
the essence of a risk-based approach.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from sentinel.models import Alert, Severity, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.VELOCITY_SPIKE


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("velocity_spike", {})
    if not cfg.get("enabled", False):
        return []

    multiplier = cfg.get("multiplier", 3.0)
    recent_window = timedelta(hours=cfg.get("recent_window_hours", 24))
    baseline_span = timedelta(days=cfg.get("baseline_window_days", 30))
    min_baseline_txns = cfg.get("min_baseline_txns", 5)
    severity = severity_from_config(cfg.get("severity"))

    by_account: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        by_account[t.sender_account].append(t)

    alerts: list[Alert] = []
    for account, txns in by_account.items():
        ordered = sort_by_time(txns)
        if len(ordered) <= min_baseline_txns:
            continue
        times = [t.timestamp for t in ordered]
        peak: list[Transaction] | None = None
        peak_total = 0.0
        peak_baseline = 0.0
        for end, end_time in enumerate(times):
            if end + 1 < len(times) and times[end + 1] == end_time:
                continue  # same-instant txns belong in one window
            recent_start = end_time - recent_window
            recent_from = bisect_left(times, recent_start)
            baseline = ordered[bisect_left(times, end_time - baseline_span) : recent_from]
            if len(baseline) < min_baseline_txns:
                continue

            baseline_per_window = _mean_active_window_total(baseline, recent_start, recent_window)
            recent = ordered[recent_from : end + 1]
            recent_total = sum(t.amount for t in recent)
            if recent_total < multiplier * baseline_per_window:
                continue

            if peak is not None and recent_start > peak[-1].timestamp:
                alerts.append(_spike_alert(account, peak, peak_baseline, severity))
                peak = None  # the previous episode is over
            if peak is None or recent_total > peak_total:
                peak, peak_total, peak_baseline = recent, recent_total, baseline_per_window

        if peak is not None:
            alerts.append(_spike_alert(account, peak, peak_baseline, severity))
    return alerts


def _mean_active_window_total(
    baseline: Sequence[Transaction], recent_start: datetime, recent_window: timedelta
) -> float:
    """Mean total per recent-window-sized bucket, counting only buckets with activity."""
    totals: dict[int, float] = defaultdict(float)
    for t in baseline:
        totals[(recent_start - t.timestamp) // recent_window] += t.amount
    return sum(totals.values()) / len(totals)


def _spike_alert(
    account: str, recent: list[Transaction], baseline_per_window: float, severity: Severity
) -> Alert:
    recent_total = sum(t.amount for t in recent)
    return build_alert(
        RULE_ID,
        account,
        recent,
        severity,
        evidence={
            "recent_total": round(recent_total, 2),
            "baseline_per_window": round(baseline_per_window, 2),
            "ratio": round(recent_total / baseline_per_window, 2),
            "recent_txn_count": len(recent),
        },
    )
