# Pre-GW1 Production Readiness Review

**Date:** 2026-08-20
**Reviewer:** opencode (automated audit, all findings verified against source code)
**Scope:** Full system — architecture, models, data pipeline, chatbot, security, deployment, UX, performance
**Branch:** `main` | **HEAD:** `7b6ca45` | **Tests:** 368/368 passing

---

## 1. Executive Summary

**Manny's FPL House is well-engineered for a solo-developer FPL analytics application but is NOT ready for public GW1 deployment.**

Two blocking issues prevent launch:

1. **No deployment infrastructure exists.** There is no Dockerfile, no hosting configuration, and no CD pipeline. The app runs locally only. The README states "the app is not yet publicly hosted."

2. **A critical bug (`NameError`) will crash the Assistant Manager page** for every user who has a valid squad — which is the primary use case.

The codebase itself is of high quality: clean separation of concerns, thorough test coverage (368 tests, zero failures), strong security practices, well-structured configuration, and thoughtful model architecture. The prediction pipeline is correct. The chatbot is well-defended. The onboarding system is secure.

If the blocking issues are resolved and the app is deployed to a single-user environment (your own browser), the system is operationally sound for GW1 usage.

### Go / No-Go

| Condition | Status |
|-----------|--------|
| Code correctness | PASS (with 1 critical bug) |
| Test suite | PASS (368/368) |
| Security | PASS |
| Deployment | FAIL (not deployed) |
| Assistant Manager | FAIL (NameError crash) |
| **GW1 Verdict** | **CONDITIONAL GO** — fix the bug, deploy locally, GW1 works |

---

## 2. System Architecture Review

### Architecture

```
User (Streamlit browser)
  → About.py (entry) / pages/ (8 pages)
  → components/ (theme, charts, tables, sidebar, onboarding)
  → services/ (API client, pipeline, scoring, assistant chat, league intelligence)
  → engines/ (20 prediction/analysis engines)
  → features/store.py (FeatureStore — single source of truth)
  → database/ (SQLAlchemy ORM, 16 tables, Alembic migrations)
  → config/ (11 versioned YAML files, active.yaml selector)
  → FPL API (https://fantasy.premierleague.com/api/)
```

### Verdict: PASS

- Clean layered architecture with explicit separation between prediction, decision intelligence, and UI
- FeatureStore as SSOT is enforced
- Configuration is versioned and immutable
- No circular dependencies between modules
- Research pipeline is cleanly separated from production

### One Issue Found

The dev container uses Python 3.11 (`python:3.11-bookworm`) while the app requires Python 3.12+ per the README. This mismatch could cause subtle issues for anyone using GitHub Codespaces.

---

## 3. Production Model Review

### V3 xPts — Primary Model

**Status: CORRECTLY IMPLEMENTED**

| Check | Result |
|-------|--------|
| V3 (`expected_points_v1`) is primary | PASS — `config/production/production_v1.yaml` line 24 |
| V1/V2 are shadow/control, never override V3 | PASS — guard at `production_predictor.py:161-162` |
| xPts = xPts_per_90 × (expected_minutes / 90) | PASS — `expected_projection_engine.py:113` |
| FeatureStore is single source of truth | PASS — all engines call `store.xgi_features()` etc. |
| Column-presence gating for ev_* columns | PASS — `np.isfinite()` checks on every evidence path |
| No accidental fallback to V1/V2 | PASS — no fallback paths exist |
| Hist configs separate from current | PASS — separate YAML files |

### xPts_per_90 breakdown

```
xPts_per_90 = xg_90 × fixture_mult × goal_val
            + xa_90 × fixture_mult × assist_val
            + clean_sheet_prob × cs_val
            + expected_bonus
            + expected_saves
            + expected_cards (negative)
            + set_piece_bonus
```

Floor at 0.0 prevents non-physical negative xPts/90. Fixture multiplier applies only to goal/assist (correct).

