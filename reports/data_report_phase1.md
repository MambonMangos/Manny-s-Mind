# Data Workstream Report (Phase 1) — Data Engineer

## Executive Summary

Alembic migrations are live, with a baseline matching the existing schema (verified against both the model metadata and the live database). API reliability was hardened via configurable timeout/retry/backoff, and the security-crippling TLS fallback is now disabled by default.

## Completed Work

1. **Alembic migration framework**:
   - `alembic init`; `alembic/env.py` wired to `DATABASE_URL` + `Base.metadata` (same variable the app uses).
   - `alembic.ini` default `sqlite:///data/moneyball.db`.
   - Baseline migration `129653672751_baseline_schema` — full schema in one migration, verified on a scratch DB:
     - **17 tables** (incl. `alembic_version`) match `database/models.py` exactly.
     - **No missing tables** vs. the live DB (16 user tables + version table) → zero schema drift.
2. **API reliability** (`services/api_client.py`):
   - 30s timeout (configurable `FPL_API_TIMEOUT`).
   - Exponential backoff, 3 retries (`FPL_API_MAX_RETRIES`, `FPL_API_BACKOFF_BASE`).
   - Retries on 429 (honours `Retry-After`) and 5xx; retries on connection errors/timeouts.
   - **TLS verification on by default**; the insecure fallback only fires if `FPL_API_ALLOW_INSECURE_SSL=true` (never in production).
3. **Persistence docs** — `docs/database.md` (tables, migrations, rollback, connection handling, backup).
4. **DB tests** — `tests/test_migrations.py` (upgrade head, schema parity, single head).

## Risks

| Risk | Severity | Notes |
|---|---|---|
| SQLite is single-file/single-writer | MEDIUM | Fine single-user; must mount `data/` volume when containerised |
| `fetch_all_picks()` up to 38 sequential requests for full season | MEDIUM | Rate-limit risk under load; monitor 429s |
| Cold-start freshness reset on restart (in-process staleness) | LOW | Persist last-refresh timestamp (Phase 2) |
| Missing indexes on some FKs (`Player.team_id`, etc.) | LOW | Full scans acceptable now; index as data grows |

## Recommendations

1. **Migration policy**: new schema changes ship as Alembic migrations; `create_all()` remains only for bootstrap compatibility.
2. Replace direct `get_session()/close()` in pages with a shared `with db_session()` context manager to guarantee closes under exceptions.
3. Persist data-freshness timestamp in the DB to survive restarts.
4. When hosting publicly, migrate to PostgreSQL (Alembic already supports it; only URL + volume change).

## Handoff

Owner: Data. Alembic baseline is verified and safe. The migration-then-`upgrade head` deploy sequence in `docs/operations.md` is the reference procedure.
