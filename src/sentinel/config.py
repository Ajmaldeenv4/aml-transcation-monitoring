"""Configuration loading for the rules engine and watchlists."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

# Repo root = three parents up from this file (src/sentinel/config.py -> repo).
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@cache
def load_rules_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config/rules.yaml (or an explicit override path)."""
    return load_yaml(Path(path) if path else CONFIG_DIR / "rules.yaml")


@cache
def load_high_risk_countries(path: str | Path | None = None) -> set[str]:
    """Return the set of high-risk country codes from the watchlist file."""
    data = load_yaml(Path(path) if path else CONFIG_DIR / "high_risk_countries.yaml")
    return {c.strip().upper() for c in data.get("high_risk_countries", [])}