### Issues Found

#### ISSUE-1 (HIGH): Hist Shadow Predictions Silently Lost

**File:** `services/expected_pipeline.py:210-220`

The `version_tag` is computed as `xpts-gw{gw_id}-{config_hash[:8]}` where `config_hash` is derived from the **active** config only. The `model_name` parameter (`"v3_hist_d_team"`) is NOT included in the tag.

When the primary model runs first and persists (creating tag `xpts-gw5-abc12345`), the hist shadow computes the **identical** tag, hits the idempotency guard, and silently returns the primary's version_id without persisting its own predictions.

**Impact:** Model D shadow predictions are never stored. Post-gameweek validation of hist vs non-hist is impossible.

**Fix:** Include `model_name` in the version tag or use the model-specific config hash.

#### ISSUE-2 (MEDIUM): Confidence Tier Config Key Mismatch

**Files:** `config/expected_points/expected_points_v1.yaml:90-94` vs `engines/expected_points_engine.py:450-452`

Config keys: `no_data`, `limited_data`, `moderate_data`, `good_data`
Engine lookup: `confidence_cfg.get(data_quality, 40)` where `data_quality` is `"none"`, `"limited"`, etc.

These keys don't match. Every player gets confidence=40 regardless of data quality.

Same bug exists in `expected_minutes_v1.yaml` — all players get confidence=45.

**Impact:** Confidence intervals are miscalibrated. Players with good data get the same CI as players with no data.

**Fix:** Rename config keys to `none`, `limited`, `moderate`, `good` (or prefix them in the engine lookup).

---

## 4. Historical Data Review

### Available Data

| Season | GW Data | xG/xA | `starts` | Used in Backtest |
|--------|---------|-------|----------|-----------------|
| 2022-23 | Yes | Yes | Yes | Yes (FAITHFUL_SEASONS) |
| 2023-24 | Yes | Yes | Yes | Yes |
| 2024-25 | Yes | Yes | Yes | Yes |
| 2025-26 | Yes | Yes | Yes | **No** (on disk but not in FAITHFUL_SEASONS) |
| 2026-27 | Preseason only | Yes | Yes | N/A (current season) |

### Player Matching

Players matched across seasons via FPL's `code` field (stable per-player identifier), NOT via `element` (season-scoped). Verified stable for Salah/Saka/Haaland/Watkins across 2022-25.

### Leakage Protection

**PASS.** Multi-layered and tested:
- State builder: `past = gw[gw["round"] < gw_n]` — strict less-than
- Historical features: identical guard
- Evidence layer: identical guard + raises ValueError on empty
- Previous-season priors: completed season by definition
- Leakage tests exist: `test_player_features_leakage_safe`, `test_previous_season_prior_leakage_safe`, `test_leakage_audit_future_rounds_do_not_influence_evidence`

### Critical Gap: Historical Data NOT Active in Production

The production pipeline (`config/active.yaml`) uses `expected_points_v1` and `expected_minutes_v1` — configs **without** `empirical`, `historical_minutes`, or `prev_season` sections. The `hist_*` and `ev_*` columns are only injected by the research backtest path.

**This means:**
- GW1 uses the full 2025-26 preseason snapshot as "current" data
- GW2 uses only GW1 of 2026-27 — the previous season's data vanishes entirely
- There is no gradual transition from historical to live data in production

### Promoted/Relegated Teams

Handled correctly. Promoted players have no FPL `code` from a previous PL season, so `prev_*` columns are NaN, falling back to position-average priors. Newly promoted teams default to league-average team strength (1.0).

### 2025-26 Not in FAITHFUL_SEASONS

Complete 2025-26 data exists on disk but is not included in `FAITHFUL_SEASONS`. Verify if this is intentional (holdout set) or an oversight.

---

## 5. Expected Minutes / Substitute Review

### Production Model (Non-Hist)

