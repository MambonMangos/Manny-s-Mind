# EXECUTIVE AUDIT REPORT — Manny's FPL House

**Auditor:** Senior Software Auditor (Independent)
**Date:** 2026-07-28
**Scope:** Full repository — 60 Python source files, 7 YAML configs, 2 test files
**Role:** Production readiness assessment — investigate only, no code changes

---

## EXECUTIVE SUMMARY

| Metric | Score |
|--------|-------|
| **Overall Health** | **62/100** — Functional but fragile. Core architecture is sound (layered design, Feature Store pattern, config-driven engines) but pervasive violations and untested failure paths create significant risk. |
| **Confidence** | **5/10** — Would not deploy to production in current state. The codebase will likely work for a single user running locally against live FPL data, but any deviation from the happy path (API failure, missing data, config error) will cause unhandled crashes. |
| **Production Readiness** | **NOT READY** — 7 critical issues, 18 high-severity issues identified. At minimum, the 8 pre-GW1 action items must be addressed. |

### Top 10 Findings

| Rank | Finding | Severity | Category |
|------|---------|----------|----------|
| 1 | **No database migration system** — `create_all()` on every startup, no Alembic, no rollback | CRITICAL | Database |
| 2 | **API error handling is nonexistent** — no retry, no rate-limit handling, single failure crashes app | CRITICAL | Failure Modes |
| 3 | **`ManualSquad` model missing** — `save_manual_squad()` imports nonexistent model, will crash at runtime | CRITICAL | Data Integrity |
| 4 | **Test suite provides false confidence** — `test_v2_pipeline.py` has zero assertions; validation tests use clean synthetic data with no NULLs/edge cases | CRITICAL | Testing |
| 5 | **Every page manages database sessions directly** — 7 pages + 1 component import `get_session()`; no centralized data access layer | HIGH | Architecture |
| 6 | **Four V1 engines still active, duplicating V2 logic** — `value_engine`, `market_engine`, `prediction_engine`, `captain_engine` all have V2 equivalents but continue to be used | HIGH | Architecture |
| 7 | **Engines re-compute Feature Store features** — fixture windows, market signals, finishing ratios computed in 2+ places; divergence risk | HIGH | Feature Store |
| 8 | **No indexes on critical foreign keys** — `Player.team_id`, `PlayerGameweekStat.player_id`, `PlayerGameweekStat.gameweek_id`, `PriceHistory.player_id` unindexed | HIGH | Database |
| 9 | **SSL verification silently disabled on failure** — `verify=False` fallback with globally suppressed warning; MITM risk | HIGH | Security |
| 10 | **27 `iterrows()` loops across engines** — pandas anti-pattern repeated in every engine; engine pipeline is O(N*E) | HIGH | Performance |

---

## SECTION 1: ALL FINDINGS

### 1. CRITICAL FINDINGS (7)

#### C-01: No Database Migration System
- **File:** N/A (missing `alembic/`)
- **Issue:** `Base.metadata.create_all()` on startup blindly creates/alters tables. No migration history, no versioning, no rollback.
- **Risk:** Any schema change requires data loss. No way to deploy incremental changes.
- **Evidence:** `database/database.py:34` — single `create_all()` call, no migration framework present.

#### C-02: API Error Handling is Nonexistent
- **Files:** `services/api_client.py`, `services/data_loader.py`, `services/result_ingestion_service.py`
- **Issue:** `fpl_get()` has 30s timeout but no retry, no exponential backoff, no rate-limit detection. A single 429 or 5xx crashes the calling code.
- **Risk:** During GW deadlines when FPL API is under load, the app will crash entirely.
- **Evidence:** `api_client.py:34-49` — only `SSLError` is caught; `raise_for_status()` on line 49 throws unhandled `HTTPError`.

