"""API-key identity for write endpoints.

The audit trail records who acted, so the actor must come from a credential
rather than from text the caller supplies. ``SENTINEL_API_KEYS`` holds
``analyst:key`` pairs separated by commas. With no keys configured every write is
rejected: the service fails closed.
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import Header, HTTPException


def _configured_keys() -> list[tuple[str, str]]:
    pairs = (p.partition(":") for p in os.environ.get("SENTINEL_API_KEYS", "").split(","))
    return [(name.strip(), key.strip()) for name, _, key in pairs if name.strip() and key.strip()]


def current_analyst(x_api_key: Annotated[str | None, Header()] = None) -> str:
    """Return the analyst who owns the presented key, or reject the request."""
    presented = (x_api_key or "").encode()
    analyst = None
    for name, key in _configured_keys():
        if hmac.compare_digest(presented, key.encode()):
            analyst = name
    if analyst is None:
        raise HTTPException(status_code=401, detail="missing or invalid API key")
    return analyst