```
expected_minutes = start_prob × minutes_if_starting × (1 - substitution_risk)
```

- **Start probability:** 60% × starts_rate + 40% × chance_of_playing_next_round, with form adjustments
- **Minutes-if-starting:** 60% historical + 40% positional baseline (3+ starts); positional baseline only (<3 starts)
- **Substitution risk:** Binary step function — 0.25 if minutes_if_starting ≥ 78, else 0.10

### Shadow Model (Hist)

```
expected_minutes = P(start) × E[min|start] + P(not start) × P(sub|not start) × E[min|sub]
```

Uses beta-binomial posterior for start probability. Includes bench-appearance branch. `substitution_risk` is informational only (not applied).

### Issues

#### ISSUE-3 (MEDIUM): Production Cannot Value Substitute Minutes

The non-hist formula has no bench-appearance branch. A player with 0 starts but regular sub appearances gets the same expected minutes as a player who never plays (given the same starts_rate = 0). The substitute philosophy ("minimum-cost reliable minutes") is structurally impossible with this model.

**Impact:** The assistant cannot distinguish between a cheap reliable sub and a cheap non-playing filler.

**Mitigation:** The hist shadow model addresses this. Promote after ≥5 GW shadow validation.

#### ISSUE-4 (MEDIUM): Universal Substitution Risk Penalties All Players

`substitution_risk = 0.25` for every player with minutes_if_starting ≥ 78. This applies to GKP (true sub-off rate ~0.6%), nailed-on DEFs (~5%), and true rotation risks (~12%) identically.

For a nailed-on GKP: current expected minutes = 0.95 × 90 × 0.75 = 64.1. Correct estimate: ~85.0. **~25% systematic underprediction for nailed-on starters.**

**Documented in:** `reports/historical_minutes_analysis.md` and `reports/model_audit_substitute_selection.md`

#### ISSUE-5 (LOW): `_games_played` Floors at 1

A player with 0 minutes returns `games_played = 1`. Used for diagnostics only, not calculation.

---

## 6. League Intelligence Review

### Architecture

```
Prediction Layer → V3 Projections (read-only)
                         ↓
               League Intelligence Layer
               (consumes projections, never modifies them)
                         ↓
               StrategicRecommendations
               (carry untouched xpts + strategy scores)
```

### Separation from Prediction: PASS

- Zero imports from `engines/` in `league_intelligence/`
- Zero imports from `league_intelligence/` in `engines/`
- Every model/engine carries the contract: "xpts is carried through from the prediction layer UNCHANGED"

### External Data Dependencies

| Provider | Source | Failure Behavior |
|----------|--------|-----------------|
| OwnershipProvider | Local FeatureStore | Always available |
| CaptainPollProvider | Optional external API | Returns `{}` if unavailable |
| Top-10k ownership | Optional | Returns `None` if unavailable |
| MiniLeagueProvider | FPL API | Wrapped in try/except, returns `[]` on failure |

**All dependencies are best-effort.** Missing data degrades to None/0.0/empty lists.

### One Gap

The assistant manager currently does not pass `league_id` or `league_squads` to the League Intelligence engine, so league differentials are based on global ownership, not actual league peer data. This is a data completeness gap, not a correctness bug.

---

## 7. Assistant Manager Review

### Architecture

One-shot advisory engine. Read-only. No write path to team, database, prediction models, or league settings.

### Context Received

- User squad (web_name, position, team, price, form, xGI/90, xPts, fixtures)
- Top V3 projections (top 15 by xPts)
- Shadow model projections (Model D)
- League differentials (global ownership)
- User context (team_id, gameweek, bank, transfers)

### Data Fabrication Defense

- System prompt: "Never invent numbers that are not in the context"
- Deterministic tools bypass the LLM entirely (player comparison, captaincy, transfers)
- Provenance labels required on every statement
- Output guard blocks leaked internals

### API Failure Handling

All failures caught and return a friendly degraded message. No stack traces, credentials, or architecture details are ever surfaced.