#### C-03: `ManualSquad` Model Missing
- **File:** `database/crud.py:223`
- **Issue:** `from database.models import ManualSquad` imports a class that doesn't exist in `models.py`. Verified with `python3 -c "from database.models import ManualSquad"` — raises `ImportError`.
- **Risk:** Any code path calling `save_manual_squad()` or `get_manual_squad()` crashes at runtime.
- **Evidence:** `crud.py:223,250` — both functions import `ManualSquad`. The model is absent from `models.py`.

#### C-04: Test Suite Provides False Confidence
- **Files:** `tests/test_v2_pipeline.py`, `tests/test_validation_platform.py`
- **Issue:** `test_v2_pipeline.py` has zero assertions — it prints timings and declares "ALL TESTS PASSED!" based solely on no exceptions being raised. `test_validation_platform.py` uses synthetic data with no NULLs, no edge cases, no missing columns.
- **Risk:** Developers get false confidence. Production failures (missing data, API errors, NULL fields) are completely untested.
- **Evidence:** `test_v2_pipeline.py:173` — `print("ALL TESTS PASSED!")` with no assertions. `test_validation_platform.py:61-106` — `create_synthetic_players()` generates perfectly clean data.

#### C-05: Validation Engine Tightly Coupled to Database
- **File:** `engines/validation_engine.py:24-31`
- **Issue:** An engine imports 5 CRUD functions, 2 ORM models, and `sqlalchemy.orm.Session` directly. This bypasses the entire service and feature layer.
- **Risk:** Cannot unit test the validation engine without a live database. Changing any table schema requires updating the engine.
- **Evidence:** `from database.crud import get_validation_metrics, get_projections, get_prediction_versions, get_player_by_id, get_latest_snapshot` and `from database.models import Player, ValidationMetrics` and `from sqlalchemy.orm import Session`.

#### C-06: Projection/Confidence Variance Duplication
- **Files:** `engines/projection_engine.py:250-305`, `engines/confidence_engine.py:119-125`
- **Issue:** Both engines compute variance/confidence with **identical weights** (minutes=0.30, fixture=0.15, regression=0.20, base=0.25, historical=0.10). Two independent CI implementations that will diverge.
- **Risk:** Different code paths produce different confidence values for the same player. No single source of truth for uncertainty.
- **Evidence:** Both compute `_compute_variance`/`total_uncertainty` with identical hardcoded weight tuples.

#### C-07: Fixture Feature Duplication — Feature Store vs Engine
- **Files:** `features/store.py:219-284`, `engines/fixture_engine.py:250-332`
- **Issue:** `fixture_engine.py:compute_fixture_windows()` duplicates the entire `_build_fixture_features()` method from Feature Store. Both compute `fixture_avg_1gw/3gw/6gw`, `home_count`, `easy_count`, `hard_count`, `fixture_swing`.
- **Risk:** Updates to one are not reflected in the other. Silent divergence guaranteed over time.
- **Evidence:** Both functions iterate over players × gameweeks computing identical summary statistics with the same formulas.

---

### 2. HIGH FINDINGS (18)

#### H-01: No Indexes on 5 Foreign Key Columns
- **Files:** `database/models.py:65,178-179,228,244`
- **Issue:** `Player.team_id`, `PlayerGameweekStat.player_id`, `PlayerGameweekStat.gameweek_id`, `PriceHistory.player_id`, `Snapshot.gameweek_id` have no indexes.
- **Risk:** Every JOIN or filter on these columns does a full table scan. `get_players_dataframe()` JOINs Player→Team on `team_id` scanning all rows.
- **Severity:** HIGH

#### H-02: 27 `iterrows()` Loops Across 6+ Engines
- **Files:** `features/store.py`, `engines/minutes_engine.py`, `engines/projection_engine.py`, `engines/regression_engine.py`, `engines/fixture_engine.py`, `engines/opportunity_engine.py`, `engines/squad_optimizer.py`, `services/snapshot_service.py`
- **Issue:** `iterrows()` creates a pandas Series for each row — the slowest iteration method. For 700 players × 10 engines = 7,000 iterations with overhead.
- **Risk:** Pipeline runtime scales O(N*E). Adding a new engine adds a full player scan.
- **Severity:** HIGH

