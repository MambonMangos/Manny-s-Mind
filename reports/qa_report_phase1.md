# QA Workstream Report (Phase 1) — QA Engineer

## Executive Summary

The test suite was rebuilt from exception-only to **assertion-based**, expanding from 17 to **33 passing tests** across four files. All Phase 1 files are lint-clean. The broader codebase has pre-existing lint debt (out of Phase 1 scope) — see Risks.

## Completed Work

1. **Rewrote `tests/test_v2_pipeline.py`** — replaced exceptions-only assertions with real behavioural checks.
2. **Added `tests/test_smoke.py`**:
   - Every `pages/*.py` parses/compiles.
   - `config/active.yaml` + all referenced version files are valid YAML and loadable.
   - DB initializes from models (table set matches expectations).
   - Logging setup is idempotent.
3. **Added `tests/test_scoring_weights.py`**:
   - `value_score` weights sum to **1.0** (guards the 0.30+0.32+0.15+0.08+0.08+0.02+0.05 invariant).
   - Active config matches `weights_v3` selection.
   - Weights within [0,1]; xGI monotonic.
4. **Added `tests/test_migrations.py`**:
   - `upgrade head` runs cleanly on a scratch DB.
   - Table parity between migration and live models.
   - Exactly one migration head.
5. **Ran full suite**: 33 passed. **Phase 1 files lint-clean** (`ruff check` on `app.py`, `utils/`, `database/database.py`, `services/api_client.py`, `services/data_loader.py`, `alembic/`, new tests).

## Test Inventory

| File | Covers |
|---|---|
| `tests/test_v2_pipeline.py` | End-to-end V2 pipeline behaviour |
| `tests/test_scoring_weights.py` | Weights integrity + active config |
| `tests/test_smoke.py` | Boot, page parse, config load, DB init |
| `tests/test_migrations.py` | Migration apply + schema parity |
| `tests/test_validation.py` | Validation engine metrics (pre-existing) |

## Risks

| Risk | Severity | Notes |
|---|---|---|
| **Pre-existing lint debt across codebase** (pages/, components/, engines/, older tests) | MEDIUM | ~300 issues (import sorting, unused imports, noqa) — pre-dates Phase 1; clean incrementally |
| Coverage of engines still thin (only pipeline + validation covered) | MEDIUM | Add per-engine unit tests as debt is refactored |
| No CI integration yet | MEDIUM | Blocked on git init; add lint+test gate immediately after |
| API-dependent tests can be flaky offline | LOW | Keep them fixture-based |

## Recommendations

1. Wire `pytest` + `ruff` into CI as the release gate (ready as soon as git exists). CI should lint **changed files** first, then the whole repo once the pre-existing debt is cleared.
2. Add tests for each engine as it is touched (unit-level, DB-independent via dependency injection to fix TD-6).
3. Keep the sum-to-1 weights test as a permanent invariant guard.

## Handoff

Owner: QA. 33/33 passing; Phase 1 files lint-clean. Any Phase 2 refactor must keep the suite green; engine-touch PRs should extend per-engine unit coverage. Full-repo lint cleanup is tracked as pre-existing debt (not a Phase 1 deliverable).