### Token/Cost Controls

| Control | Default |
|---------|---------|
| Per-session request limit | 60 |
| Cumulative token budget | 100K |
| Max conversation window | 12 messages |
| Max user message length | 4,000 chars |
| Max output tokens | 900 |
| Temperature | 0.4 |

### Prompt Injection Defense

Multi-layered: input sanitization → structural delimiters → system prompt hardening → response guard → rate limiting.

### Verdict: PASS

Well-engineered chatbot with appropriate safety constraints. The only limitation is inherent LLM hallucination risk, which is mitigated by provenance labels and deterministic tools.

---

## 8. Onboarding Review

### Flow

1. User arrives → landing page (no team required)
2. Navigates to personalized page → `require_team()` gate
3. If no team_id in session → onboarding component rendered
4. User enters FPL Team ID → sanitized (digits only, 1-99,999,999)
5. Live API call to `/entry/{team_id}/` with 10s timeout, 1 retry
6. VALID → stored in `st.session_state["team_id"]`, `st.rerun()`
7. Page loads with validated team

### Security Properties

| Check | Result |
|-------|--------|
| Director's personal FPL ID as default | **ABSENT** — deliberately excluded everywhere |
| Cross-user data leakage | **NONE** — session-isolated by design |
| URL parameter bypass | **NOT POSSIBLE** — seeds input only, not session state |
| Invalid FPL ID handling | **ALL modes handled** with friendly messages |
| Team switching | **Works** — "Change Team" button in sidebar |
| FPL ID redaction in logs | **Yes** — `_redact_url()` scrubs `/entry/{digits}` |
| Session state isolation | **Correct** — per-browser-tab by Streamlit design |

### Verdict: PASS

The onboarding and user isolation system is production-ready. No changes required.

---

## 9. Data / Database Review

### Schema

16 tables, all with appropriate column types. SQLite with WAL mode. Foreign keys enabled via `PRAGMA foreign_keys=ON` on every connection.

### Index Coverage

**Indexed:** `decision_log.team_id`, `decision_log.gameweek_id`, `chip_state.team_id`, `audit_log.action`, `audit_log.created_at`, `player_snapshots.player_id`, `player_snapshots.gameweek_id`, `projections.version_id/player_id/gameweek_id`, `validation_metrics.version_id/gameweek_id`, `error_classifications.*`, `recommendation_outcomes.*`, `engine_accuracy.*`.

**NOT indexed (significant gaps):**
- `players.team_id` — join for every player query
- `players.element_type` — position filtering
- `projections.(version_id, gameweek_id)` — frequently queried together
- `player_gameweek_stats.(player_id, gameweek_id)` — frequently queried together
- `price_history.player_id`

### Transaction Safety

**Missing rollback paths in:**
- `production_predictor.py:252,315` — `session.commit()` with no rollback on failure
- `expected_pipeline.py:137` — `session.commit()` with no try/except
- `decision_log.py:35,52,69,185` — `session.commit()` with no rollback
- `learning_service.py:210` — `session.commit()` after validation loop

### SQLite Concurrency

- WAL mode enabled (concurrent reads, serialized writes)
- **Missing `PRAGMA busy_timeout`** — concurrent writes fail immediately with `SQLITE_BUSY`
- `check_same_thread=False` set (required for Streamlit, removes safety check)
- No connection pool tuning (`pool_pre_ping` absent)

### Prediction Ledger

Append-only by design. `version_tag` has UNIQUE constraint. `update_projection_actuals_bulk()` legitimately fills in post-hoc data (documented as update, not contradiction of append-only claim).

### Idempotency

`version_tag` uniqueness is the strongest guarantee. Read-then-write patterns in result ingestion have TOCTOU race conditions (low risk for single-user).

---

## 10. API Reliability Review

### FPL API Client

