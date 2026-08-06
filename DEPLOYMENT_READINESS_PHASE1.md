# PHASE 1 — DEPLOYMENT READINESS REPORT — Manny's FPL House

**Prepared for:** Senior Engineering Manager
**Prepared by:** Open Code Development Team
**Date:** 2026-08-02
**Scope:** Infrastructure preparation only. No prediction logic, weighting, validation, or learning-system behaviour was changed.
**Method:** Read-only audit of source, config, and runtime behaviour. No production deployment performed.

---

## 1. EXECUTIVE SUMMARY

### Deployment Readiness Score: **45 / 100** (NOT READY — Foundation is Sound, Wrapping Is Not)

The core architecture is genuinely strong for a personal project: a layered design (database → services → engines → Streamlit pages), a versioned YAML config system, a config hash for experiment tracking, and an append-only prediction ledger. The gap between "runs on Manny's Mac" and "safe to host publicly" is wide, and it is almost entirely **infrastructure**, not application logic.

### Major Strengths

| # | Strength | Evidence |
|---|----------|----------|
| S1 | Versioned, single-source config loader | `utils/config.py` + `config/active.yaml` + `config/weights/weights_v3.yaml` |
| S2 | Configuration already hash-tracked for experiments | `get_config_hash()` / `PredictionVersion.config_hash` |
| S3 | API client already has retry + backoff + rate-limit handling | `services/api_client.py:36-99` |
| S4 | Database URL already env-var aware | `database/database.py:15` |
| S5 | `.gitignore` is comprehensive and env-aware | `.gitignore` covers `.env`, `*.db`, `secrets.toml`, local configs |
| S6 | All secrets already absent from source | no API keys/tokens found in any `.py` file |
| S7 | Testing exists and passes (17 tests) | `pytest` → 17 passed |
| S8 | Requirements are explicitly declared | `requirements.txt` |

### Major Risks (see §7 for full detail)

| # | Risk | Severity |
|---|------|----------|
| R1 | **No version control at all** — project is not a git repo | CRITICAL |
| R2 | **No database migration system** — `create_all()` on every start | CRITICAL |
| R3 | **Single-user assumptions baked in** — `TEAM_ID=<developer's team ID>` hardcoded, staleness tracked in-process | HIGH |
| R4 | **`.env` support is declared but never wired up** — `python-dotenv` installed, `load_dotenv()` never called | HIGH |
| R5 | **SSL verification silently disabled on failure** (`verify=False`) with warnings suppressed | HIGH |
| R6 | **Logging is not configured** — Python logs are dropped, only Streamlit's own UI errors surface | HIGH |
| R7 | **Loose dependency pins** (`>=`) — no reproducible installs | MEDIUM |
| R8 | **SQLite file persistence** — unsuitable for multi-user concurrent writes | MEDIUM |

### Estimated Effort Remaining

| Area | Estimate |
|------|----------|
| Config externalization (Task 2) | 0.5 – 1 day |
| Dependency hardening (Task 3) | 0.5 day |
| Deployment documentation (Task 4) | 1 day |
| Production-readiness fixes (Task 5) | 2 – 3 days |
| Repository preparation (Task 6) | 0.5 – 1 day |
| **Total (Phase 1 completion)** | **4.5 – 6.5 engineering days** |

---

## 2. CURRENT STATE ASSESSMENT

### 2.1 What Is Deployment-Ready Already

1. **Dependency declaration exists.** `requirements.txt` lists all 11 direct packages.
2. **Config system is versioned and centralized.** `utils/config.py` reads `config/active.yaml` to resolve categories to versioned YAML files. Switching weights is a one-line edit.
3. **Runtime is self-bootstrapping.** `utils/helpers.py:ensure_data_loaded()` initialises the DB and loads FPL data on first run.
4. **Streamlit is configured headless.** `.streamlit/config.toml` sets `headless = true` and usage stats off.
5. **No secrets in source.** Confirmed by scan.
6. **Basic tests exist and pass.** 17 tests across 3 files.

### 2.2 What Is NOT Deployment-Ready