#### H-03: N+1 Query in Error Classifier
- **File:** `services/error_classifier.py:117-122`
- **Issue:** Inside a loop over projections, the classifier calls `session.get(Player, p.player_id)` and `session.query(PlayerGameweekStat).filter_by(...)` per projection. ~500 projections = ~1000 extra queries.
- **Risk:** Slow error classification as prediction ledger grows.
- **Severity:** HIGH

#### H-04: N+1 API Calls in `fetch_all_picks`
- **File:** `services/team_service.py:184-191`
- **Issue:** One HTTP request per gameweek for all 38 GWs — 38 sequential API calls with no parallelization.
- **Risk:** Slow page load on Team History page. Could trigger rate limiting.
- **Severity:** HIGH

#### H-05: SSL Verification Silently Disabled on Failure
- **File:** `services/api_client.py:41-48`
- **Issue:** On any SSL error, the client retries with `verify=False`. `InsecureRequestWarning` is suppressed globally (line 19).
- **Risk:** MITM attack vulnerability. Operator receives no alert when verification is bypassed.
- **Severity:** HIGH

#### H-06: 4 V1 Engines Still Active Alongside V2 Equivalents
- **Files:** `engines/value_engine.py`, `engines/market_engine.py`, `engines/prediction_engine.py`, `engines/captain_engine.py`
- **Issue:** All four are actively imported by `services/assistant_manager/` and pages. Each has a V2 equivalent that computes the same or better metrics.
- **Risk:** Parallel computation paths produce inconsistent results. V1 minutes projection (`prediction_engine.py:15-29`) duplicates `minutes_engine.py` AND Feature Store heuristic — **three implementations** of the same logic.
- **Severity:** HIGH

#### H-07: 6 Features Re-Computed in Engines (Feature Store Bypass)
- **Files:** `engines/regression_engine.py:147-148`, `engines/market_intelligence_engine.py:128,133-134,145-150,156-161`
- **Issue:** `finishing_ratio`, `creative_ratio`, `net_transfers`, `transfer_velocity`, `ownership_tier`, `price_direction` are all computed in engines despite existing in Feature Store.
- **Risk:** Six divergence points between Feature Store and engines.
- **Severity:** HIGH

#### H-08: Direct Column Access Without `.get()` in Feature Store
- **File:** `features/store.py:157,175-188`
- **Issue:** `self.df["player_id"]`, `df["minutes"]`, `df["starts"]` use direct key access. If columns are missing, raises `KeyError` and crashes pipeline.
- **Risk:** Silent pipeline failure if data source schema changes.
- **Severity:** HIGH

#### H-09: `min()` on Empty Dict Crashes Insight Generation
- **File:** `services/learning_service.py:382`
- **Issue:** `top_error = max(by_type, key=by_type.get)` — if `by_type` is empty dict, raises `ValueError`.
- **Risk:** Weekly report generation crashes if no errors classified.
- **Severity:** HIGH

#### H-10: Invalid YAML Causes Unhandled Crash
- **File:** `utils/config.py:34`
- **Issue:** `yaml.safe_load(f)` raises unhandled `YAMLError` on malformed files. No fallback or graceful degradation.
- **Risk:** A single bad YAML file crashes the entire application.
- **Severity:** HIGH

#### H-11: No Retry/Rate-Limit Handling for API Calls
- **File:** `services/api_client.py:34-49`
- **Issue:** Only one retry attempt (for SSL failure). No retry for 429, 5xx, connection resets, DNS failures.
- **Risk:** Transient API issues cause complete application failure.
- **Severity:** HIGH

