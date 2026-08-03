# Phase 1 Report — Manny's FPL House

**Phase:** Deployment Foundation (Engineering Reorganization)
**Date:** 2026-08-02
**Status:** Complete (local version control done; GitHub remote deferred — no access)

## Summary

Phase 1 took the project from a working-but-undeployable prototype to a documented, configurable, tested, migration-managed foundation — without changing any prediction or validation behaviour.

## Deliverables by Workstream

### Platform (DevOps)
- Env-driven config: `utils/env.py`, `utils/constants.py`, `.env.example`
- TLS fallback disabled by default (`FPL_API_ALLOW_INSECURE_SSL`)
- Logging: `utils/logging_setup.py` wired into `app.py`
- Pinned deps: `requirements.txt`, `requirements-dev.txt`
- Repo hygiene: `.gitignore`, MIT `LICENSE`, rewritten `README.md`

### Data (Data Engineering)
- Alembic framework + baseline migration, verified zero schema drift vs live DB
- API client: configurable timeout/retry/backoff; TLS on by default

### ML (review-only)
- Engine ownership map, tech debt register (TD-1..9), post-GW1 roadmap
- **No prediction/weight/validation changes**

### QA
- **33 tests passing** (up from 17), assertion-based, migration + weights invariants covered
- Phase 1 files lint-clean; pre-existing codebase lint debt documented (out of scope)

### Technical Writer
- 9-doc package in `docs/`; README docs table current

## Verification Results

| Check | Result |
|---|---|
| `pytest` | 33 passed |
| `ruff check` (Phase 1 files) | clean |
| App boot | HTTP 200 on :8501 |
| Alembic `upgrade head` on scratch DB | 17 tables, matches live schema |
| Weights invariant (sum = 1.0) | held |

## Open Items

| Item | Owner | Blocker |
|---|---|---|
| ~~`git init` + initial commit~~ | Platform | **Done** — local repo on `main`, commit `41168e8` |
| Push to a remote (GitHub) | Platform | Remote access unavailable for now |
| CI pipeline (lint → test → migrations) | Platform/QA | GitHub Actions requires remote |
| Post-GW1: V1→V2 engine retirement, feature de-dup, CI consolidation | ML | GW1 actuals |
| Containerisation + Postgres for public hosting | Platform/Data | hosting decision (Phase 2) |

## Next Action

Version control is established locally (git 2.55.0 via micromamba, `main` branch, initial commit `41168e8`). When remote access returns, add a GitHub remote and push; then enable CI. Until then, keep using feature branches per `docs/development.md`.

## Per-Workstream Reports

`reports/platform_report_phase1.md` · `reports/data_report_phase1.md` · `reports/ml_report_phase1.md` · `reports/qa_report_phase1.md` · `reports/technical_writer_report_phase1.md`
