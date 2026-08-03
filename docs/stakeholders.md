# Project Stakeholders — Manny's FPL House

The project is organised into five engineering workstreams. Every component has an owner; nothing drifts unowned.

## Workstream Owners

| Workstream | Owner | Scope |
|---|---|---|
| **Platform** | DevOps / Full-stack Engineer | Deployment, configuration, environment, logging, security, git, docs tooling |
| **Data** | Data Engineer | Database schema, Alembic migrations, FPL API reliability, data persistence |
| **ML** | ML / Analytics Engineer | Prediction engines, features, weights, validation, confidence calibration |
| **QA** | QA Engineer | Test coverage, linting, release gates, regression safety |
| **Technical Writer** | Documentation | Architecture, configuration, deployment, database, development, prediction, validation, operations |

## Routing Decisions

| Concern | Route to |
|---|---|
| Bug in a deployed environment / app won't start | Platform |
| Database schema change, migration, data quality | Data |
| Score formula, weights, projection, CI, model behaviour | ML |
| Tests failing, coverage gaps, lint | QA |
| Any doc file in `docs/` | Technical Writer |
| Config value changes (weights/versions) | ML (weights) / Platform (env) |
| New dependency / pinned version | Platform |

## Collaboration Rules

- **Prediction freeze**: no changes to projection/weight/validation behaviour until after GW1 validation. Refactors must be behaviour-preserving and covered by tests.
- **One source of truth**: shared constants → `utils/constants.py`; tunable weights → `config/`; derived features → Feature Store. Never duplicate a formula across modules.
- **Zero silent failures**: fail loudly with a clear log; no silent downgrade/degradation.
- **Cross-workstream changes** are coordinated and documented (see `docs/development.md`).

## Open Coordination Items

| Item | Owner(s) | Blocked on |
|---|---|---|
| Add GitHub remote + push `main` + enable CI | Platform | GitHub access (unavailable for now) |
| V1 → V2 engine retirement (TD-1) | ML + Data | GW1+ validation evidence |
| CI/variance single source (TD-3) | ML | None (behaviour-preserving refactor) |
| Public multi-user DB migration (SQLite → Postgres) | Data + Platform | Hosting decision, Phase 2+ |
