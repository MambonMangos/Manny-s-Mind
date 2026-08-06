"""Tests for the operational audit log (``services/audit.py``)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import AuditLog, Base
from services.audit import get_recent_audit_log, log_audit


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_log_audit_persists_entry(tmp_path):
    session = _session(tmp_path)
    try:
        log_audit(
            session,
            "ingest_results",
            resource="gameweek:5",
            detail={"status": "ok", "n_actuals": 3},
        )
        session.commit()

        rows = session.query(AuditLog).all()
        assert len(rows) == 1
        entry = rows[0]
        assert entry.action == "ingest_results"
        assert entry.resource == "gameweek:5"
        assert entry.detail == {"status": "ok", "n_actuals": 3}
        assert entry.actor, "actor must be resolved"
        assert entry.created_at is not None
    finally:
        session.close()


def test_get_recent_audit_log_orders_newest_first(tmp_path):
    session = _session(tmp_path)
    try:
        log_audit(session, "data_refresh", detail={"source": "sidebar"})
        log_audit(session, "ingest_results", resource="gameweek:1")
        log_audit(session, "ingest_results", resource="gameweek:2")
        session.commit()

        all_events = get_recent_audit_log(session)
        assert [e.resource for e in all_events] == ["gameweek:2", "gameweek:1", None]

        only_ingest = get_recent_audit_log(session, action="ingest_results")
        assert len(only_ingest) == 2

        limited = get_recent_audit_log(session, limit=1)
        assert len(limited) == 1
    finally:
        session.close()


def test_log_audit_with_explicit_actor(tmp_path):
    session = _session(tmp_path)
    try:
        log_audit(session, "data_refresh", actor="cron")
        session.commit()
        assert session.query(AuditLog).one().actor == "cron"
    finally:
        session.close()