1. **No version control.** There is no `.git` directory. The repository cannot be shared, reviewed, or rolled back.
2. **No migration system.** `Base.metadata.create_all()` (`database/database.py:34`) creates tables on startup. Any schema evolution requires manual intervention.
3. **Single-user identity is hardcoded.** `TEAM_ID: int = <developer's team ID>` (`utils/constants.py:19`) is the personal FPL team used by every page. A public deployment would expose one manager's private data and cannot be personalised.
4. **Environment files are not actually loaded.** `python-dotenv` is installed and `.env.example` exists, but `load_dotenv()` is never called. `DATABASE_URL` works only if exported in the shell environment.
5. **Logging is unconfigured.** No `logging.basicConfig`/`dictConfig` anywhere in application code. `logger.warning/info` calls in `api_client.py`, `data_loader.py`, etc. have no handlers → silently discarded.
6. **Data freshness is an in-process singleton.** `_staleness_tracker` (`services/data_loader.py:173`) resets on every restart, so a fresh boot always considers data stale and triggers a full FPL API re-fetch on first page load.
7. **README and scoring-weights docs are stale.** README describes "Placeholder" fixture/set-piece status and lists only 2 pages; the weights table no longer reflects the active V3 config.
8. **No license.** Cannot be published without deciding licensing.

### 2.3 What Is Missing Entirely

| Missing Item | Why It Matters |
|---|---|
| Git repository + remote | No history, no collaboration, no backup |
| Deployment documentation (install/configure/init/start/upgrade/recover) | Task 4 deliverable — absent |
| Production logging config | Debugging incidents is impossible |
| Database backup/migration strategy | Data loss risk on schema change |
| Health/startup checks | No way to verify the app came up correctly |
| Reproducible dependency lock | `>=` ranges allow drift |
| License | Legal blocker for public sharing |
| CI pipeline (even trivial) | No automated gate |

---

## 3. REQUIRED CHANGES

Prioritised. All estimates are engineering effort for a single engineer. **None of these alter prediction logic, weights, validation, or the learning system.**

### CRITICAL (block deployment)

| ID | Change | Effort | Notes |
|----|--------|--------|-------|
| C1 | Initialise git repository, add remote, first commit | 0.5 hr | Project currently has no `.git` |
| C2 | Add a database migration path (Alembic) OR an explicit `init_db.py` CLI + documented manual migration procedure | 1 – 2 days | `create_all()` is fine for greenfield; needs versioned migrations before hosting |
| C3 | Externalise `TEAM_ID` to environment/config with a safe default | 0.5 hr | Currently `utils/constants.py:19` |
| C4 | Wire up `.env` loading (call `load_dotenv()` at app start) | 0.5 hr | `python-dotenv` already installed, unused |
| C5 | Remove the `verify=False` SSL fallback or make it opt-in via config with a loud warning | 0.5 day | `services/api_client.py:61-67` |

### HIGH

| ID | Change | Effort | Notes |
|----|--------|--------|-------|
| H1 | Configure logging (level, format, file + console) via config/env | 0.5 day | No handler exists today |
| H2 | Make FPL API base URL, user agent, timeouts, retries configurable | 0.5 day | `utils/constants.py:23-24`, `api_client.py:25-27` |
| H3 | Make staleness threshold configurable and persist last-refresh in DB instead of memory | 0.5 day | `data_loader.py:63,173` |
| H4 | Pin dependencies to exact versions (`==`) and add `requirements-dev.txt` | 0.5 day | See §6 |
| H5 | Add boot-time health check / friendly error when DB or API is unavailable | 0.5 day | Improves startup reliability |
| H6 | Add a license file (decision required) | 0.25 hr | Legal prerequisite for public repo |

### MEDIUM

| ID | Change | Effort | Notes |
|----|--------|--------|-------|
| M1 | Update README (current pages, active weights, config instructions) | 0.5 day | Currently misleading |
| M2 | Document config cache TTL / add hot-reload note in docs (do not silently reload) | 0.25 day | `utils/config.py:22` caches forever in-process |
| M3 | Add tests for `compute_value_score` + `WEIGHTS` sum invariant | 0.5 day | Weights changed to V3 with no scoring test |
| M4 | Dockerfile + `docker-compose.yml` (optional but recommended) | 1 day | Simplest path to hosting |
| M5 | Add `data/` persistence note and volume guidance | 0.25 hr | SQLite file must survive restarts |
| M6 | Replace per-page `get_session()` boilerplate with a context helper | 0.5 day | Consistency, not a blocker |

### LOW

| ID | Change | Effort | Notes |
|----|--------|--------|-------|
| L1 | Centralise the repeated `_radar_colors` / `_colors` lists into `components/theme.py` | 0.25 hr | Small cleanup |
| L2 | Add `py.typed` / package metadata if moving to `pyproject.toml` | 0.5 day | Optional |
| L3 | Add a `Makefile` or documented command script for common ops | 0.5 hr | Nice-to-have |
| L4 | Remove `test_v2_pipeline.py`'s print-based "PASSED" pattern in favour of assertions | 0.5 day | Test quality, not deployment |

