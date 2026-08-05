# Development Guide — Manny's FPL House

## 1. Developer Setup

See `README.md` for the quick start. In short:

```bash
git clone <repo-url>
cd moneyball-fpl
uv venv .venv
uv pip install -r requirements-dev.txt   # includes runtime + dev deps
cp .env.example .env
streamlit run About.py                      # → http://localhost:8501
```

## 2. Tooling

| Tool | Purpose | Command |
|---|---|---|
| `uv` | Environment & dependency manager | `uv pip install -r requirements.txt` |
| `streamlit` | Web app framework | `streamlit run About.py` |
| `pytest` | Test runner | `pytest` |
| `ruff` | Linter / formatter | `ruff check .` / `ruff format .` |
| `alembic` | Database migrations | `alembic upgrade head` |

Run the linter and tests before opening a PR:

```bash
ruff check .
pytest
```

## 3. Branch Strategy

`main` is always deployable. Work happens on short-lived feature branches; **one logical change per branch** (small, reviewable changes).

```
main  ──────────── ● ──────────────── ●
                    \                /
feature/weights-v4  └── ● ───────────┘
```

Conventions:

- `feature/<what>` — new feature or change (e.g., `feature/externalize-config`).
- `fix/<what>` — bug fix.
- `chore/<what>` — maintenance, docs, infra.
- `docs/<what>` — documentation-only changes.

Merge via squash/rebase so `main` history stays linear. Every commit message should explain **what** and **why** — a major decision should still make sense six months later.

## 4. Commit Conventions

- Imperative subject line (≤ 72 chars), optional body.
- Reference the workstream/phase when relevant (e.g., `(phase1)`).
- Never commit `.env`, `data/*.db`, `*.log`, or secrets (see `.gitignore`).

## 5. Code Organisation Rules

- **One source of truth.** Shared constants → `utils/constants.py`. Tunable weights → `config/`. Derived features → Feature Store (`features/store.py`). Do not duplicate a formula in a second module; coordinate ownership before implementing.
- **Ownership.** Platform = deployment/config/logging; Data = database/API; ML = prediction/features; QA = tests; Tech Writer = docs. Cross-discipline changes require coordination (documented in the relevant report).
- **Prediction freeze.** Until after GW1 validation, no changes to projection/weight/validation behaviour. Architectural refactors must be behaviour-preserving and covered by tests.
- **Zero silent failures.** Fail loudly with a clear log/error; never silently swallow or degrade (e.g., no silent SSL downgrade).

## 6. Testing Expectations

- New logic ships with tests (unit for services/engines, smoke for boot).
- Convert any exception-only test into assertion-based validation.
- Run the migration tests when schema changes (`tests/test_migrations.py`).

## 7. Running a Local Sanity Loop

```bash
pytest -q                                # fast feedback
streamlit run About.py                      # manual check
alembic upgrade head                      # after model changes
```

## 8. Getting Help

- Architecture overview: `docs/architecture.md`
- Configuration reference: `docs/configuration.md`
- Deployment: `docs/deployment.md`
- Database/migrations: `docs/database.md`
- Prediction system: `docs/prediction.md`
- Validation platform: `docs/validation.md`
- Operations & release: `docs/operations.md`