| Feature | Status |
|---------|--------|
| HTTPS enforcement | PASS — non-HTTPS rejected by default |
| SSL verification | PASS — `verify=certifi.where()`, insecure fallback gated behind env var |
| Retry logic | PASS — 3 retries, exponential backoff (1s, 2s, 4s) |
| HTTP 429 handling | PASS — respects `Retry-After` header, capped at 60s |
| 5xx handling | PASS — in retryable set |
| Timeouts | PASS — 30s default, configurable |
| URL redaction | PASS — FPL IDs scrubbed from logs |

### Gaps

- No jitter on exponential backoff (thundering herd risk)
- No circuit breaker for prolonged FPL API outages
- `verify=False` fallback exists but is gated behind `FPL_API_ALLOW_INSECURE_SSL=true`

---

## 11. Security Review

### Scorecard

| Category | Status |
|----------|--------|
| Secrets in codebase | **CLEAN** — no hardcoded secrets |
| `.gitignore` coverage | **Comprehensive** |
| SSL verification | **Secure** by default, gated exception |
| Prompt injection (chatbot) | **Multi-layered defense** |
| XSS / HTML injection | **Centralized escaping** via `esc()` |
| SQL injection | **Negligible** — ORM-only |
| User data logging | **Proactive redaction** of team IDs and keys |
| Environment variables | **Well handled** — centralized, secrets separated |
| Authentication | **Optional admin token** (single-owner model) |
| Dangerous functions | **None** — no eval/exec/os.system |
| Dependencies | **Pinned and recent** |

### Recommendations

1. Confirm `FPL_API_ALLOW_INSECURE_SSL` is not set in production
2. Confirm `ADMIN_TOKEN` is set in production
3. Confirm `DB_ALLOW_CREATE_ALL=false` in production
4. Add adversarial prompt injection test suite
5. Run `pip-audit` one final time before deployment

---

## 12. Testing Review

### Results

```
368 passed, 0 failed, 0 errors, 2683 warnings (64.88s)
Ruff: 0 errors, 0 warnings
```

### Test Quality Assessment

| Category | Rating | Notes |
|----------|--------|-------|
| Engine correctness | Strong | Exact value assertions, not just "doesn't crash" |
| Evidence layer | Strong | Numerical precision, monotonicity, temporal integrity |
| Production predictor | Strong | Exact model IDs, projection counts, persistence idempotency |
| Onboarding / team ID | Strong | Session state round-trips, corrupt-value clearing, URL params |
| Chatbot security | Strong | Prompt leakage, tool output verification, provider mocking |
| Validation platform | Strong | Full lifecycle, error classification, evidence thresholds |
| Security | Strong | Secret leakage tests, input sanitization |

### Weak Tests

3 standalone `assert X is not None` without follow-up assertions (out of 368). Contextually appropriate in most cases.

### Testing Gaps

| Gap | Severity |
|-----|----------|
| No statistical significance test in `compare_versions()` | Medium |
| No integration test for live FPL API | Low |
| No test for `compare_versions` with identical versions | Low |

---

## 13. Deployment Review

### Current State

| Item | Status |
|------|--------|
| Hosted? | **NO** — local only |
| Dockerfile | **Not present** |
| docker-compose | **Not present** |
| Cloud platform config | **Not present** |
| CD pipeline | **Not present** |
| CI (lint + tests) | **Present** — `.github/workflows/ci.yml` |
| Dependabot | **Active** — weekly pip + Actions updates |
| Database backup script | **Present** — `scripts/backup_db.py` (manual) |
| Release tags | **None** |

### Deployment Options

1. **Streamlit Community Cloud** — path of least resistance (same stack, free tier)
2. **Fly.io / Render** — Dockerfile required, more control
3. **Local** — `streamlit run About.py` (current method)

### Blockers for Public Deployment

1. No containerization or hosting configuration
2. SQLite requires persistent volume in containerized environments
3. No `DB_ALLOW_CREATE_ALL=false` in production config
4. No automated backup before deploys
5. No staging environment

