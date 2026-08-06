# Deployment Guide — Manny's FPL House

This guide assumes the reader has **never seen the project before**. It explains how to install, configure, initialise, run, upgrade, and recover the application.

## 1. Requirements

- **Python 3.12+** (3.12 is tested). No system libraries are required — all dependencies are pure-Python wheels.
- **Network access** to `https://fantasy.premierleague.com/api` (the public FPL API).
- **Persistence**: the database is a SQLite file (`data/moneyball.db`). A persistent volume is required for any containerised deployment.

## 2. Install

```bash
git clone <repo-url>
cd moneyball-fpl

# Recommended: uv
uv venv .venv
uv pip install -r requirements.txt

# Or pip
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify the install:

```bash
.venv/bin/python -c "import streamlit, sqlalchemy, pandas; print('deps OK')"
```

## 3. Configure

```bash
cp .env.example .env
```

Edit `.env` for your environment. The defaults are safe for local development. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/moneyball.db` | Database location |
| `FPL_API_BASE_URL` | `https://fantasy.premierleague.com/api` | FPL API endpoint |
| `FPL_API_ALLOW_INSECURE_SSL` | `false` | Never enable in production |
| `DATA_STALENESS_SECONDS` | `3600` | Refresh cadence for FPL data |
| `LOG_LEVEL` / `LOG_FILE` | `INFO` / unset | Logging level and file |

There is **no** `FPL_TEAM_ID` — the visitor's Team ID is runtime state set on
the onboarding page (see `docs/onboarding.md`).

See `docs/configuration.md` for the full reference.

## 4. Initialise the Database

Two equivalent ways:

**Alembic (recommended):**

```bash
alembic upgrade head
```

**Legacy ORM creation** (still performed automatically at startup by `ensure_data_loaded()`):

```bash
python -c "from database.database import init_db; init_db()"
```

On first run the app also fetches the full FPL dataset (~1–2 MB) from the API. This requires network access.

## 5. Start Streamlit

```bash
streamlit run About.py --server.headless true --server.port 8501
```

Open `http://localhost:8501`. The Streamlit server settings live in `.streamlit/config.toml`; port/address can also be overridden with `--server.*` flags or the `STREAMLIT_*` environment variables.

### Health check

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501   # expect 200
```

## 6. Run Tests

```bash
pytest                       # full suite
pytest tests/test_smoke.py   # fast boot smoke tests
```

## 7. Update Dependencies

Dependencies are pinned exactly (`==`) in `requirements.txt` / `requirements-dev.txt`. To update:

```bash
# See what's installed
uv pip list

# Install the latest allowed by a new pin, then update the file
uv pip install streamlit==<new-version>
```

Then re-run the full test suite. **Never change a pin without verifying the suite passes.**

## 8. Configuration System

- Tunable analytics config lives in `config/*.yaml`, one file per version per category.
- The **active version** of each category is set in `config/active.yaml`.
- To try a new weight set, create `config/weights/weights_vN.yaml` and switch `config/active.yaml` — never overwrite an existing version.
- The loader caches parsed YAML in-process; restart the app after switching versions (a reload API `invalidate_cache()` exists for programmatic use).

## 9. Upgrade Path

1. Pull the latest code.
2. Install any new dependencies (`uv pip install -r requirements.txt`).
3. Run migrations: `alembic upgrade head`.
4. Restart Streamlit.
5. Verify: health check + run the smoke tests + sanity-check a page.

## 10. Recovering from Common Problems

| Symptom | Likely cause | Fix |
|---|---|---|
| `HTTPError` / API timeout on load | FPL API unreachable or rate limited | Retry; the client already retries with backoff. Check `LOG_LEVEL=DEBUG`. |
| "No player data available" | Empty/stale database | Ensure network access, then trigger a refresh (`Refresh Data` in the sidebar) or delete `data/moneyball.db` and restart. |
| `sqlite3.OperationalError: unable to open database file` | `data/` directory missing or not writable | Create it: `mkdir -p data`; ensure the process user can write there. |
| Migration error on `alembic upgrade` | Database at an unexpected state | Run `alembic current` and `alembic history`. Never run `alembic stamp` without understanding it. |
| Streamlit won't start / port in use | Port conflict | `--server.port <other-port>`; or kill the stale process (`pkill -f "streamlit run"`). |
| Blank page / missing fonts | Google Fonts CDN blocked | Style falls back to system fonts; not blocking. |
| SSL verification errors | Certificates issue | Confirm `certifi` is up to date. Do **not** set `FPL_API_ALLOW_INSECURE_SSL=true` in production. |

## 11. Containerised Deployment (recommended for hosting)

- Provide a **persistent volume** for the SQLite database (the app state is not ephemeral-safe; see `docs/database.md`).
- Expose only port 8501 (or run behind a reverse proxy terminating TLS).
- Set `FPL_API_ALLOW_INSECURE_SSL=false` and a `LOG_FILE` pointing at a persistent, rotated log.
- Run migrations (`alembic upgrade head`) as a one-time container step before starting the app.
- See `docs/operations.md` for the release checklist and monitoring guidance.
