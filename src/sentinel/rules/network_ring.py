"""Network / Mule Ring detection (advanced, optional).

Typology: a cluster of accounts cycling funds among themselves, e.g.
A -> B -> C -> A. We build a directed graph of transfers, search for simple
cycles whose length is within the configured bounds, then look for one transfer
on every edge inside a single window. Disabled by default in config; enable to
demonstrate the graph-based scenario.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config, sort_by_time

RULE_ID = Typology.NETWORK_RING


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("network_ring", {})
    if not cfg.get("enabled", False):
        return []

    min_len = cfg.get("min_cycle_length", 3)
    max_len = cfg.get("max_cycle_length", 6)
    window = timedelta(hours=cfg.get("window_hours", 168))
    severity = severity_from_config(cfg.get("severity"))

    # Adjacency with every transaction on each directed edge, oldest first.
    edges: dict[str, dict[str, list[Transaction]]] = defaultdict(dict)
    for t in sort_by_time(transactions):
        if t.sender_account == t.receiver_account:
            continue
        edges[t.sender_account].setdefault(t.receiver_account, []).append(t)

    cycles = _find_cycles(edges, min_len, max_len)
    alerts: list[Alert] = []
    seen: set[str] = set()
    for cycle in cycles:
        legs = [edges[a][b] for a, b in zip(cycle, cycle[1:] + cycle[:1], strict=False)]
        txns = _first_ring_in_window(legs, window)
        if txns is None:
            continue
        entity = min(cycle)  # canonical entity for the ring
        alert = build_alert(
            RULE_ID,
            entity,
            txns,
            severity,
            evidence={
                "cycle": cycle,
                "cycle_length": len(cycle),
                "total_amount": round(sum(t.amount for t in txns), 2),
            },
        )
        if alert.alert_id not in seen:
            seen.add(alert.alert_id)
            alerts.append(alert)
    return alerts


def _first_ring_in_window(
    legs: Sequence[list[Transaction]], window: timedelta
) -> list[Transaction] | None:
    """Return one transaction per leg, all within ``window``, earliest such set first."""
    anchors = sorted({t.timestamp for leg in legs for t in leg})
    for anchor in anchors:
        picked: list[Transaction] = []
        for leg in legs:
            i = bisect_left(leg, anchor, key=lambda t: t.timestamp)
            if i == len(leg) or leg[i].timestamp - anchor > window:
                break
            picked.append(leg[i])
        else:
            return picked
    return None


def _find_cycles(
    edges: dict[str, dict[str, list[Transaction]]], min_len: int, max_len: int
) -> list[list[str]]:
    """Find simple directed cycles within [min_len, max_len]. Deduplicated by node set."""
    results: list[list[str]] = []
    seen_sets: set[frozenset[str]] = set()

    def dfs(start: str, node: str, path: list[str]) -> None:
        if len(path) > max_len:
            return
        for nxt in edges.get(node, {}):
            if nxt == start and len(path) >= min_len:
                key = frozenset(path)
                if key not in seen_sets:
                    seen_sets.add(key)
                    results.append(list(path))
            elif nxt not in path and len(path) < max_len:
                dfs(start, nxt, [*path, nxt])

    for node in list(edges):
        dfs(node, node, [node])
    return results
