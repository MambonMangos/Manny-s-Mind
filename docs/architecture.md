# Architecture — Manny's FPL House

## Overview

Manny's FPL House is a data-driven Fantasy Premier League analytics platform. It is a **Streamlit multi-page web application** backed by a **SQLite database** populated from the public FPL API, with a layered analysis stack (services → feature store → engines).

```
┌──────────────────────────────────────────────────────────────────┐
│  Streamlit (app.py + pages/ + components/)                       │
│  ─ UI rendering, filters, charts, recommendations                │
├──────────────────────────────────────────────────────────────────┤
│  Services (services/)                                            │
│  ─ data loading, scoring, team/fixture data, pipeline orchestration│
├──────────────────────────────────────────────────────────────────┤
│  Feature Store (features/store.py) — SINGLE SOURCE OF TRUTH      │
│  ─ derived features per player (minutes, xGI, fixtures, market…) │
├──────────────────────────────────────────────────────────────────┤
│  Engines (engines/)                                              │
│  ─ projection, confidence, regression, minutes, fixture, etc.    │
├──────────────────────────────────────────────────────────────────┤
│  Data layer (database/)                                          │
│  ─ SQLAlchemy models, engine, CRUD, Alembic migrations           │
├──────────────────────────────────────────────────────────────────┤
│  External: FPL API (fantasy.premierleague.com/api)               │
└──────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Bootstrap** — `app.py` calls `ensure_data_loaded()` (`utils/helpers.py`), which initialises the database and fetches data from the FPL API when stale.
2. **Ingest** — `services/data_loader.py` fetches `bootstrap-static` (teams, players, gameweeks) and upserts into SQLite. Fixtures, team history, and picks are fetched on demand by `services/fixture_service.py` and `services/team_service.py`.
3. **Derive** — `services/scoring.py` normalises raw stats and computes the composite value score using the weights in `config/weights/`.
4. **Feature engineering** — `features/store.py` builds the Feature Store: a per-player, per-gameweek snapshot of derived features (minutes, xGI, fixture difficulty, market signals, regression flags, set pieces, trends).
5. **Prediction** — `services/pipeline.py` orchestrates the V2 prediction pipeline (`engines/projection_engine.py`, `confidence_engine.py`, etc.) producing projected points, confidence intervals, and opportunity scores.
6. **Presentation** — pages render rankings, comparisons, team analysis, assistant-manager recommendations, and model analytics.

## Layering Rules

- Pages must not touch the database directly beyond `get_session()` (see note below); logic lives in services/engines.
- Engines must consume features from the Feature Store rather than recomputing them (known technical debt — see `docs/prediction.md`).
- Every shared value lives in exactly one place (`utils/constants.py` for constants, `config/` for tunable weights).

## Configuration Architecture

```
Environment Variables (.env → utils/env.py)
        ↓
config/*.yaml  (versioned; active version chosen in config/active.yaml)
        ↓
Safe Defaults (utils/constants.py, utils/config.py)
```

- `utils/env.py` loads `.env` once at import time.
- `utils/config.py` loads and caches versioned YAML from `config/`.
- `utils/constants.py` exposes application constants, many sourced from environment variables with safe defaults.

## Session & Database Notes

- A single SQLite database (`data/moneyball.db`) is shared by the whole app (WAL mode, `check_same_thread=False`).
- Pages currently call `get_session()` individually — a known simplification to be consolidated (see `docs/database.md`).
- Schema changes are managed with Alembic (`alembic/`), baselined to the current schema.

## Key Directories

| Path | Responsibility | Owner |
|---|---|---|
| `pages/` | Streamlit pages | — |
| `components/` | UI components | — |
| `services/` | Application services & data loading | Data / ML |
| `engines/` | Prediction & analysis engines | ML |
| `features/` | Feature Store | ML |
| `database/` | ORM, CRUD, engine | Data |
| `config/` | Versioned YAML configuration | Platform |
| `alembic/` | Database migrations | Data |
| `utils/` | Constants, config, env, logging | Platform |
| `tests/` | Test suite | QA |
| `docs/` | Documentation | Technical Writer |
