"""Operational audit log — append-only trail of mutating actions.

Complements the domain-level ``decision_log`` (what the model recommended)
with an operational record of *who did what*: result ingestion, validation
cycles, manual data refreshes, and persist-to-ledger comparisons.

Rows are never updated or deleted; the caller commits the session.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from database.models import AuditLog

logger = logging.getLogger(__name__)


def log_audit(
    session: Session,
    action: str,
    *,
    actor: str | None = None,
    resource: str | None = None,
    detail: dict | None = None,
) -> AuditLog:
    """Record one audit event and flush it to the session.

    Audit logging must never break the primary action, so failures are
    logged and swallowed. The caller decides when to commit.
    """
    if actor is None:
        try:
            from utils.team_context import get_current_team_id

            team_id = get_current_team_id()
            actor = f"team:{team_id}" if team_id is not None else "unknown"
        except Exception:  # noqa: BLE001 - never let audit resolution fail the action
            actor = "unknown"

    entry = AuditLog(action=action, actor=actor, resource=resource, detail=detail)
    session.add(entry)
    try:
        session.flush()
    except Exception:
        logger.exception("Failed to persist audit event action=%s", action)
        return entry

    logger.info("audit action=%s actor=%s resource=%s", action, actor, resource)
    return entry


def get_recent_audit_log(
    session: Session,
    limit: int = 100,
    action: str | None = None,
) -> list[AuditLog]:
    """Return the most recent audit events, newest first."""
    query = session.query(AuditLog).order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc()
    )
    if action:
        query = query.filter(AuditLog.action == action)
    return query.limit(limit).all()