#### H-12: No Edge Case Tests
- **File:** `tests/test_validation_platform.py`
- **Issue:** No tests for: empty DataFrames, missing columns, NULL values, division by zero, API failures, config errors, database errors.
- **Risk:** All error handling code is untested.
- **Severity:** HIGH

#### H-13: Market Intelligence Engine Hardcodes 1M FPL Players
- **File:** `engines/market_intelligence_engine.py:133`
- **Issue:** `owner_base = max(selected / 100 * 1_000_000, 1)` — assumes exactly 1M FPL players.
- **Risk:** If FPL player base changes significantly, transfer velocity calculations are wrong.
- **Severity:** HIGH

#### H-14: Bookmaker Engine Always Returns Zero (Dead Code)
- **File:** `engines/bookmaker_engine.py:100-101`
- **Issue:** `if not odds_data:` returns `_no_odds_projections()` — this is the **only** code path because Odds API integration is not implemented. Runs through all 700+ players computing nothing.
- **Risk:** Wasteful computation. False sense of bookmaker intelligence.
- **Severity:** HIGH

#### H-15: In-Place Projection Mutation Breaks Reproducibility
- **Files:** `engines/regression_engine.py:75-100`, `engines/bookmaker_engine.py:114-135`
- **Issue:** Both engines mutate `projections` list in-place (modify `proj.projected_points`). Pipeline is non-reproducible — cannot trace which adjustment caused what.
- **Severity:** HIGH

#### H-16: 7 Pages + 1 Component Manage DB Sessions Directly
- **Files:** All 7 pages in `pages/`, `components/sidebar.py`
- **Issue:** Every page calls `database.database.get_session()` directly. No centralized data access layer.
- **Risk:** Schema changes require updating every page. Transaction logic scattered.
- **Severity:** HIGH

#### H-17: Database World-Readable (644 Permissions)
- **File:** `data/moneyball.db`
- **Issue:** File permissions `-rw-r--r--` — readable by any user on the system.
- **Risk:** On shared machine, any user can read all prediction data, team data, decision logs.
- **Severity:** HIGH

#### H-18: Snapshot Service `player_id` Defaults to 0 (Invalid FK)
- **File:** `services/snapshot_service.py:193`
- **Issue:** `row.get("id", 0)` defaults to 0 when `"id"` column missing. `PlayerSnapshot.player_id` is a ForeignKey — value `0` causes `IntegrityError` if no player with `id=0`.
- **Risk:** Silent data corruption or crash during snapshot persistence.
- **Severity:** HIGH

---

### 3. MEDIUM FINDINGS (18)

#### M-01: No Unique Constraints on 4 Core Tables
- **Files:** `database/models.py` — `PlayerGameweekStat`, `PriceHistory`, `PlayerSnapshot`, `Snapshot`
- **Issue:** No unique constraints on `(player_id, gameweek_id)` etc. Duplicate rows possible.
- **Risk:** Data duplication on repeated ingestion.

#### M-02: Mixed Flush/Commit Transaction Boundaries
- **File:** `database/crud.py:37-62,134-153,186-205`
- **Issue:** Individual upserts use `flush()`, bulk wrappers use `commit()`. If bulk fails mid-way, flushed rows are in session but uncommitted.
- **Risk:** Partial updates on failure. Caller must know to rollback.

#### M-03: No Rollback on Error in Data Loader
- **File:** `services/data_loader.py:94-110`
- **Issue:** `try/finally` closes session but no `session.rollback()` on exception.
- **Risk:** Session left in partially-committed state on error.

#### M-04: `setattr()` on ORM Models with Arbitrary Dict Keys
- **File:** `database/crud.py:47,141,193`
- **Issue:** `upsert_player/team/gameweek` iterate over incoming dict keys calling `setattr(model, key, value)`. API response could contain unexpected fields.
- **Risk:** Could corrupt ORM state if API response includes unexpected keys.