---

## 4. DOCUMENTATION PRODUCED

| Document | Location | Status |
|----------|----------|--------|
| This deployment readiness report | `DEPLOYMENT_READINESS_PHASE1.md` | ✅ Produced |
| Deployment guide (install / configure / init DB / start / update deps / config system / upgrade / recover) | `docs/DEPLOYMENT.md` | **TODO — Task 4** |
| Configuration reference | `docs/CONFIGURATION.md` | **TODO — Task 4** |
| Developer / contributor guide | `docs/DEVELOPMENT.md` | **TODO — Task 6** |

*The engineering instruction was to complete the audit and provide the report before code/doc changes. The three documents above are scoped into Phase 1 completion and should be created next (estimated 1 day).*

---

## 5. CONFIGURATION CHANGES

Current configuration lives in two places: `utils/constants.py` (hardcoded) and `config/*.yaml` (already externalised). The audit recommends externalising the constants listed below. Nothing in this list touches prediction/weights/validation.

### Values Recommended for Externalisation

| Current Location | Value | Recommendation | Why |
|---|---|---|---|
| `utils/constants.py:19` | `TEAM_ID = <developer's team ID>` | Move to env var `FPL_TEAM_ID` with fallback to current default | Personal identifier; must not be public/baked-in; enables per-user instances later |
| `utils/constants.py:23` | `FPL_API_BASE_URL` | Env var `FPL_API_BASE_URL` | Allows testing against a stub/mirror; no code change required to redirect |
| `utils/constants.py:24` | `FPL_USER_AGENT` | Env var `FPL_USER_AGENT` | API etiquette; identifiable source |
| `services/api_client.py:25-27` | `_TIMEOUT=30`, `_MAX_RETRIES=3`, `_BACKOFF_BASE=1.0` | Config block `api.timeout/retries/backoff` | Host environments may need different network tolerances |
| `services/data_loader.py:63` | `STALENESS_THRESHOLD_SECONDS = 3600` | Config/env `DATA_STALENESS_SECONDS` | Deployment freshness policy |
| `database/database.py:15` | `DATABASE_URL` | Already env-aware ✅; add `load_dotenv()` | `.env` support is currently dead code |
| `.streamlit/config.toml` | port/headless/theme | Move port + server settings to env (`STREAMLIT_SERVER_PORT`) for container use | Static config hard to override in containers |
| *(missing)* | Logging level / format | Add `logging.level`, `logging.file` config | No logging config exists today |
| *(missing)* | SSL verification fallback | Add `api.allow_insecure_ssl=false` default | Security control, currently silent |
| *(missing)* | Config reload | Document `invalidate_cache()`; consider TTL | `utils/config.py:22` caches forever |

### Preferred Hierarchy (as specified)

```
Environment Variables
        ↓
config/*.yaml  (versioned, active.yaml selects)
        ↓
Safe Defaults (utils/constants.py fallbacks)
```

The existing `utils/config.py` already implements the bottom two layers. Only the top layer (env → constants) needs wiring.

---

## 6. DEPENDENCY REPORT

Python 3.12.13 (installed via uv for this environment). No system libraries beyond a Python interpreter are required — all dependencies are pure-Python wheels. No ports beyond Streamlit's 8501 (configurable).

### Production Dependencies

| Package | Installed | Required | Purpose |
|---|---|---|---|
| streamlit | 1.60.0 | ✅ | Web UI framework — the application itself |
| pandas | 3.0.5 | ✅ | DataFrame manipulation in all engines/services |
| numpy | 2.5.1 | ✅ | Numerical ops (`services/scoring.py` imports it directly) |
| plotly | 6.9.0 | ✅ | Charts (radar, bar, heatmap, scatter) |
| sqlalchemy | 2.0.51 | ✅ | ORM + SQLite access |
| requests | 2.34.2 | ✅ | HTTP client for FPL API |
| certifi | 2026.7.22 | ✅ | CA bundle for SSL verification |
| pyyaml | 6.0.3 | ✅ | Parsing `config/*.yaml` |
| python-dotenv | 1.2.2 | ⚠️ *declared but unused* | Should load `.env`; not yet wired |

### Development-Only Dependencies

| Package | Installed | Purpose |
|---|---|---|
| ruff | 0.16.1 | Linter/formatter |
| pytest | 9.1.1 | Test runner |

### Issues