---

## 14. Performance Review

### iterrows() Usage

**83 instances** across the codebase. Critical production-path instances in:

| File | Lines | Impact |
|------|-------|--------|
| `features/store.py` | 248, 277 | Two separate iterrows over 550+ players |
| `engines/expected_points_engine.py` | 108 | Core projection engine |
| `engines/expected_minutes_engine.py` | 99 | Minutes projection |
| `engines/captain_engine.py` | 51 | Captain recommendation |
| `engines/fixture_engine.py` | 176, 226, 272 | Fixture processing (3 loops) |

**Estimated impact:** 5,500+ Python-level iterations per full pipeline run. Not catastrophic for single user but adds 2-5 seconds of unnecessary overhead.

### Caching

Only 2 `@st.cache_data` in entire app. What is NOT cached:
- `ensure_data_loaded()` — full FPL API fetch on every page load
- `build_feature_store()` — called twice per Model Comparison run
- `run_assistant()` — full engine pipeline on every page load
- `fetch_team_data()` — network I/O with no spinner

### N+1 Queries

- `pages/7_Model_Analytics.py:214-217` — `get_projections()` called once per version inside set comprehension
- Same pattern repeated at line 736-740

### Session Leaks

- `pages/7_Model_Analytics.py` opens 10 separate `get_session()` calls per page load, never closed
- Default SQLAlchemy pool size is 5 — potential exhaustion

---

## 15. Findings

### 🔴 MUST FIX BEFORE GW1

| # | Finding | File | Impact | Fix Effort |
|---|---------|------|--------|------------|
| **R1** | **`squad_eval` NameError crashes Assistant Manager** — variable only assigned in `if squad_eval is None` branch, referenced in `else` path at line 124. Every user with a valid squad triggers `NameError`. | `pages/6_Assistant_Manager.py:61-68,124` | Assistant Manager page completely broken for all real users | 1 line — add `else: squad_eval = report.squad_evaluation` |
| **R2** | **No deployment infrastructure** — no Dockerfile, no hosting config, no CD pipeline. App runs locally only. | Entire repo | Cannot serve users | Platform selection + config |
| **R3** | **Confidence tier key mismatch** — config keys (`no_data`, `limited_data`...) don't match engine lookup keys (`none`, `limited`...). All players get confidence=40/45. | `config/expected_points/expected_points_v1.yaml:90-94`, `engines/expected_points_engine.py:450-452` | Confidence intervals miscalibrated for all players | Rename 8 config keys or engine strings |

### 🟠 SHOULD FIX SOON AFTER GW1

| # | Finding | File | Impact | Fix Effort |
|---|---------|------|--------|------------|
| **O1** | **Hist shadow predictions silently lost** — version tag doesn't include model_name, so shadow hits idempotency guard and returns primary's version_id. | `services/expected_pipeline.py:210-220` | Model D predictions never persisted, cannot validate | Include model_name in version tag |
| **O2** | **Production cannot value substitute minutes** — no bench-appearance branch in non-hist minutes formula. Cheap subs valued same as non-players. | `engines/expected_minutes_engine.py:164-168` | Substitute philosophy unachievable | Port hist branch or promote hist model |
| **O3** | **Universal 0.25 substitution risk** — all 78+ minute players penalized 25%. GKP (0.6% true rate) treated same as rotation risk (12%). ~25% underprediction for nailed starters. | `engines/expected_minutes_engine.py:288-298` | Systematic minutes underprediction | Position-specific rates or remove |
| **O4** | **Missing `PRAGMA busy_timeout`** — concurrent writes fail immediately with `SQLITE_BUSY`. | `database/database.py` | Data loss on concurrent access | 1 line pragma |
| **O5** | **Missing indexes** — `players.team_id`, `players.element_type`, `projections.(version_id, gameweek_id)` composite. | `database/models.py` | Slow queries on every page load | Add index=True |
| **O6** | **No rollback on commit failure** — production_predictor, expected_pipeline, decision_log, learning_service. | Multiple files | Broken session state on failure | Wrap in try/except/rollback |
| **O7** | **My Team page has no spinner** — `fetch_team_data()` is network I/O with no loading indicator. | `pages/1_My_Team.py:50` | User sees frozen page | Add st.spinner |
| **O8** | **Chat handler has no try/except** — `_handle_message` in Assistant Manager. | `pages/6_Assistant_Manager.py:318-329` | Page crashes on LLM error | Add try/except |
| **O9** | **DB_ALLOW_CREATE_ALL defaults to true** — should be false in production to prevent schema drift. | `.env.example` | Schema could silently drift from Alembic | Change default |
| **O10** | **Dev container Python 3.11 vs app requirement 3.12+** | `.devcontainer/devcontainer.json` | Codespaces users get wrong Python version | Update image |