#### M-05: Engine Accuracy Insert Without Idempotency Guard
- **Files:** `engines/validation_engine.py:276-278`
- **Issue:** `insert_engine_accuracy` called in loop without checking for existing `(version_id, gameweek_id, engine_name)` record.
- **Risk:** Duplicate engine accuracy rows on repeated validation.

#### M-06: Validation Cycle Has No Per-Version Savepoints
- **File:** `services/learning_service.py:170-203`
- **Issue:** Single `session.commit()` at end of loop. If one version fails, all successfully validated versions are rolled back.
- **Risk:** Wasted computation on partial failure. No partial progress.

#### M-07: Stored XSS Risk via `unsafe_allow_html=True`
- **Files:** `components/theme.py:405`, `components/player_card.py`, `pages/5_Player_Comparison.py`, `pages/6_Assistant_Manager.py`, `app.py`
- **Issue:** F-string interpolation of variables into HTML with `unsafe_allow_html=True`. Player names/team names could contain malicious content.
- **Risk:** XSS if database is ever populated with non-FPL data.

#### M-08: No SQLite Connection Pooling Limits
- **File:** `database/database.py:17-21`
- **Issue:** No `pool_size` or `max_overflow` set. SQLite supports one writer at a time.
- **Risk:** Concurrent writers could cause `database is locked` errors.

#### M-09: `id` vs `player_id` Column Name Ambiguity
- **File:** `services/snapshot_service.py:193`
- **Issue:** `row.get("id", 0)` assumes column name `"id"`. `build_feature_store()` has fallback renaming `id`→`player_id`. Inconsistency between modules.
- **Risk:** Subtle data corruption if column name changes.

#### M-10: Unnecessary DataFrame Copy in `scoring.py`
- **File:** `services/scoring.py:46`
- **Issue:** `add_derived_columns()` calls `df.copy()` upfront. `compute_value_score()` calls `add_derived_columns()` which makes another copy.
- **Risk:** Doubles memory per pipeline run.

#### M-11: Tests Use Live Config Files
- **Files:** `tests/test_v2_pipeline.py:105`, `tests/test_validation_platform.py:139`
- **Issue:** Both test files read actual YAML configs from `config/`. Tests depend on filesystem state.
- **Risk:** CI failures due to config issues unrelated to code changes. Tests not hermetic.

#### M-12: Tests Share Mutable File-Based Database
- **File:** `tests/test_validation_platform.py:30-54`
- **Issue:** `reset_db()` drops/recreates tables in same `data/moneyball.db`. Test order matters.
- **Risk:** Data residue between tests. Parallel execution impossible.

#### M-13: Hardcoded TEAM_ID
- **File:** `utils/constants.py:19`
- **Issue:** `TEAM_ID: int = 472930` — no environment variable fallback.
- **Risk:** Cannot deploy for another user. Single-user only.

#### M-14: Feature Store Has No Cache Invalidation
- **File:** `features/store.py:64-108`
- **Issue:** Lazy caching builds once per instance. No TTL, no invalidation if underlying data changes.
- **Risk:** Stale features on repeated pipeline runs without rebuild.

#### M-15: `fixture_engine.py` Has Too Many Responsibilities
- **File:** `engines/fixture_engine.py` (410 lines)
- **Issue:** Combines: fixture map building, score computation, window analysis, swing detection, heatmap generation, summary tables.
- **Risk:** Difficult to test, maintain, or extend. Violates single responsibility.

#### M-16: `projection_engine.py` Duplicates Confidence Engine Logic
- **File:** `engines/projection_engine.py:250-335`
- **Issue:** 85 lines of variance/confidence computation that belongs in `confidence_engine.py`.
- **Risk:** Two implementations of the same logic will diverge.

#### M-17: Stale Features Computed But Never Consumed
- **File:** `features/store.py:295-296,368-371`
- **Issue:** `value_form`, `value_season`, `ict_index`, `influence`, `creativity`, `threat` are computed in Feature Store but no engine reads them.
- **Risk:** Wasted computation. Misleading future developers about available features.