1. **Loose pins.** `requirements.txt` uses `>=` for all entries. Two engineers installing on different days can get different environments (pandas 3.0 / numpy 2.5 are recent major releases — behaviour could differ from the pins' original intent).
2. **`ruff` and `pytest` are runtime-listed but dev-only.** They ship in any production install.
3. **`python-dotenv` is installed but inert** — either wire it up or remove it.
4. **Transitive deps are unpinned entirely** (altair, anyio, pyarrow, etc. — 49 total packages installed).

### Recommended `requirements.txt` Split

| File | Contents |
|---|---|
| `requirements.txt` (prod) | streamlit, pandas, numpy, plotly, sqlalchemy, requests, certifi, pyyaml, python-dotenv — all pinned `==` |
| `requirements-dev.txt` | ruff, pytest, `-r requirements.txt` — pinned `==` |

Alternative: a `pyproject.toml` with `[project]` + `[project.optional-dependencies].dev` would be cleaner, but a two-file `requirements` split is the lower-risk change and matches the existing layout.

---

## 7. DEPLOYMENT RISKS

| # | Risk | Severity | Detail |
|---|------|----------|--------|
| 1 | **Database persistence (SQLite file)** | HIGH | `data/moneyball.db` is a local file. Any container/VM restart without a persistent volume loses all data. SQLite is single-writer — unsafe for concurrent multi-user traffic. |
| 2 | **Boot-time API stampede** | HIGH | `_staleness_tracker` is in-memory. Every restart marks data stale → first page load calls the FPL API (`bootstrap-static` ~1.5 MB + fixtures). Multiple users hitting a fresh boot = parallel API bursts. |
| 3 | **FPL API rate limiting** | MEDIUM | `fetch_all_picks()` makes up to 38 sequential calls (`services/team_service.py:184-191`). Client has 429 handling, but a public instance amplifies call volume. |
| 4 | **SSL MITM exposure** | HIGH | `api_client.py:61-67` retries with `verify=False` on SSL error and `InsecureRequestWarning` is globally suppressed (`api_client.py:20`). No alert to the operator. |
| 5 | **Logging black hole** | HIGH | No logging config → production incidents are invisible. |
| 6 | **No migrations** | HIGH | Schema change on a populated DB = manual work or data loss. |
| 7 | **No version control** | CRITICAL | Nothing to deploy from, no rollback, no audit trail. |
| 8 | **Single-user hardcoding** | MEDIUM | Public instance shows Manny's personal team/history. Must be replaced before public launch. |
| 9 | **Config cache never expires** | LOW | Editing YAML mid-process requires restart (`utils/config.py:22`). |
| 10 | **External CDN dependency** | LOW | Theme loads Google Fonts (`components/theme.py:84`). Offline/air-gapped hosting breaks styling. |
| 11 | **Resource usage** | LOW | 700-player pipeline with `iterrows()` loops (noted in prior audit) is fine for one user; monitor under load. |
| 12 | **`chance_of_playing` defaults** | LOW | Missing fixture data silently falls back to flat 3.0 / 50.0 (noted in `LOW_ISSUES_SENIOR_MANAGER.md`) — produces plausible-but-fake projections. Not a Phase 1 blocker. |

---

## 8. RECOMMENDED NEXT PHASE (Phase 2)

Recommendation only — no work started.

Phase 2 should be **"Deployment Foundation Hardening"** and should execute, in order:

1. **Establish version control** (C1) — init git, first commit, choose host (GitHub/GitLab).
2. **Externalise configuration** per §5 (C3–C5, H1–H3) — the highest-value, lowest-risk change set.
3. **Introduce Alembic migrations** (C2) with a baseline migration capturing the current schema.
4. **Pin dependencies and split dev/prod requirements** (H4, §6).
5. **Write the three documentation deliverables** from §4 (Deployment / Configuration / Development guides).
6. **Add containerisation** (M4) — a Dockerfile + compose file providing a persistent volume for `data/`.
7. **Add a lightweight CI pipeline** (lint + pytest) so future phases are gated.

Phase 2's explicit non-goals (defer to later phases): authentication, user accounts, payment, domain purchase, real hosting, and any prediction/validation/learning-system changes.

---

## 9. SUCCESS CRITERIA CHECK

| Criterion | Status |
|---|---|
| Application remains functionally identical | ✅ No code changed |
| Prediction behaviour unchanged | ✅ Untouched |
| Validation behaviour unchanged | ✅ Untouched |
| No GW1 functionality affected | ✅ Untouched |
| Deployment requirements fully documented | ⚠️ This report + 3 docs to write (Task 4) |
| Configuration cleaner and easier to manage | ⚠️ Recommended in §5, not yet applied |
| Another engineer can deploy using documentation alone | ⚠️ Not yet — docs are Task 4 |
