# Architecture — Manny's FPL House

## Overview

Manny's FPL House is a data-driven Fantasy Premier League analytics platform. It is a **Streamlit multi-page web application** backed by a **SQLite database** populated from the public FPL API, with a layered analysis stack (services → feature store → engines).

```
┌──────────────────────────────────────────────────────────────────┐
│  Streamlit (About.py + pages/ + components/)                      │
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

1. **Onboarding gate** — every personalized page (and the home page) calls `require_team()` (`utils/team_context.py`). New visitors see the welcome/onboarding page (`components/onboarding.py`); a Team ID is validated against the FPL API (`services/team_validation.py`) before it becomes the session's active team. See `docs/onboarding.md`.
2. **Bootstrap** — `About.py` calls `ensure_data_loaded()` (`utils/helpers.py`), which initialises the database and fetches data from the FPL API when stale.
3. **Ingest** — `services/data_loader.py` fetches `bootstrap-static` (teams, players, gameweeks) and upserts into SQLite. Fixtures, team history, and picks are fetched on demand by `services/fixture_service.py` and `services/team_service.py`.
4. **Derive** — `services/scoring.py` normalises raw stats and computes the composite value score using the weights in `config/weights/`.
5. **Feature engineering** — `features/store.py` builds the Feature Store: a per-player, per-gameweek snapshot of derived features (minutes, xGI, fixture difficulty, market signals, regression flags, set pieces, trends).
6. **Prediction** — `services/production_predictor.py` runs the **V3 production model** (`engines/expected_projection_engine.py`, `xPts = xPts/90 × expected minutes / 90`) and persists it append-only; V2 (`services/pipeline.py` → `projection_v2`) continues running as a **shadow / control** model. Both are written to the prediction ledger so they can be validated against actuals over time.
7. **League Intelligence** — `services/league_intelligence/` layers league context (effective ownership, differentials, mini-league/rival analysis) **on top of** the V3 production projections to shape recommendations only; it never modifies prediction values (see `docs/league_intelligence.md`).
8. **Presentation** — pages render rankings, comparisons, team analysis, assistant-manager recommendations, and model analytics.

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

## Team Context & Session Architecture

The viewer's FPL Team ID is **runtime state, not configuration**. There is no
default team — an unvalidated visitor has no team, never Manny's team.

```
Anonymous Visitor
        ↓
Enter Team ID  (components/onboarding.py)
        ↓  validated against the FPL API (services/team_validation.py)
Session Team Context  (utils/team_context.py ↔ session_state.team_id)
        ↓
Every personalized service reads get_current_team_id()
```

- `utils/team_context.py` is the single provider: `get_current_team_id()`,
  `set_current_team_id()`, `clear_current_team_id()`, `is_onboarded()`,
  `seed_from_url()` (URL pre-fill hint, never auto-trusted), and
  `require_team()` (the page gate — renders onboarding and stops the script
  when no team exists).
- Team identity lives only in Streamlit session memory. Nothing is persisted,
  nothing is logged (API client redacts `/entry/<id>` path segments), and
  sessions are isolated by Streamlit, so no visitor inherits another's team.
- A `?team_id=` URL parameter only pre-fills the onboarding input; the team
  must still be validated by the visitor.
- This layer is deliberately thin so a future login system can provide a
  persistent user profile to the same provider without changing call sites.

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
| `services/league_intelligence/` | League-aware strategy layer (analysis + recommendations) | ML |
| `engines/` | Prediction & analysis engines | ML |
| `features/` | Feature Store | ML |
| `database/` | ORM, CRUD, engine | Data |
| `config/` | Versioned YAML configuration | Platform |
| `alembic/` | Database migrations | Data |
| `utils/` | Constants, config, env, logging | Platform |
| `tests/` | Test suite | QA |
| `docs/` | Documentation | Technical Writer |