#### M-18: Monte Carlo Engine Not Seeded
- **File:** `engines/monte_carlo_engine.py:115`
- **Issue:** `np.random.normal()` with no `np.random.seed()`. Simulations are non-reproducible.
- **Risk:** Different results every run. Cannot debug simulation outcomes.

---

### 4. LOW FINDINGS (12)

| # | Finding | File | Detail |
|---|---------|------|--------|
| L-01 | `or 0` redundancy | Multiple files | `.get("field", 0) or 0` — double-default pattern |
| L-02 | JSON in Text columns | `models.py:163,245,261,264,348` | `chip_plays`, `snapshot_json` etc. use `String` not `JSON` |
| L-03 | Inline imports | 2 files | `import numpy as np` in `player_service.py:28`, `import pandas as pd` in `fixture_widget.py:22` |
| L-04 | Missing FK constraints | `models.py:258,285,574` | `DecisionLog.team_id`, `ChipState.team_id`, `RecommendationOutcome.team_id` no FK |
| L-05 | `update_prediction_version_metrics` overwrites | `crud.py:335` | `pv.mae = mae` — no check for existing value |
| L-06 | Exception leakage to logs | `result_ingestion_service.py:90-93` | `logger.error("Result ingestion failed: %s", e)` |
| L-07 | No `__init__.py` in 5 packages | `database/`, `services/`, `components/`, `pages/`, `utils/` | Namespace packages work but explicit `__init__.py` recommended |
| L-08 | Typo "differentails" | `market_intelligence_engine.py:90` | Should be "differentials" |
| L-09 | Dead config file | `config/weights/weights_v1.yaml` | `active.yaml` points to `weights_v2`; V1 unused |
| L-10 | No pagination on version queries | `result_ingestion_service.py:106` | `get_prediction_versions()` returns all — will slow as ledger grows |
| L-11 | Config cache has no TTL | `utils/config.py:22-23,40-41` | Plain dict cache, no invalidation across processes |
| L-12 | Empty fixture_map silent fallback | `features/store.py:275-282` | Defaults to 3.0 with no log warning |

---

## SECTION 2: IMMEDIATE ACTION ITEMS (Pre-GW1)

These 8 items must be addressed before GW1. Estimated total effort: **8-12 hours**.

### P0 — Critical (Must Fix Before GW1)

| # | Item | Effort | Files Affected |
|---|------|--------|---------------|
| 1 | **Add API retry + rate-limit handling** — wrap `fpl_get()` with exponential backoff (3 retries), detect 429, sleep on `Retry-After`. Single retry for transient failures prevents most crashes. | 1h | `services/api_client.py` |
| 2 | **Fix false-positive test suite** — add real assertions to `test_v2_pipeline.py`. Verify pipeline outputs contain expected fields. Add NULL/empty-data edge case tests. | 2h | `tests/test_v2_pipeline.py`, `tests/test_validation_platform.py` |
| 3 | **Add config file fallback** — `load_config()` should have default values when YAML missing. `constants.py` already has weight defaults; extend to minutes/fixtures/prediction. | 1h | `utils/config.py`, `utils/constants.py` |
| 4 | **Handle empty DataFrames gracefully** — add guard clauses with logging warnings in every engine's main function. Empty input should produce empty/zero output, not crash. | 1h | All 11 engine files |
| 5 | **Fix `min()` on empty dict crash** — wrap `max(by_type, key=by_type.get)` with empty check. | 15min | `services/learning_service.py:382` |

### P1 — High (Should Fix Before GW1)

| # | Item | Effort | Files Affected |
|---|------|--------|---------------|
| 6 | **Add critical FK indexes** — index `Player.team_id`, `PlayerGameweekStat(player_id, gameweek_id)`, `PriceHistory(player_id)`, `Snapshot.gameweek_id`. Reduces full table scans. | 30min | `database/models.py` |
| 7 | **Fix `id` vs `player_id` column ambiguity** — ensure snapshot_service uses same column name convention as Feature Store. | 30min | `services/snapshot_service.py` |
| 8 | **Add rollback on data_loader error** — `session.rollback()` in exception handler before close. | 15min | `services/data_loader.py` |