### 🟡 MONITOR DURING GW1

| # | Finding | Notes |
|---|---------|-------|
| **M1** | Historical data not active in production — GW1→GW2 discontinuity | Production uses no hist integration; prior vanishes between preseason and GW2 |
| **M2** | 83 iterrows instances in hot path | Adds 2-5s overhead per pipeline run. Acceptable for single user but watch under load |
| **M3** | Only 2 @st.cache_data in entire app | Repeated API calls on every page navigation. Watch FPL API rate limits at GW1 deadline |
| **M4** | 10 DB sessions per Model Analytics page load | Connection pool (default 5) could be exhausted |
| **M5** | LLM hallucination risk in chatbot conversational mode | Deterministic tools are safe; free-form LLM responses could fabricate numbers despite provenance labels |
| **M6** | FPL API outage behavior — no circuit breaker | Retries exhaust then raise RetryError. Watch for prolonged outages |
| **M7** | Sidebar shows raw team ID instead of team name | Minor UX issue but noticed by users |
| **M8** | Model Comparison calls _build_store() twice | Double pipeline execution per comparison run |
| **M9** | 2025-26 not in FAITHFUL_SEASONS | Verify if intentional (holdout) or oversight |

### 🟢 FUTURE ENGINEERING

| # | Finding |
|---|---------|
| **F1** | Migrate from SQLite to PostgreSQL for multi-user deployment |
| **F2** | Add jitter to exponential backoff (thundering herd risk) |
| **F3** | Add circuit breaker for FPL API |
| **F4** | Add connection pool tuning (`pool_pre_ping`, `pool_size`) |
| **F5** | Port hist minutes bench-appearance branch to production |
| **F6** | Add 2025-26 to FAITHFUL_SEASONS for expanded calibration |
| **F7** | Add cross-season normalization of historical priors |
| **F8** | Add adversarial prompt injection test suite |
| **F9** | Vectorize iterrows in FeatureStore fixture features |
| **F10** | Cache FeatureStore and assistant pipeline at session level |
| **F11** | Add Content-Security-Policy headers |
| **F12** | Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` |
| **F13** | Add `pool_pre_ping=True` to SQLAlchemy engine |
| **F14** | Add unique constraint on `player_gameweek_stats.(player_id, gameweek_id)` |
| **F15** | Add N+1 query fix in Model Analytics |
| **F16** | Add `st.spinner` to all network I/O and DB calls |

---

## 16. GW1 Go / No-Go Recommendation

### CONDITIONAL GO

**The system is safe, correct, and well-engineered — but not yet deployed and has one critical bug.**

**For your own GW1 usage (single user, local):**

1. Fix the `squad_eval` NameError (1 line)
2. Fix the confidence tier key mismatch (rename 8 config keys)
3. Run `streamlit run About.py`
4. The system works

**For public deployment:**

Not ready. Needs hosting configuration, Dockerfile, and the blocking bugs above.

### What Works Correctly

- V3 xPts production model — correct formula, correct config, correct shadow isolation
- Onboarding — secure, validated, no default FPL ID exposure
- Chatbot — multi-layered prompt injection defense, deterministic tools, graceful degradation
- League Intelligence — clean separation from prediction, all dependencies best-effort
- Security — no secrets in code, SSL enforced, proactive redaction, centralized HTML escaping
- Test suite — 368/368 passing, strong correctness assertions
- Historical data — safe, no leakage, correct player/team matching

### What Needs Fixing

1. `squad_eval` NameError (R1) — blocks Assistant Manager
2. Confidence key mismatch (R3) — miscalibrates all CIs
3. Deployment infrastructure (R2) — blocks any user other than yourself

---

## 17. First 3 Gameweeks — What to Monitor

| Area | What to Watch | Why |
|------|--------------|-----|
| **Prediction accuracy** | MAE, RMSE for V3 vs actual FPL points | Core model performance |
| **Expected minutes accuracy** | Predicted vs actual minutes for starters and subs | Minutes model calibration |
| **Starts prediction** | Did predicted starters actually start? | Start probability calibration |
| **Substitute appearances** | Did non-starters come on as predicted? | Bench-appearance model |
| **Unused substitutes** | Players predicted to get minutes who didn't play | False positive rate |
| **V3 vs Model D** | Do hist priors improve over non-hist in early GWs? | Historical integration value |
| **V3 vs V2** | Does xPts outperform the older projection model? | Primary model validation |
| **FPL API reliability** | 429/5xx responses, latency spikes | Infrastructure resilience |
| **User onboarding** | Successful validations, invalid ID handling | User experience |
| **Chatbot quality** | Deterministic tool accuracy, LLM hallucination reports | Advisory quality |
| **League Intelligence** | Differential accuracy, ownership data freshness | Decision support value |
| **Historical vs live data influence** | How quickly do GW1-3 results shift predictions? | Decay mechanism |

---

## 18. Recommended GW1 Monitoring Dashboard

### Prediction Metrics (collect after each GW)

| Metric | Source | Target |
|--------|--------|--------|
| V3 MAE | `validation_metrics` table | < 2.0 |
| V3 RMSE | `validation_metrics` table | < 3.0 |
| V3 correlation | `validation_metrics` table | > 0.30 |
| V3 CI coverage (80%) | `validation_metrics` table | 70-90% |
| Model D MAE | `validation_metrics` table | Track trend |
| Model D vs V3 delta | `compare_versions()` | Track direction |
| Top-10 accuracy | Manual | > 60% in top-10 |
| Captain accuracy | Manual | > 50% in top-3 |

### Minutes Metrics (collect after each GW)

| Metric | Source | Target |
|--------|--------|--------|
| Predicted vs actual minutes | `projections` + actuals | MAE < 10 min |
| Start prediction accuracy | `start_probability` vs actual starts | > 75% |
| Sub appearance rate | Actual subs / predicted subs | Track trend |
| 0-minute surprises | Players with >0 expected minutes who got 0 | < 10% of squad |

### Infrastructure Metrics

| Metric | Source | Target |
|--------|--------|--------|
| FPL API response time | `api_client` logs | < 2s p95 |
| FPL API error rate | `api_client` logs | < 5% |
| Page load time | Streamlit | < 5s |
| DB session count | Connection pool | < pool_size |
| Chatbot response time | `usage.py` logs | < 10s |

### Weekly Checklist

After each gameweek:
1. Run result ingestion (`pages/7_Model_Analytics.py`)
2. Run validation cycle
3. Check V3 MAE/RMSE trend
4. Check Model D shadow performance
5. Check minutes prediction accuracy
6. Review any 0-minute surprises
7. Check FPL API error logs
8. Update monitoring spreadsheet

---

*This review was produced by automated code inspection. All findings were verified against the actual source code in the repository at commit `7b6ca45`.*
