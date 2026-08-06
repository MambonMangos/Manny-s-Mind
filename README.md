# Manny's FPL House

A data-driven Fantasy Premier League analytics platform built with Streamlit, SQLAlchemy, and Plotly.

> **Status:** Deployed and running locally against live FPL data; public launch is prepared (CI, onboarding, security hardening) but the app is **not yet publicly hosted**. Prediction and validation behaviour are frozen — no weight tuning or model changes until after GW1.

## Features

- **Player Rankings** — filter, sort, and rank every FPL player by configurable value scores.
- **Team Analysis** — aggregate stats across all 20 Premier League clubs.
- **Team History** — season-by-season performance and gameweek breakdowns.
- **Player Comparison** — head-to-head radar charts, fixture difficulty, and efficiency metrics.
- **Assistant Manager** — squad evaluation, transfer recommendations, chip strategy, future planning.
- **Model Analytics** — projection quality metrics, validation, experiment tracking.

## Quick Start

### Prerequisites

- **Python 3.12+** (3.12 is tested)
- No system libraries beyond a standard Python interpreter are required.

### Install

```bash
git clone <repo-url>
cd moneyball-fpl

# Create a virtual environment (uv recommended)
uv venv .venv
uv pip install -r requirements.txt

# Or with pip
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
pip install -r requirements.txt

# Developer dependencies (lint, tests)
uv pip install -r requirements-dev.txt

# Create your environment file
cp .env.example .env
```

### Run

```bash
streamlit run About.py
```

Open **http://localhost:8501** in your browser.

On first load the app initialises the SQLite database (`data/moneyball.db`) and fetches live data from the FPL API. Data is refreshed automatically when it is more than 1 hour old (configurable — see below).

### Tests

```bash
pytest
```

## Configuration

Configuration follows a strict hierarchy:

```
Environment Variables (.env)
          ↓
config/*.yaml  (versioned, active.yaml selects the active version)
          ↓
Safe Defaults  (utils/constants.py)
```

- **`.env`** — environment-specific values (database URL, API settings, logging). The visitor's FPL Team ID is **not** configuration — it is entered per session on the onboarding page (see `docs/onboarding.md`). See `.env.example`.
- **`config/`** — versioned YAML configs (weights, fixtures, minutes, prediction, bookmaker, features). The active version of each category is selected in `config/active.yaml`. Switch versions by editing that file — never overwrite old versions.

See `docs/configuration.md` for the full reference.

## Database

SQLite by default (`data/moneyball.db`). The schema is defined in `database/models.py` and managed with Alembic migrations in `alembic/`:

```bash
alembic upgrade head          # apply migrations
alembic revision --autogenerate -m "describe change"   # create a new migration
```

> The current database is at `data/moneyball.db`. A persistent volume must be provided in any containerised deployment — see `docs/deployment.md`.

## Project Layout

```
├── About.py                   # Streamlit entry point
├── pages/                    # Streamlit multi-page app
├── components/               # UI components (theme, charts, tables, sidebar)
├── database/                 # SQLAlchemy models, engine, CRUD
├── services/                 # Data loading, scoring, team/fixture services
├── engines/                  # Prediction & analysis engines
├── features/                 # Feature Store (single source of truth for features)
├── config/                   # Versioned YAML configuration
├── alembic/                  # Database migrations
├── utils/                    # Constants, config loader, env, logging
├── docs/                     # Documentation package
└── tests/                    # Test suite
```

## Documentation

See the `docs/` directory for the full documentation package:

| Guide | Purpose |
|---|---|
| `docs/architecture.md` | System architecture and data flow |
| `docs/stakeholders.md` | Workstream owners and routing decisions |
| `docs/engineering_workflow.md` | Leadership, roles, AI-assisted workflow, review & approval process |
| `docs/development.md` | Developer setup and contribution guide |
| `docs/deployment.md` | Production deployment guide |
| `docs/configuration.md` | Configuration reference |
| `docs/database.md` | Database and migration guide |
| `docs/prediction.md` | Prediction system architecture, engine ownership, tech debt |
| `docs/validation.md` | Validation platform guide |
| `docs/operations.md` | Operations manual and release checklist |

## License

MIT — see [LICENSE](LICENSE).