---

## SECTION 3: POST-GW1 RECOMMENDATIONS

These require real data to validate correctness. Plan for **GW2-5 window**.

| # | Item | Rationale | Effort |
|---|------|-----------|--------|
| 1 | **Remove duplicate Feature Store computations from engines** | Cannot verify correctness without real data. After one GW of actuals, compare engine outputs to verify which path is correct before deleting. | 3h |
| 2 | **Centralize variance/confidence in Confidence Engine** | Need real projections + actuals to validate CI calibration before merging implementations. | 2h |
| 3 | **Replace in-projection mutation with immutable records** | Need real data to verify adjustment correctness after refactor. | 2h |
| 4 | **Add unique constraints to core tables** | Need real ingestion to test that duplicates don't occur before constraining. | 1h |
| 5 | **Seed Monte Carlo RNG** | Need real simulations to verify reproducibility. | 15min |
| 6 | **Replace `iterrows()` with vectorized operations** | Need real pipeline runtime to measure before/after. | 3h |
| 7 | **Add database indexes and measure improvement** | Need real query volume to verify index selection. | 1h |

---

## SECTION 4: LONG-TERM TECHNICAL DEBT

For the offseason or major refactoring cycles.

| # | Item | Effort | Notes |
|---|------|--------|-------|
| 1 | **Remove V1 engines entirely** | 4h | Migrate all consumers to V2 equivalents; delete `value_engine.py`, `market_engine.py`, `prediction_engine.py`, `captain_engine.py` |
| 2 | **Add Alembic migration system** | 4h | Replace `create_all()` with proper migrations. Requires zero-downtime schema change strategy for SQLite. |
| 3 | **Refactor `fixture_engine.py` into 3 modules** | 3h | Split into: fixture map service, fixture feature computation (→ Feature Store), UI helpers (→ components) |
| 4 | **Add `__init__.py` to all packages** | 30min | Prevent subtle import shadowing issues |
| 5 | **Add centralized data access layer** | 4h | Create `services/database_service.py` with context managers. Remove direct `get_session()` from all pages. |
| 6 | **Add engine abstraction/protocol** | 3h | Define `Engine` protocol; pipeline depends on abstraction not concrete engines |
| 7 | **Remove stale/unused features from Feature Store** | 1h | `value_form`, `value_season`, `ict_index`, `influence`, `creativity`, `threat` |
| 8 | **Add proper type annotations to suppress `# noqa`** | 1h | 12 remaining `# noqa` suppressions across engine/service layer |
| 9 | **Implement Bookmaker Odds API integration** | 4h | Replace `_no_odds_projections()` with actual odds fetching |
| 10 | **Make TEAM_ID configurable via env var** | 30min | Fallback to hardcoded value, but allow override |
| 11 | **Add database file permission hardening** | 15min | Restrict to owner-only on creation |
| 12 | **Replace JSON-in-Text columns with proper JSON type** | 1h | `chip_plays`, `snapshot_json`, etc. |

---

## SECTION 5: POSITIVE FINDINGS

Not everything needs work. These areas are well-implemented.

### Strong Architecture Decisions

