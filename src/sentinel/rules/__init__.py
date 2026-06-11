"""Typology-based detection rules.

Each rule is a pure function ``(transactions, config) -> list[Alert]`` so it is
trivially unit-testable with golden cases. The :mod:`sentinel.rules.runner`
module loads config, runs every enabled rule, and aggregates the alerts.
"""

from sentinel.rules.runner import run_rules

__all__ = ["run_rules"]
