"""Case-store errors, kept apart so they stay stable for every importer."""

from __future__ import annotations


class InvalidTransition(Exception):
    """The requested change is not allowed from the alert's current status."""


class AuditImmutableError(Exception):
    """Something tried to change or delete an audit entry."""
