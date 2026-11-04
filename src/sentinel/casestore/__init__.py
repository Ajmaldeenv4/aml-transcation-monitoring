"""Case store: persistence for alerts, dispositions, SAR drafts, and an
immutable audit trail. SQLite by default; Postgres via the SENTINEL_DB_URL env var.
"""

from sentinel.casestore.db import get_session, init_db
from sentinel.casestore.errors import AuditImmutableError, InvalidTransition
from sentinel.casestore.repository import CaseStore

__all__ = ["AuditImmutableError", "CaseStore", "InvalidTransition", "get_session", "init_db"]