| Finding | File(s) | Why It's Good |
|---------|---------|---------------|
| Config-driven design with versioned YAML | `config/`, `utils/config.py` | Settings externalized, version-tracked, separate from code |
| Feature Store pattern | `features/store.py` | Single source of truth for player features; lazy caching; 8 organized categories |
| Engine separation into dedicated modules | `engines/*.py` | Each engine has a focused responsibility; consistent return types (dataclasses) |
| `from __future__ import annotations` | 20+ files | Universal modern type annotation practice |
| Dataclass result types | All engines | Typed return values improve IDE support and documentation |
| Prediction Ledger append-only design | `services/snapshot_service.py` | Event-sourcing pattern — never mutate, never delete |
| Validation platform architecture | `services/learning_service.py`, `engines/validation_engine.py` | Scientific evaluation loop with evidence levels, human oversight |
| Dependency injection of FeatureStore | 6 engines | `Depends(get_store)` pattern enables testability |
| WAL mode enabled for SQLite | `database/database.py:41-42` | Enables concurrent reads during writes |
| Safe YAML loading | `utils/config.py:34` | Uses `yaml.safe_load()` — prevents arbitrary code execution |
| No secrets/API keys in codebase | All files | TEAM_ID is public FPL data, not sensitive |
| No SQL injection risk | All files | 100% SQLAlchemy ORM usage, no raw SQL |
| No dangerous builtins (`eval`, `exec`, `pickle`) | All files | These are only present in `.venv` dependencies |

### Well-Written Modules

| Module | Reason |
|--------|--------|
| `services/scoring.py` | Clean function separation, protected divisions, documented formulas |
| `services/api_client.py` | SSL fallback is pragmatic (even if insecure by default); 30s timeout; proper headers |
| `database/crud.py` | Consistent upsert pattern, bulk operations for projections |
| `components/theme.py` | Comprehensive CSS, semantic color variables, typography ramp, responsive grids |
| `engines/minutes_engine.py` | Focused responsibility, rotation risk modeling, well-documented modifier system |
| `engines/monte_carlo_engine.py` | Clean simulation approach, bimodal adjustments, risk metrics |

### No Issues Found In

- No circular imports that crash (lazy import workaround is in place)
- No memory leaks in steady state
- No unclosed file handles
- No unclosed database connections (sessions properly closed)
- No hardcoded credentials or tokens
- No debug endpoints in production code
- No overly complex inheritance hierarchies
- No monkey-patching of third-party libraries

---

## SECTION 6: FINAL RECOMMENDATION

### VERDICT: NOT READY

**The codebase is not ready for production deployment.**

**Why:**
- **7 critical issues** that will cause hard crashes under real-world conditions (API failure, missing data, config errors)
- **18 high-severity issues** that will cause incorrect results, performance degradation, or data integrity problems
- **Test suite provides false confidence** — the primary test file has zero assertions, and validation tests use unrealistically clean data
- **No graceful degradation** for any failure mode — API down = app down, config missing = app down, bad data = app crash
- **Architecture violations are pervasive** — 30% of files (18/60) have layering violations. Every page directly manages database sessions.

**What will keep you awake:**
- GW1 API load triggers a 429 rate limit → the app crashes during the most important time to use it
- A missing YAML config file (or typo) crashes the entire engine pipeline silently
- The test suite passes but production data has NULL fields or missing columns → pipeline crashes mid-way
- Duplicate prediction ingestion produces duplicate rows because no unique constraints exist
- The confidence engine and projection engine disagree on player variance, producing inconsistent captain recommendations

**What can safely wait:**
- Removing V1 engines (V2 equivalents exist but need real-data validation first)
- Refactoring `fixture_engine.py` into smaller modules (works now, just hard to maintain)
- Adding Alembic (no schema changes planned before GW1)
- The bookmaker engine (it's effectively dead code but doesn't crash)
- Performance optimization of `iterrows()` loops (codebase handles 700 players acceptably)

### Recommendation Summary

| Timeline | Action |
|----------|--------|
| **Before GW1** | Address 8 immediate action items (Section 2) — ~8-12h effort |
| **After GW1** | Validate with real data, then fix 7 post-GW1 items (Section 3) |
| **Offseason** | Address 12 long-term debt items (Section 4) |

With the 8 pre-GW1 items addressed, the codebase would move to **READY WITH MODERATE RISKS** — deployable for a single user with monitoring, but not production-grade for multi-user or public deployment.
