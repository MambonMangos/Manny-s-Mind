# Platform Workstream Report (Phase 1) — DevOps / Full-stack Engineer

## Executive Summary

Phase 1 delivered a deployment foundation: environment-driven configuration, dependency pinning, logging, repository hygiene, and a full documentation package. **Version control is established locally** — git 2.55.0 installed via micromamba (no CLT required) — with the initial commit on `main`. Pushing to GitHub is deferred pending remote access. The app runs cleanly on localhost.

## Completed Work

1. **Configuration externalization** — all deployment-specific values moved out of source code into env vars with safe defaults:
   - `utils/env.py` — loads `.env` at import.
   - `utils/constants.py` — env-driven `FPL_TEAM_ID`, `FPL_API_BASE_URL`, `FPL_USER_AGENT`, `FPL_API_TIMEOUT`, `FPL_API_MAX_RETRIES`, `FPL_API_BACKOFF_BASE`, `FPL_API_ALLOW_INSECURE_SSL` (default `false`), `DATA_STALENESS_SECONDS`; helper functions `_env_int/_env_float/_env_bool`.
   - `services/api_client.py` — TLS fallback now gated behind `FPL_API_ALLOW_INSECURE_SSL` (never on by default; no silent downgrade).
   - `services/data_loader.py` — uses `DATA_STALENESS_SECONDS`.
   - `.env.example` expanded to document every variable.
2. **Dependencies pinned** — `requirements.txt` locked to exact versions (Streamlit 1.60.0, SQLAlchemy 2.0.51, pandas 3.0.5, requests 2.34.2, Alembic 1.18.5, etc.); `requirements-dev.txt` adds pytest + ruff.
3. **Logging** — `utils/logging_setup.py` (`setup_logging()`), wired in `app.py`, env-configurable `LOG_LEVEL` / `LOG_FILE`.
4. **Repository hygiene** — `.gitignore` (adds `*.log`, `logs/`), MIT `LICENSE`, rewritten `README.md`.
5. **Version control** — git 2.55.0 installed into `~/git-tools` via micromamba (no CLT/GitHub needed); `git init -b main`; initial commit `41168e8` (112 files). Repo-local identity `mannysmac <mannysmac@localhost>` (change with `git config user.name/user.email`).
6. **License**: MIT, per owner decision.

## Risks

| Risk | Severity | Status |
|---|---|---|
| No git binary on host | RESOLVED | git 2.55.0 via micromamba (`~/git-tools/bin/git`) |
| No GitHub remote (access unavailable) | LOW | Local repo on `main`, commit `41168e8`; push when access returns |
| SQLite single-writer limits concurrent users | MEDIUM | Acceptable for single-user; Postgres for public hosting (Phase 2+) |
| `.env` drift between environments | MEDIUM | Mitigated via `.env.example`; CI validation recommended |
| No external monitoring/log shipping | LOW | Add synthetic health check + log aggregation when public |

## Recommendations

1. Add a GitHub remote and push `main` when access is available; then enable CI.
2. Containerise with a Dockerfile (Python 3.12 + pinned deps + persistent `data/` volume) — Phase 2.
3. Add a CI pipeline (lint → test → migration check) once a remote exists.
4. Validate `.env.example` against the config loader in CI to prevent drift.

## Handoff

Owner: Platform. Phase 1 config/env/logging work is complete and verified. Version control is established locally (`main`, commit `41168e8`). Next step when GitHub access returns: add a remote, push `main`, and enable the CI pipeline.
