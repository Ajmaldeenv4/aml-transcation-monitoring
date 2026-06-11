"""Network / Mule Ring detection (advanced, optional).

Typology: a cluster of accounts cycling funds among themselves, e.g.
A -> B -> C -> A. We build a directed graph of transfers within the window and
search for simple cycles whose length is within the configured bounds. Disabled
by default in config; enable to demonstrate the graph-based scenario.
"""

from __future__ import annotations

from collections import defaultdict

from sentinel.models import Alert, Transaction, Typology
from sentinel.rules._common import build_alert, severity_from_config

RULE_ID = Typology.NETWORK_RING


def detect(transactions: list[Transaction], config: dict) -> list[Alert]:
    cfg = config.get("rules", {}).get("network_ring", {})
    if not cfg.get("enabled", False):
        return []

    min_len = cfg.get("min_cycle_length", 3)
    max_len = cfg.get("max_cycle_length", 6)
    window = cfg.get("window_hours", 168) * 3600
    severity = severity_from_config(cfg.get("severity"))

    # Adjacency with the representative transaction for each directed edge.
    edges: dict[str, dict[str, Transaction]] = defaultdict(dict)
    for t in transactions:
        if t.sender_account == t.receiver_account:
            continue
        edges[t.sender_account].setdefault(t.receiver_account, t)

    cycles = _find_cycles(edges, min_len, max_len)
    alerts: list[Alert] = []
    seen: set[str] = set()
    for cycle in cycles:
        txns = [edges[a][b] for a, b in zip(cycle, cycle[1:] + cycle[:1], strict=False)]
        span = (
            max(t.timestamp for t in txns) - min(t.timestamp for t in txns)
        ).total_seconds()
        if span > window:
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


def _find_cycles(
    edges: dict[str, dict[str, Transaction]], min_len: int, max_len: int
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
