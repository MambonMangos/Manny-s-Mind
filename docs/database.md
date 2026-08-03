# Database Guide — Manny's FPL House

## 1. Overview

The application uses a single **SQLite** database by default (`data/moneyball.db`), accessed through **SQLAlchemy 2.x**. SQLite runs in WAL mode with foreign keys enabled (see `database/database.py`).

- **Engine**: `database/database.py` builds the engine from `DATABASE_URL`.
- **Models**: `database/models.py` defines all tables (single `Base` metadata).
- **CRUD**: `database/crud.py` provides the data-access functions.
- **Migrations**: `alembic/` manages schema versions.

## 2. Tables

| Table | Purpose | Notes |
|---|---|---|
| `teams` | Club metadata and strengths | 20 rows |
| `players` | Full player data from FPL bootstrap | ~600+ rows |
| `gameweeks` | Event metadata | 38 rows |
| `player_gameweek_stats` | Per-GW player history | future use |
| `price_history` | Daily price tracking | future use |
| `snapshots` | Weekly full-pool snapshots | future use |
| `player_snapshots` | Point-in-time player states (pre/post GW) | append-only |
| `prediction_versions` | Model version ledger | append-only, `config_hash` + `weights_snapshot` |
| `projections` | Projected points per player/GW/version | append-only |
| `experiment_runs` | A/B experiment tracking | |
| `decision_log` | Assistant-manager recommendations | |
| `recommendation_outcomes` | Outcomes vs recommendations | |
| `validation_metrics` | Per-version/GW accuracy metrics | |
| `error_classifications` | Rule-based error categorisation | |
| `engine_accuracy` | Per-engine contribution metrics | |
| `chip_state` | Chip usage tracking | |

## 3. Migration Strategy

**Current status:** Phase 1 established an Alembic baseline matching the live schema. `create_all()` at startup remains for backward compatibility; **new schema changes must ship as Alembic migrations**.

### Everyday workflow

```bash
# Apply pending migrations (deploy step)
alembic upgrade head

# Create a new migration from model changes
alembic revision --autogenerate -m "describe the change"
# ⚠️ always review the generated file before committing

# Apply one step / roll back one step
alembic upgrade +1
alembic downgrade -1

# Inspect state
alembic current      # where the DB is
alembic history      # full migration history
alembic heads        # latest revisions
```

### Configuration

- `alembic.ini` — default `sqlalchemy.url = sqlite:///data/moneyball.db`.
- `alembic/env.py` — wires `target_metadata = Base.metadata` and overrides the URL from `DATABASE_URL` when set (same variable the app uses).

### Baseline

- The baseline migration (`alembic/versions/129653672751_baseline_schema.py`) recreates the full schema and was verified against the live database (identical table sets).
- Existing databases created by `create_all()` are equivalent to the baseline; no data migration is required.

## 4. Rollback Strategy

- **Code**: every migration has a `downgrade()`. `alembic downgrade -1` reverses the last change.
- **Data**: for destructive migrations, back up the DB file first (`cp data/moneyball.db data/moneyball.db.bak`). SQLite is a single file — a file-level copy is a complete backup.
- **Restore**: stop the app, replace the file, restart. Restore + `alembic upgrade head` will re-apply migrations if the backup predates them.

## 5. Indexes & Constraints

- Primary keys are explicit (`autoincrement=False` where the source API supplies IDs).
- Foreign keys on the prediction/validation tables are indexed (`index=True`).
- Known gap (technical debt): `Player.team_id` and several legacy tables lack indexes. Full scans are acceptable at current scale but should be addressed as the dataset grows (see `docs/prediction.md`).

## 6. Connection Handling

- `get_session()` returns a SQLAlchemy session from a module-level sessionmaker.
- `check_same_thread=False` allows use from Streamlit's threads.
- **Note:** several pages open sessions directly (`get_session()` / `close()`). A shared context manager (`with db_session()`) is recommended future consolidation to guarantee closing under exceptions.

## 7. Persistence & Deployment

- The DB is a **file** — a containerised deployment **must** mount a persistent volume at `data/`.
- SQLite is single-writer; concurrent multi-user writes are not supported. For public multi-user hosting, migrate to a client/server database (e.g., PostgreSQL) — Phase 2+.
- Data freshness is tracked in-process (`services/data_loader.py`); after a restart the first page load re-fetches from the FPL API.

## 8. API Data Reliability

The FPL API client (`services/api_client.py`) provides:

- 30s timeout (configurable via `FPL_API_TIMEOUT`).
- Exponential backoff retries (3 by default; `FPL_API_MAX_RETRIES`).
- Retry on HTTP 429 (honours `Retry-After`) and 5xx.
- Retry on connection errors/timeouts.
- **TLS verification** on by default; the insecure fallback is disabled unless `FPL_API_ALLOW_INSECURE_SSL=true` (never in production).

Known API risk: `fetch_all_picks()` issues up to 38 sequential requests for a full season history (see `services/team_service.py`). Monitor rate-limit behaviour under public load.
