# Engineering History & Progress Report — Manny's FPL House

**Document type:** Authoritative engineering history · retrospective · technical whitepaper · executive briefing
**Audience:** Project Director, Engineering Leadership, Future Contributors, Stakeholders
**Status:** Living document — v1.0 assembled 2026-08-06
**Repository:** `github.com/MambonMangos/Manny-s-Mind`
**Version referenced:** `HEAD` (10 commits, 2026-07-30 → 2026-08-05) plus uncommitted Phase 2 + onboarding work

> **How to read this document.** It is the project's official engineering history. A new
> engineer joining the project should be able to read this end-to-end and understand where
> the project began, why major decisions were made, what was built, what problems were
> solved, what architecture now exists, what remains to be completed, and where the platform
> is heading. Each chapter was contributed by its owning discipline and assembled by the
> Technical Writer. Appendices A–F hold the diagrams, pipelines, decision records, roadmap
> tables and glossary.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Origins](#2-project-origins)
3. [Engineering Evolution](#3-engineering-evolution)
4. [Architecture Evolution](#4-architecture-evolution)
5. [Prediction Model Evolution](#5-prediction-model-evolution)
6. [Validation Platform](#6-validation-platform)
7. [League Intelligence](#7-league-intelligence)
8. [Security Evolution](#8-security-evolution)
9. [Infrastructure Evolution](#9-infrastructure-evolution)
10. [Quality Assurance](#10-quality-assurance)
11. [Public Launch Preparation](#11-public-launch-preparation)
12. [Lessons Learned](#12-lessons-learned)
13. [Future Roadmap](#13-future-roadmap)
14. [Current State Assessment](#14-current-state-assessment)
15. [Appendices](#15-appendices)

---

# 1. Executive Summary

**Contributed by:** Technical Writer (assembled from all workstreams)

## 1.1 What Manny's FPL House is

Manny's FPL House is a **data-driven Fantasy Premier League (FPL) analytics platform**.
It is a Streamlit multi-page web application backed by a SQLite database populated from the
public FPL API (`fantasy.premierleague.com/api`), with a layered analysis stack:
database → services → Feature Store → engines → UI.

Its pages answer the questions an FPL manager asks every gameweek:

| Page | Question it answers |
|---|---|
| About / Onboarding | *What is this, and which team am I analysing?* |
| 1 · My Team | *What is my squad? Who should be captain?* |
| 2 · Player Rankings | *Which players should I buy / sell / watch?* |
| 3 · Team Analysis | *Which clubs are strong, cheap, productive?* |
| 4 · Team History | *How is my season tracking vs previous ones?* |
| 5 · Player Comparison | *Player A or Player B?* |
| 6 · Assistant Manager | *What should I do this week — transfers, chips, captain?* |
| 7 · Model Analytics | *Did the model predict well? Can I trust the next prediction?* |
| 8 · Model Comparison | *Should I trust the V3 production model vs the V2 control?* |

The application is distinguished by three things that most hobby FPL tools do not have:

1. **An append-only Prediction Ledger.** Every forecast is persisted with the config hash
   and weights snapshot that produced it, so every claim is reproducible and auditable.
2. **A scientific Validation Platform.** Forecasts are scored against real actuals
   (MAE, RMSE, bias, CI calibration) with an evidence ladder and a deliberately
   *human-in-the-loop* learning loop — the model never retrains itself.
3. **A disciplined engineering process.** Three independent audits (security, deployment,
   validation), a versioned configuration system, Alembic migrations, a CI pipeline, and a
   growing 162-test suite.

## 1.2 Why it exists

The project began as a **single owner's personal prototype**: a self-taught builder who
wanted to stop making FPL decisions on gut feel and instead use data — projections,
fixtures, value scores, uncertainty — to inform transfers, captaincy and chip strategy.
It was built "by a beginner" on a single Mac, for a single team (`TEAM_ID = 472930`).

Over five weeks (late July → early August 2026) it evolved from that prototype into a
**documented, tested, security-hardened, multi-user public application** with a production
prediction model (V3 Expected Points), a validated control model (V2), an evidence
framework, and a designed onboarding experience. The ambition is stated plainly in the
README: a production-quality FPL analytics system suitable for public hosting.

## 1.3 Current project status (snapshot, 2026-08-06)

| Dimension | Status |
|---|---|
| Prediction model | **V3 Expected Points (xPts)** is production primary; V1/V2 run as shadow/control |
| Validation platform | Implemented, tested, evidence-ladder driven; awaiting GW1 real actuals |
| Database | SQLite + WAL, Alembic-managed (baseline + audit-log migration), 17 user tables |
| Tests | **162 passed** (`pytest`), `ruff check .` clean, CI workflow ready |
| Security | Phase 1 hardening + Phase 2: admin token gate, append-only audit log, secrets scan in CI |
| Multi-user | Public onboarding + per-session Team Context shipped; team ID is runtime state, not config |
| Deployment | Documented (docs/deployment.md + operations.md + container guidance); not yet hosted |
| Git | On GitHub (`MambonMangos/Manny-s-Mind`); Phase 2 + onboarding work pending commit |

## 1.4 High-level accomplishments

- **Three audit cycles** drove the roadmap: Executive Audit (62/100, "NOT READY", 7
  critical + 18 high findings) → Deployment Readiness (45/100) → Validation Platform
  self-audit (confidence 9/10). Each audit's findings were converted into prioritized
  workstreams and executed.
- **Version control, migrations, logging, env-driven config, pinned deps, license, docs**
  — the entire "deployment foundation" gap closed in one phase (17 → 33 tests).
- **V3 Expected Points model** promoted to production with a shadow/control framework,
  a comparison and explainability layer, and an evidence ladder.
- **Security remediation** — TLS fallback gated, HTML escaping, fail-secure logging,
  dependency pinning, dependency scanning, admin-gated writes, append-only audit log,
  secrets scan in CI.
- **Ruff cleanup** — all ~291 pre-existing lint issues resolved; whole repo lint-clean.
- **Public onboarding** — the app no longer defaults to Manny's team; any visitor can
  validate their own Team ID and use the platform; identity is per-session runtime state.

## 1.5 Future direction

- **Validate V3 with real GW1+ data** — the single highest-priority remaining step. No
  weight tuning or model changes before ≥3 gameweeks of validation data.
- **Execute the post-GW1 ML roadmap** (V1 engine consolidation, single uncertainty source,
  Feature Store de-duplication, vectorization).
- **Public hosting** — containerise, migrate to a client/server database for concurrent
  writes, add monitoring/log aggregation, and finalize hosting.
- **League Intelligence phases 2–7** — live effective-ownership providers, mini-league and
  rival persistence, differential calibration, game-theory engine.
- **UX**: extend the Trust Layer and design system to all remaining pages; "This Week"
  briefing; explainability everywhere.
- **Authentication** — the Team Context layer was deliberately built as the future login
  seam.

---

# 2. Project Origins

**Contributed by:** ML / Analytics Engineer, with the Technical Writer

## 2.1 Initial vision

The original vision was a single sentence: *"make better FPL decisions with data."* The
owner wanted a personal tool that could:

- rank every FPL player by a transparent **value score**;
- project **minutes and points** for the next gameweek;
- evaluate **the squad, transfers, captaincy, chips**;
- keep a **decision history** so the owner could learn which recommendations were right.

It was explicitly a **learning project**. The codebase began as a personal experiment with
no version control, no test discipline beyond "it didn't crash", and no concept of any user
other than the owner.

## 2.2 Original architecture

The original architecture (pre-git, pre-audit) was already **well-layered for a personal
project**, and the auditors gave it credit for that:

```
Streamlit pages (app.py + pages/)
        │  direct get_session() calls
        ▼
services/  (data_loader, scoring, team_service, pipeline, learning_service, …)
        ▼
engines/   (16 engines: value, market, prediction, captain, minutes, projection,
        │    regression, confidence, fixture, bookmaker, opportunity, squad_optimizer,
        │    monte_carlo, market_intelligence, validation, expected_*)
        ▼
features/store.py   (Feature Store — "single source of truth" for derived features)
        ▼
database/  (models.py, crud.py, database.py — SQLAlchemy + SQLite)
        ▼
FPL API  (fantasy.premierleague.com/api)
```

Notable original strengths that survived every later phase:

- **Versioned YAML configuration** (`utils/config.py` + `config/active.yaml` + versioned
  `weights_v1/v2/v3`) — settings externalized, version-tracked, switchable by editing one
  file, with a **config hash** recorded against every experiment.
- **Feature Store pattern** (`features/store.py`) — a single place where per-player derived
  features (minutes, xGI, fixtures, market signals, set pieces, regression flags) are built,
  with lazy caching and ~8 organized categories.
- **Engine separation** — each engine a focused module returning typed dataclasses.
- **Append-only Prediction Ledger** (`prediction_versions`, `projections`) — an
  event-sourcing choice: never mutate, never delete.
- **WAL mode** for SQLite; `yaml.safe_load`; 100% SQLAlchemy ORM (no raw SQL, no SQL
  injection); no secrets committed.

## 2.3 Original prediction methodology (V1)

The original model ("V1") was a **value-score engine layer** rather than a forecasting
pipeline:

- `value_engine.py` — composite value score from weighted components (form, xGI, fixture
  difficulty, price, ownership) plus a player rating.
- `market_engine.py` — transfers in/out, ownership trends, price direction.
- `prediction_engine.py` — a simple points/minute projection (e.g. minutes projected from
  starts rate; points from xGI and form).
- `captain_engine.py` — captaincy analysis from the above.
- `fixture_engine.py` — fixture difficulty, windows, swings.
- `bookmaker_engine.py` — a stub intended to fold in odds (never wired to a data source).
- `monte_carlo_engine.py` — simulation-based uncertainty (unseeded at the time).

**Weaknesses that led to replacement** (all documented in the Executive Audit):

1. The V1 "projection" was a **heuristic blend**, not an expected-value calculation — it
   mixed minutes, xGI, fixture difficulty and price into a single score with no underlying
   probability model.
2. Four V1 engines duplicated logic that had **V2 equivalents** (`value_engine` ↔
   `opportunity_engine`, `market_engine` ↔ `market_intelligence_engine`,
   `prediction_engine` ↔ `minutes_engine` + `projection_engine`, `captain_engine` ↔
   assistant-manager recommendation code). The auditor found **three separate
   implementations** of minutes projection at one point.
3. **No uncertainty.** V1 produced point estimates with no confidence intervals.
4. **Not validated.** There was no ledger, no actuals, no MAE — the owner could not know
   whether the scores were any good.

V1 was never deleted. It remains today as the **fallback** path when no projection data is
available and, together with V2, as part of the shadow/control group. That decision — keep
old models as a control group rather than deleting them — became a founding principle of
the validation philosophy.

## 2.4 Development philosophy

The development philosophy that shaped everything after the audits can be summarized in
four rules, now codified in `docs/development.md` and `docs/stakeholders.md`:

1. **One source of truth.** Constants → `utils/constants.py`; tunable weights → `config/`;
   derived features → Feature Store. Never duplicate a formula across modules.
2. **Prediction freeze until evidence.** No projection/weight/validation changes until
   GW1+ validation data exists. Refactors must be behaviour-preserving and covered by tests.
3. **Zero silent failures.** Fail loudly with a clear log/error; never silently downgrade
   (e.g. no silent TLS downgrade, no silent fixture fallbacks).
4. **Scientific humility.** Every claim about the model is a hypothesis until validated
   against real gameweek actuals. Shadow models are never removed; they exist so every
   production claim is auditable.

---

# 3. Engineering Evolution

**Contributed by:** Platform Engineer (chronology), with inputs from all disciplines

This chapter records the project's evolution chronologically. Each milestone states *what
was done*, *why it was done*, and *the lesson it taught*.

## 3.1 Timeline overview

| Date | Milestone | Chapter |
|---|---|---|
| ~July 2026 | Personal prototype built (single user, no git, no tests) | [2](#2-project-origins) |
| 2026-07-27 | Validation Platform self-audit (confidence 9/10) | [6](#6-validation-platform) |
| 2026-07-28 | Executive Audit — **62/100, NOT READY**, 7 critical / 18 high | [8](#8-security-evolution) |
| 2026-07-30 | Initial commit to GitHub (`414d928`) — repo `MambonMangos/Manny-s-Mind` | [3.2](#32-phase-0-version-control) |
| 2026-08-02 | Deployment Readiness audit — **45/100, NOT READY** | [9](#9-infrastructure-evolution) |
| 2026-08-02 | **Phase 1 (Deployment Foundation)** executed; 17 → 33 tests | [3.4](#34-phase-1-deployment-foundation-2026-08-02) |
| 2026-08-03 | Phase 1 security remediation commit (`fdd7439`) | [8](#8-security-evolution) |
| 2026-08-04 | V3 xPts comparison layer (`df3965f`); design-system UX foundation (`fefad2d`) | [5](#5-prediction-model-evolution), [9](#9-infrastructure-evolution) |
| 2026-08-05 | V3 promoted to production with shadow/control (`3c1b648`); per-viewer team selection; Dev Container; crash fix | [5](#5-prediction-model-evolution) |
| 2026-08-06 | **Phase 2 (security/ops)** + ruff cleanup; 141 tests | [8](#8-security-evolution) |
| 2026-08-06 | **Public Onboarding & Team ID Management**; 162 tests | [9](#9-infrastructure-evolution), [11](#11-public-launch-preparation) |

## 3.2 Phase 0 — Version control (2026-07-30)

**What happened.** The owner created the initial commit and pushed the project to GitHub
(`github.com/MambonMangos/Manny-s-Mind`). This gave the project history, remote backup,
and the ability to be reviewed and rolled back — the single highest-severity finding of the
Deployment Readiness audit ("No version control at all" was rated CRITICAL) was thereby
closed even before the formal Phase 1.

**Why.** A repository that cannot be shared, reviewed, or rolled back cannot become a
serious project.

**Lesson learned.** *Version control is the prerequisite for everything else.* Every later
discipline (security remediation, UX, onboarding) depended on being able to see diffs and
review history.

## 3.3 The audit-driven roadmap (2026-07-27 → 08-02)

Three audits ran almost back-to-back, and together they defined the work plan:

1. **Validation Platform self-audit** (Manuel Lopez, 2026-07-27) — the builder audited his
   own validation infrastructure end-to-end against real FPL API data. Found and fixed 4
   bugs (including a silent data-corruption risk: the `id` vs `player_id` column alias),
   wrote 6 integration tests, and published an honest confidence of **9/10** — with the
   explicit caveat that no real GW1 data existed yet, so MAE and CI calibration were
   unproven.
2. **Executive Audit** (independent Senior Software Auditor, 2026-07-28) — a full-repo
   production-readiness assessment: **7 critical, 18 high, 18 medium, 12 low** findings.
   Overall **62/100**, confidence **5/10**, verdict **NOT READY**.
3. **Deployment Readiness Phase 1** (2026-08-02) — infrastructure-only audit: **45/100**,
   verdict **NOT READY — "Foundation is Sound, Wrapping Is Not"**.

The key structural insight from the Executive Audit was that the *architecture was sound
but the failure paths were untested and unhandled*: no retries on the API client, no
migrations, a test file with zero assertions, a missing ORM model that would crash at
runtime, and every page managing its own DB sessions.

**Lesson learned.** *Get an independent audit before building more.* All three audits
surfaced issues the owner had not seen, and each produced a prioritized, effort-estimated
work plan that the team executed almost verbatim.

## 3.4 Phase 1 — Deployment Foundation (2026-08-02 → 08-03)

Phase 1 was the first disciplined, multi-workstream engineering phase. Its explicit scope:
**infrastructure only — no prediction, weight, or validation behaviour changes.** Five
workstreams ran in parallel (`reports/*_phase1.md`):

| Workstream | Deliverables |
|---|---|
| **Platform** | Env-driven config (`utils/env.py`, `.env.example`), TLS fallback disabled by default, logging (`utils/logging_setup.py`), pinned deps, `.gitignore`, MIT `LICENSE`, rewritten `README.md`, git established |
| **Data** | Alembic framework + baseline migration (zero schema drift vs live DB), API client with configurable timeout/retry/backoff, TLS on by default, `docs/database.md` |
| **ML** | Review-only: engine ownership map, technical-debt register (TD-1..9), post-GW1 roadmap |
| **QA** | 17 → **33 assertion-based tests**; smoke, migration, scoring-weights tests added |
| **Technical Writer** | 9-document package in `docs/` + README docs table |

Phase 1 closed the biggest deployment blockers: version control, migrations, logging,
env support, TLS-insecure-by-default, unpinned dependencies, and missing documentation.
It also produced the two defining engineering controls that still govern the project:
**`docs/operations.md`** (the release checklist) and the **prediction freeze**.

**Verification (Phase 1):** `pytest` 33 passed; `ruff check` clean on Phase 1 files; app
boot HTTP 200; Alembic `upgrade head` → 17 tables matching live schema; weights invariant
(sum = 1.0) held.

**Lesson learned.** *A "behaviour-preserving" phase can still move the project enormously.*
Phase 1 changed zero prediction logic and yet took the project from "undeployable" to
"deployable with moderate risk" by addressing the wrapping, not the engine.

## 3.5 Phase 1 security remediation (2026-08-03)

Commit `fdd7439` hardened the attack surface that the Executive Audit had flagged:

- **API hardening** — the silent `verify=False` TLS fallback became opt-in and loud
  (`FPL_API_ALLOW_INSECURE_SSL`, default `false`); non-HTTPS requests are refused when it
  is off.
- **Dependency scanning** — `pip-audit` added to dev requirements.
- **DB path consistency** — the app resolved its default database path consistently across
  entry points.
- **HTML escaping** — the first steps to neutralize stored-XSS risk around
  `unsafe_allow_html=True` (later systematized into the design system's presenter
  boundary).
- **Fail-secure logging** — logging configured so warnings/errors surface instead of being
  silently dropped.

**Lesson learned.** *Security fixes are cheap when they are structural.* Gating the TLS
fallback behind an explicit flag, rather than patching one bug, removed an entire class of
MITM risk permanently.

## 3.6 V3 xPts comparison layer (2026-08-04)

Commit `df3965f` built the **Expected Points (V3)** model as three independently testable
engines plus orchestration, and — critically — built it as a *scientific comparison*, not a
replacement: a comparison-report service, a V2-vs-V3 comparison dashboard (page 8), and
docs. This established the **shadow/control** pattern that governed the V3 promotion one
day later. See Chapter 5 for the full model history.

**Lesson learned.** *Introduce a new model the way you'd introduce a new product:
alongside the old one, measured, with an explainability layer — never by deletion.*

## 3.7 Phase 1 UX foundation — the design system (2026-08-04)

Commit `fefad2d` created the **3-tier design-token system**, UI primitives, domain
components with a **Trust Layer**, and migrated the Assistant Manager page onto it. This
was the UX discipline's answer to the UX discovery audit's core findings: recommendations
were unaccountable, engineering vocabulary leaked to users, and pages hand-rolled markup.
See [Chapter 9.4](#94-ux-foundation--the-design-system).

**Lesson learned.** *Design systems are a security control too.* The presenter-boundary
rule (all dynamic values escaped at the HTML boundary, pages never build
`unsafe_allow_html=True` strings) systematically closes the stored-XSS class of bugs that
the audit had flagged as M-07.

## 3.8 V3 production promotion (2026-08-05)

Commit `3c1b648` promoted **V3 Expected Points to production primary** with V1/V2 as
shadow/control models, driven entirely by configuration (`config/production/production_v1.yaml`)
and orchestrated by a new `services/production_predictor.py`. Every production path now
consumes V3 by default; V2 keeps being persisted and validated as the control group.

**Lesson learned.** *Model selection is configuration, not code.* Promoting or reverting a
model is a one-line YAML change plus a version bump — the exact same mechanism used for
weights.

## 3.9 Per-viewer team selection (2026-08-05)

Three commits moved the app from single-user to multi-user in one day:

- `1318603` — `?team_id=` URL parameter for per-viewer team selection.
- `00d215e` — **Player Rankings crash fix** (cost-change columns missing from the player
  dataframe caused a runtime crash).
- `deeb567` — sidebar Team-ID input with safe URL-to-widget sync.

This was the **first step toward public multi-user use**: visitors could now point the app
at their own team via the URL. But it still defaulted to Manny's team, and the team ID was
a widget — not validated, not session-scoped. Phase 2's onboarding work (Chapter 9.6)
replaced this with a validated, session-scoped Team Context.

**Lesson learned.** *The URL parameter was a bridge, not the destination.* The intermediate
step taught the team exactly what a public flow must do (validate, scope per session, never
trust the URL as identity) — which is precisely what the final onboarding implemented.

## 3.10 Phase 2 — Security & operations hardening (2026-08-06)

Phase 2 executed the deferred security/operations roadmap:

- **ADMIN_TOKEN gate** (`utils/access.py`) — when configured, mutating actions (result
  ingestion, validation cycles, persist-to-ledger, manual refresh) require a sidebar admin
  unlock. Constant-time token comparison (`hmac.compare_digest`); no token = single-owner
  unrestricted mode preserved.
- **Append-only audit log** — new `AuditLog` table + Alembic migration `b7c8d9e0f1a2`,
  `services/audit.py` with `log_audit()` that *never breaks the primary action*;
  actor attribution from the session Team Context.
- **WAL-consistent backup script** (`scripts/backup_db.py`) — uses the SQLite online
  backup API (not a raw file copy), retention via `--keep N`, optional `--offsite-dir`,
  timezone-aware microsecond stamps.
- **CI workflow** (`.github/workflows/ci.yml`) — ruff → pip check → secrets scan → pytest
  on every push/PR.
- **Ruff cleanup** — all ~291 pre-existing lint issues resolved across the repo (auto-fixes
  plus deliberate `noqa` + `TODO` annotations on two latent runtime bugs — see
  [Chapter 14.8](#148-outstanding-engineering-items-and-technical-debt)).

Suite went from 111 → **141 passed**; `ruff check .` fully clean.

## 3.11 Public onboarding & Team ID management (2026-08-06)

The final major milestone replaced the URL-parameter team selection with a real
**public onboarding flow**:

- `utils/team_context.py` — per-session Team Context (set/clear/get, `require_team()` gate,
  `seed_from_url()` pre-fill hint).
- `services/team_validation.py` — Team ID validated against the FPL API with sanitization,
  structured results, never-raises, fail-fast timeouts.
- `components/onboarding.py` — welcome page with hero, input, help, trust footer.
- Sidebar **team switcher** ("Change Team" → clear + return to onboarding).
- **Gated pages** — About + pages 1, 4, 6, 8 require a validated team; pages 2, 3, 5, 7
  remain public (browse/explore) and 7 remains admin-scoped.
- **Log redaction** — the API client redacts `/entry/<id>` path segments so Team IDs never
  reach logs.
- 29 new tests (rewritten `test_team_id.py` + new `test_team_validation.py`); suite → **162
  passed**.

The app **never defaults to Manny's team anymore** — an unvalidated visitor has no team.

**Lesson learned.** *Identity is runtime state, not configuration.* Removing
`FPL_TEAM_ID`/`TEAM_ID` entirely (rather than keeping a default) is what makes the product
genuinely public: there is no personal team to leak, and a future login system can hand a
persistent profile to the same provider without changing any call site.

---

# 4. Architecture Evolution

**Contributed by:** Platform Engineer (layering) with ML/Analytics Engineer (prediction
path) and Data Engineer (data path)

## 4.1 Initial architecture (pre-audit)

```
┌─────────────────────────────────────────────────────────────┐
│  Streamlit (app.py + pages/1..8)  — UI rendering            │
│  • every page called get_session() directly                 │
│  • hardcoded TEAM_ID = 472930 everywhere                    │
├─────────────────────────────────────────────────────────────┤
│  services/  data_loader, scoring, team_service, pipeline,   │
│             learning_service, snapshot_service, ...          │
├─────────────────────────────────────────────────────────────┤
│  engines/   16 engines (V1 + V2 layers, parallel &          │
│             sometimes divergent)                            │
├─────────────────────────────────────────────────────────────┤
│  features/store.py  Feature Store (single source of truth)  │
├─────────────────────────────────────────────────────────────┤
│  database/  models.py (17 tables), crud.py, database.py     │
│             • create_all() on every start, no migrations    │
│             • SQLite file, world-readable (0644)            │
├─────────────────────────────────────────────────────────────┤
│  FPL API  (no retries, silent SSL downgrade, 30s timeout)   │
└─────────────────────────────────────────────────────────────┘
```

## 4.2 Current architecture (2026-08-06)

```
┌───────────────────────────────────────────────────────────────┐
│  Streamlit (About.py + pages/ + components/)                  │
│  ─ UI rendering; onboarding gate; Trust Layer; admin unlock   │
│  ├  components/ui + domain + design_tokens (design system)    │
│  ├  components/onboarding.py  ── visitor → validated team     │
│  └  components/sidebar.py  ── team switcher, admin, refresh   │
├───────────────────────────────────────────────────────────────┤
│  Session / Team Context  (utils/team_context.py)              │
│  ─ per-session runtime identity; require_team() page gate     │
├───────────────────────────────────────────────────────────────┤
│  services/                                                     │
│  ─ data loading, scoring, team/fixture, pipeline orchestration│
│  ─ production_predictor (primary V3 + shadow V2)              │
│  ─ validation: result_ingestion, validation engine,           │
│    error_classifier, learning_service                         │
│  ─ league_intelligence/ (EO, differentials, mini-league,      │
│    rivals, game-theory interfaces)                            │
│  ─ audit.py (append-only op log), team_validation.py          │
├───────────────────────────────────────────────────────────────┤
│  Feature Store (features/store.py) — SINGLE SOURCE OF TRUTH   │
│  ─ minutes, xGI, fixture, market, regression, set-piece, ...  │
├───────────────────────────────────────────────────────────────┤
│  engines/  20 engines (V1/V2 shadow + V3 production +         │
│            validation + expected_*)                           │
├───────────────────────────────────────────────────────────────┤
│  Data layer (database/)                                        │
│  ─ SQLAlchemy models (18 tables), CRUD, engine (WAL)          │
│  ─ Alembic migrations (baseline + audit_log)                  │
│  ─ SQLite file, owner-scoped, WAL-consistent backups          │
├───────────────────────────────────────────────────────────────┤
│  External: FPL API via api_client.py (retry, backoff, TLS,    │
│            redaction)                                          │
└───────────────────────────────────────────────────────────────┘
```

### Data flow (current)

```
Anonymous visitor
   → onboarding: validate_team_id(raw) → session_state.team_id
   → require_team() gates personalized pages
ensure_data_loaded()          # init DB + fetch when stale
   → api_client.fpl_get()     # retries/backoff/TLS/redaction
   → data_loader upsert
   → scoring.normalise + value score (config/weights)
   → features/store.py build Feature Store
   → production_predictor.run_production_predictions()
        primary: expected_points_v1 (V3 xPts)   ┐  both persisted
        shadow:  projection_v2 (V2 pipeline)     ┘  append-only ledger
   → league_intelligence.run_league_intelligence()   # read-only on projections
   → pages render (rankings, comparison, assistant, analytics, …)
   → post-GW: result_ingestion → validation_engine → error_classifier
        → learning_service → evidence ladder → reports
```

## 4.3 Key architectural decisions (with rationale)

| Decision | Rationale |
|---|---|
| **Append-only prediction ledger** | Forecasts are experiments. Never overwrite; validate versions against actuals. Chosen over in-place update for reproducibility (audit C/D decisions). |
| **Shadow/control models, never deletion** | V1/V2 remain persisted and validated so every V3 production claim is auditable against the control group; "removal" is blocked on GW1 evidence. |
| **Config-driven model selection** (`config/production/`) | Promoting a model is a YAML version bump, not a code change. Services read `get_primary_model_id()` and never hard-code a model id. |
| **Feature Store as single source of truth** | Engines consume features via accessors; recomputation is flagged as technical debt (TD-2) because it risks silent divergence. |
| **Uncertainty is explicit** | Every projection carries 80%/95% CIs from configured variance sources; CI calibration is validated post-GW. |
| **Human-in-the-loop validation** | The model never retrains itself; config changes require manual approval gated by evidence levels. Chosen deliberately over automatic learning (see Chapter 6). |
| **Team identity as runtime state** | No default team, nothing persisted, nothing logged; the Team Context layer is thin so a future login system can replace it without refactoring call sites. |
| **SQLite + WAL now, client/server later** | SQLite is fine for the current workload and trivially portable; the migration path to PostgreSQL is documented and Alembic-ready. |
| **Layered UI with a presenter boundary** | Only renderers touch Streamlit; presenters escape all dynamic values; domain dataclasses are Streamlit-free. Makes a future REST/React migration possible and closes stored-XSS. |

## 4.4 Future architecture (post-launch, see Chapter 13)

```
Browsers / future frontend (REST/JSON layer over services)
        ▼
Reverse proxy (TLS termination) → Streamlit (or dedicated backend)
        ▼
services/  (+ authentication profiles via Team Context seam)
        ▼
PostgreSQL (client/server DB, persistent volume)  ← replaces SQLite
        ▼
FPL API + community EO/top-10k providers (League Intelligence Phase 2+)
plus: monitoring (uptime + log aggregation), scheduled backup jobs
```

---

# 5. Prediction Model Evolution

**Contributed by:** ML / Analytics Engineer

This chapter is the complete history of the prediction system. The platform has run three
generations of models; the guiding rule across all of them is that **the primary model is a
hypothesis under evaluation**, not a permanent truth.

## 5.1 Version 1 — the value-score engine layer (legacy)

### How it worked

V1 was not a forecasting pipeline but a **scoring layer**. Four engines produced scores and
recommendations:

- `value_engine.py` — composite value score (weighted blend of form, xGI, fixture
  difficulty, price, ownership) and a player rating.
- `market_engine.py` — transfer in/out trends, ownership, price movement.
- `prediction_engine.py` — a heuristic minutes/points projection (e.g. projected minutes
  from starts rate; projected points from xGI and form).
- `captain_engine.py` — captaincy analysis over those scores.

These fed the Assistant Manager and the pages directly. Config lived in
`config/weights/weights_v1.yaml` (later `v2`, then `v3`).

### Strengths

- **Simple, transparent, fast.** A single composable number per player was easy to display
  and explain ("Value Score").
- **Good enough for a single user.** For browsing and rough decisions it produced
  plausible rankings.

### Weaknesses

- **No expected-value semantics.** The score blended inputs with no underlying probability
  model — it could not answer "how many points do I expect this player to score?"
- **Duplicated logic across engines** — at one point the auditor identified **three
  implementations** of the minutes projection (V1 `prediction_engine`, V2 `minutes_engine`,
  and the Feature Store heuristic).
- **No uncertainty, no validation.** Point estimates only; nothing was measured against
  actuals, so the owner could not tell if the scores were good.
- **Parallel computation paths** could diverge (V1 vs V2 producing different answers for
  the same player).

### Why it was replaced

V2 introduced the first real forecasting pipeline; V3 then made forecasting principled
(expected values with propagated uncertainty). V1 was **never deleted** — it became the
fallback when no projection data is available and part of the shadow/control group.

## 5.2 Version 2 — the deterministic 7-step pipeline (shadow / control)

### Major improvements

V2 (`services/pipeline.py`) replaced ad-hoc scoring with a **deterministic 7-step
forecasting pipeline** that writes to the ledger:

```
1. minutes_engine        → projected minutes with rotation risk
2. projection_engine     → base point projection with CIs
3. regression_engine     → over/underperformance flags
4. bookmaker_engine      → odds-based adjustment (when available)
5. confidence_engine     → uncertainty quantification & tiering
6. persistence           → Projection ledger (append-only, config-hash stamped)
7. opportunity_engine    → undervalued player detection
```

Supporting engines: `market_intelligence_engine` (ownership/transfers/price trends),
`monte_carlo_engine` (simulation-based uncertainty), `squad_optimizer`
(budget-constrained optimization), `fixture_engine` (difficulty/windows/swings).

### Prediction philosophy

- **Uncertainty is first-class.** Every V2 projection carries 80%/95% confidence intervals
  computed from configured variance sources.
- **Everything is versioned.** `prediction_versions` stores `config_hash` +
  `weights_snapshot` per run; re-running the same gameweek is idempotent.
- **Validation is the same machinery for every model.** Actuals + `validate_version()` →
  MAE/RMSE/bias/CI calibration, per version.

### Validation methodology & lessons learned

The Validation Platform self-audit (2026-07-27) verified the entire chain end-to-end with
synthetic actuals and found/fixed 4 bugs (the `id` vs `player_id` snapshot alias — a silent
data-corruption risk; missing columns; an N+1 query; a logging-format crash). It also
forced an honest conclusion: **synthetic validation proves the plumbing, not the accuracy**.
A synthetic MAE of ~1.19 "tells me the math works, not that the projections are accurate."

### Limitations discovered

- No statistical significance testing on version comparisons (a 12% MAE difference after 1
  gameweek could be noise) — flagged for GW3–5.
- Duplicate metric computation (ingestion service vs validation engine) — could diverge.
- Rigid rule-based error classifier (7 hardcoded thresholds) — needs real-data tuning.
- Human-in-the-loop becomes a bottleneck by GW10–15 if every improvement needs manual
  approval.

## 5.3 Version 3 — Expected Points (xPts) — the production model

### Why Expected Points became the new foundation

V3 answers the question V2's heuristics could not: **what is the expected fantasy points
value of a player, per minute, for a given gameweek?** It is an expected-value calculation
over underlying footballing quantities (expected goals, expected assists, expected goals
conceded, clean-sheet probability, bonus, saves, cards, set pieces) multiplied by a
probability-weighted minutes expectation. Because everything is a *rate per 90*, players
are comparable regardless of minutes played, and the minutes decision is deliberately
separated into its own engine.

### Architecture

Three independently testable engines plus orchestration:

| Component | Responsibility |
|---|---|
| `engines/expected_points_engine.py` | `xPts_per_90` from xGI, CS probability, bonus, saves, cards, set pieces |
| `engines/expected_minutes_engine.py` | `expected_minutes` = start prob × minutes-if-starting × (1 − sub risk) |
| `engines/expected_projection_engine.py` | Compositor: `xPts = xPts_per_90 × (expected_minutes / 90)`, CIs, V2-compatible output |
| `services/production_predictor.py` | Runs primary (V3) + shadow (V2) models, persists append-only |
| `services/expected_pipeline.py` | Comparison + persistence helpers |
| `config/expected_points/`, `config/expected_minutes/`, `config/production/` | Versioned parameters |

Design constraints honoured: engines read **only** through Feature Store accessors; the
output shape mirrors V2 (`ExpectedPlayerProjection` ≡ `PlayerProjection`) so
`insert_projections_bulk()` and `validate_version()` work unchanged; persistence is
append-only and idempotent; model selection is config-driven.

### The mathematics

**Expected Points per 90.**

```
games_played = max(1, round(season_minutes / 90))
xg_90  = season_xG  / games_played
xa_90  = season_xA  / games_played
xgc_90 = season_xGC / games_played          # team-conceded adjustment

xPts_per_90 =
      xg_90  × fixture_multiplier × position[goal_value]      (FPL points per goal)
    + xa_90  × fixture_multiplier × position[assist_value]
    + P(clean_sheet) × position[clean_sheet_value]
    + E[bonus]
    + E[save points]                       (GKP only)
    + E[card deductions]                   (negative)
    + set_piece_bonus                      (penalty / FK / corner primary taker)
```

**Fixture multiplier.** `multiplier = (5 − difficulty) / 4`, floored at 0.5. Easy fixture
(difficulty 1) → 1.0; neutral (3) → 0.5; hard (5) → 0.5 (floor).

**Clean-sheet probability** — anchored to the league-average team xGC/90 so an average
defence lands near the real FPL clean-sheet rate (~25%):

```
P(CS) = clip( (league_avg_xgc_90 − xgc_90_adjusted) / league_avg_xgc_90 × 0.5, 0, 0.6 )
xgc_90_adjusted = xgc_90 × (team_strength_anchor / team_strength_raw)
```

GKP/DEF only; MID gets the 1-pt CS value; FWD receives 0.

**Bonus.** `E[bonus] = clip( bps_per_90 / 160, 0, 3 )` (linear conversion of expected BPS
per 90 to bonus points, capped at 3).

**Saves and cards.** `E[save points] = clip( saves_per_90 / 2, 0, 6 )` (GKP only);
`E[cards] = −( yellow_per_90 × 1 + red_per_90 × 3 )`.

**Set-piece bonus.** Primary penalty taker +0.25 xPts/90; FK +0.05; corner +0.05
(configurable), from Feature Store set-piece flags.

**Final gameweek projection.**

```
xPts = xPts_per_90 × (expected_minutes / 90)
```

**Confidence intervals** are propagated from the variance of both estimates (rate
uncertainty, minutes uncertainty, base randomness), weighted per `variance_sources` and
scaled by expected points (heteroscedastic), matching the V2 convention; the composite
confidence blends the two engines' confidences.

### Expected Minutes methodology

`expected_minutes` is an **expectation** — the probability-weighted sum over minutes
outcomes, not a point estimate of a single outcome:

```
expected_minutes = start_probability × minutes_if_starting × (1 − substitution_risk)
```

**Start probability:**

```
status unavailable (i/s/u) → 0
status doubtful (d)        → 0.40
otherwise:
  start_prob = 0.60 × starts_rate        (observed starts / games)
             + 0.40 × chance_next        (chance_of_playing_next_round)
  ± form adjustment (±0.05 for hot/cold form)
  clipped to [0.05, 0.97]
```

**Minutes if starting** — blend of the player's own history (trusted only when starts ≥ 3)
and a positional baseline:

```
E[minutes | start] = 0.60 × historical_minutes_per_start + 0.40 × positional_baseline
positional_baseline = {GKP: 90, DEF: 88, MID: 78, FWD: 75}
```

**Substitution risk:** `0.25` if `E[minutes|start] ≥ 78` (expected to play ~90 → more
likely subbed), else `0.10`.

Outputs per player: `expected_minutes`, `start_probability`, `minutes_if_starting`,
`substitution_risk`, a rotation-risk label (Low/Medium/High), a data-quality tier, and a
confidence score.

### V3 bug fix note

`features/store.py` had a latent bug in `_build_minutes_features()`
(`df["minutes_season"]` instead of `f["minutes_season"]`). It was never hit by V2 because
V2 reads `store.df` directly; V3 uses the accessor, so the typo was fixed. Behaviour was
unchanged for the existing pipeline and `store.minutes_features()` now works as documented.
This is a textbook case of **new consumers surfacing latent bugs in shared infrastructure** —
a reason the Feature-Store-as-single-source rule matters.

## 5.4 Shadow validation (V3 vs V2)

V3 is validated **side-by-side** with V2 through the existing validation platform. Two
layers:

**Pre-gameweek alignment (no actuals needed).** `run_expected_points_comparison()` runs V3
alongside V2 and returns an in-memory alignment report: common players, mean points per
model, mean difference, mean absolute difference, and the **correlation between V2 and V3
rankings**. This catches structural disagreement early (e.g. a position ranked completely
differently) before any real data exists.

**Post-gameweek A/B through the ledger.** With `persist=True`, V3 is written as its own
append-only version (`version_tag = "xpts-gw{id}-{config_hash[:8]}"`,
`model_name = "expected_points_v1"`), idempotently, at the same time V2's baseline version
is persisted. Once actuals arrive, the standard flow applies with no new machinery:
`mark_actuals()` → `validate_version()` on each → `compare_expected_vs_baseline()` →
`compare_versions()` → improvement %, winner.

**Drift control.** Because V3 is production and V1/V2 the control group, the evidence
framework now governs **continued trust in V3**, not one-time promotion: ≥3 gameweeks of
data before any weight/calibration change; MAE/RMSE on both models with bias monitoring; CI
coverage within tolerance (80% interval covering ~80%); consistency across positions. A
sustained control-group divergence is a **drift signal** and triggers investigation.

### Evidence thresholds

`evidence_status(n_validated_gameweeks)` is the single bridge to the learning-service
thresholds:

| Level | Gameweeks | Meaning |
|---|---|---|
| `weak` | 1 | Preliminary — could be noise. Observe only. |
| `needs_more_data` | 2 | Early signal — not yet reliable. |
| `moderate` | 3–4 | Consistent pattern emerging — monitor. |
| `strong` | 5+ | Reliable pattern (requires consistency ≥ 0.6). |
| `statistically_significant` | 10+ | Established evidence — most extensive validation available. |

The dashboard renders this as an evidence **ladder** with `gameweeks_to_next_level`
(Tiers are sample-size maturity heuristics, not formal statistical significance — no
hypothesis tests or p-values are computed.)
explicit; model changes are **never automatic**.

## 5.5 Comparison & explainability layer

A scientific-validation UI layer wraps the production-vs-shadow comparison so every
V2-vs-V3 claim is evidence-backed and every V3 forecast is explainable:

- `services/comparison_reports.py` — largest disagreements, agreement rates,
  captain/transfer/undervalued differences, evidence bridge, insights.
- `pages/8_Model_Comparison.py` — evidence banner, alignment metrics, scatter, disagreement
  table, **explainability panel**, evidence ladder.
- `tests/test_comparison_reports.py` — 14 tests.

**Explainability panel.** For any player: headline `xPts` plus inputs (`xPts_per_90`,
`expected_minutes`, `minutes_factor`, `start_probability`, `rotation_risk`), the component
breakdown (goals/assists/clean-sheet/bonus/other), confidence, data-quality tier, and the
80%/95% CIs. The requirement this satisfies: **a V3 forecast is never a black box.** When
V3 disagrees with V2, the driver (usually the minutes model) is visible per player.

## 5.6 League Intelligence compatibility

The League Intelligence Layer (Chapter 7) consumes **V3 production projections read-only**
and layers league context (effective ownership, differentials, rival analysis) on top to
shape *recommendations only* — it never modifies projection values, and it never writes to
the prediction ledger. This separation is enforced by design and by test.

## 5.7 Future V3 enhancements (post-GW1 roadmap)

1. Consolidate V1 engines into V3-driven paths (fold value/market/prediction/captain into
   the recommendation pipeline as documented fallbacks; V1/V2 remain as validated
   shadow/control models, never removed).
2. Single uncertainty source — extract CI/variance computation into one module used by
   projection and confidence engines (TD-3).
3. Feature Store de-duplication — fixture-window features fully in the Feature Store;
   engines consume, never recompute (TD-2).
4. Config-driven player rating (TD-4).
5. Performance pass — replace `iterrows()` hot loops with vectorised operations (TD-5).
6. Validation evidence loop — use GW1..N actuals to score engines; prioritize the
   highest-ROI engine improvements.
7. Persistent freshness — store last-refresh timestamp in the DB (TD-8).

Each item is a **behaviour-preserving refactor followed by validation**, not a model change.

---

# 6. Validation Platform

**Contributed by:** ML / Analytics Engineer (self-audit history), QA Engineer (testing)

## 6.1 Scientific methodology

The Validation Platform is **validation infrastructure, not prediction logic**. It answers
one question: *how accurate were past predictions, and which model/config was better?*

```
predictions (append-only ledger)          actuals (result ingestion)
        ↓                                          ↓
        └──────────→ ValidationEngine ──────────→┘
                 validate_version(session, version_id, gameweek_id)
                                    ↓
                       ValidationReport (metrics)
                                    ↓
        persisted to validation_metrics + engine_accuracy
```

Key components:

- `engines/validation_engine.py` — the engine.
- `services/result_ingestion_service.py` — ingests actual GW results post-matchday.
- `services/learning_service.py` — the learning loop that drives improvement.
- `services/error_classifier.py` — rule-based error categorization.

**Evidence thresholds** (weak → needs_more_data → moderate → strong →
statistically_significant) gate how much trust a claim earns. The ladder is the platform's
scientific backbone: **no model change is ever automatic**, and each tier requires more
gameweeks of validated data (see Chapter 5.4).

## 6.2 Metrics computed

Per version + gameweek, `validate_version()` produces a `ValidationReport`:

**Overall accuracy:** `MAE` (mean absolute error), `RMSE` (root mean squared error —
penalizes large misses), `bias` (mean(actual − projected); positive = systematic
underprediction), `median_ae` (robust central error).

**CI calibration:** `coverage_80` / `coverage_95` — fraction of actuals inside the 80%/95%
intervals. Drift from target coverage means the confidence engine's variance is
mis-scaled. Also `ci_width_avg`.

**Breakdowns:** `mae_by_position` / `rmse_by_position` / `n_by_position` per position
(GKP/DEF/MID/FWD); `best_predicted_player_id` / `worst_predicted_player_id` /
`worst_error` for outlier spotting; `engine_scores` per engine via
`validate_engine_contributions`.

**Version comparison:** `compare_versions(...)` — head-to-head accuracy between two
weight/config versions.

## 6.3 Persistence & reproducibility

`ValidationMetrics` rows → `validation_metrics` (append-only). `EngineAccuracy` rows →
`engine_accuracy`. Results are tied to a `version_id` whose `prediction_versions` row
snapshots the `config_hash` and `weights_snapshot` — so every validation is reproducible
against the exact config that produced it. Idempotency is enforced: re-running the same
gameweek returns the same `version_id` and creates exactly one `PredictionVersion` row.

## 6.4 Model comparison & candidate improvements

`learning_service.py` compares versions and flags which engines/configs improve accuracy;
the Weekly Report surfaces **Candidate Improvements** with an explicit
"recommendation only, human review required" warning. The version-comparison flow
(baseline vs treatment) uses the evidence ladder, not a bare percentage. A known gap from
the self-audit: **no statistical significance test** yet (flagged for GW3–5 — a paired
t-test or bootstrap on `compare_versions()`), so early "A is better by X%" claims are
decorative until enough gameweeks accumulate.

## 6.5 Weekly validation

The intended operational rhythm is documented in the Validation Platform self-audit:

- After GW1 finishes: **confirm `event_points` matches real GW scores** (5 minutes — the
  single highest-risk assumption, verified as per-gameweek at audit time when all were 0).
- Click **Ingest GW Results** → **Run Validation Cycle** on the Model Analytics page.
- Review the scatter (points cluster near diagonal = reasonable) and CI80 coverage
  (60–90% = calibrated).
- **Do NOT change any config unless MAE is outside 2–6 points.**
- After GW3–5: add significance testing, tune error-classifier thresholds to real error
  distributions, consolidate duplicate metric computation.
- After GW10–15: Alembic for schema evolution (done — see Chapter 9), and define
  confidence thresholds for *automatic* (low-risk) config changes.

## 6.6 Why automatic learning was intentionally avoided

The human-in-the-loop design is deliberate, and the reasoning is documented in the
self-audit and the learning-service design:

1. **Every recommendation is an experiment.** An append-only ledger with immutable version
   tags only makes sense if nothing silently changes the model.
2. **False confidence is the biggest risk.** Adopting a "better-looking" model that is
   actually noise is worse than a known-good model. The significance-testing gap makes
   automatic application especially dangerous pre-GW5.
3. **The evidence ladder exists to prevent exactly this.** Reaching `statistically_significant`
   (10+ gameweeks) is explicit; automatic changes are proposed as a *future* mechanism only
   for safe, bounded weight shifts (e.g. "MAE improves >5% for 3 consecutive gameweeks AND
   weight delta ≤ ±0.1"), preserving human oversight for risky changes.

## 6.7 Self-audit history & confidence

The 2026-07-27 self-audit ran every component end-to-end against real FPL API data plus
synthetic actuals: pipeline → persist (563 projections) → inject actuals → validate
(MAE≈1.19) → classify (188 errors) → report (6 insights). It found and fixed 4 bugs, added
6 integration tests, and concluded with **confidence 9/10** — with the honest caveat that
the missing point requires real GW1 data: *"no amount of synthetic testing can substitute
for it."*

## 6.8 Known gaps (Phase 1, documented, not yet fixed)

| Gap | Impact |
|---|---|
| No baseline "v1 vs v2" benchmark yet — needs GW1 actuals | Cannot yet prove V2 > V1; V1 retirement (TD-1) blocked on evidence |
| No statistical significance testing on comparisons | Early improvement claims could be noise |
| Validation engine couples directly to DB CRUD | Harder to unit-test without a live DB (TD-6) |
| Error classification is rule-based (7 fixed rules) | Requires tuning as real failure modes surface |
| Duplicate metric computation (ingestion vs validation engine) | Two sources of truth can diverge |

---

# 7. League Intelligence

**Contributed by:** ML / Analytics Engineer

## 7.1 Purpose

The prediction layer answers *"how many points will players score?"* League Intelligence
adds the dimension prediction intentionally does not: **league context** — what the
manager's rivals own, who is a differential, what actually moves league position. It
answers questions like:

- "Everyone in my mini-league owns Haaland — if he blanks, I lose nothing; if he hauls, I
  gain nothing."
- "Rival #3 is chasing me and owns my captain. Should I pick a different one?"
- "Nobody in my league owns this mid-priced midfielder with elite xPts — a differential."

### Core design principle (non-negotiable)

> **The prediction engine is never contaminated by league strategy.**

Projections remain objective, measurable, validated and reproducible. League context is
layered **on top of** predictions, inside the League Intelligence Layer, and only ever
shapes **recommendations**. Every recommendation carries the untouched projection value
(`xpts`) alongside a league-aware `strategy_score`. The layer never writes to the
prediction ledger — enforced by test.

## 7.2 Architecture & modules

```
FPL API ─► Data ingestion ─► Feature Store
                                 │
                                 ▼
                     PREDICTION LAYER (V2+V3, objective)
                     projections + CIs, append-only ledger
                                 │  (read-only projections)
                                 ▼
                     DECISION INTELLIGENCE (comparison_reports)
                                 ▼
                     LEAGUE INTELLIGENCE  ★ this layer ★
                     services/league_intelligence/
                                 │  (typed recommendations)
                                 ▼
                     RECOMMENDATION ENGINE (assistant_manager)
                                 ▼
                     VALIDATION PLATFORM (learning_service thresholds)
```

| Module | Responsibility | Status |
|---|---|---|
| `models.py` | Pure dataclasses (no Streamlit, no DB): `PlayerExposure`, `DifferentialScore`, `StrategicRecommendation`, `MiniLeagueAnalysis`, `RivalAnalysis`, `LeagueIntelligenceReport` | ✅ |
| `engine.py` | `run_league_intelligence(...)` orchestrator — one call → one self-contained report, no hidden state; all inputs injectable | ✅ |
| `providers.py` | Boundary to external data: Protocols (`OwnershipProvider`, `CaptainPollProvider`, `CommunityStatsProvider`, `MiniLeagueProvider`) so **no external source is ever hard-coded**; reference impls: `FeatureStoreOwnershipProvider` (offline) + `FPLApiMiniLeagueProvider` (degrades to empty on failure) | ✅ |
| `effective_ownership.py` | `compute_effective_ownership(selected, captained, tc)` = selected% + captained% + triple-captained%; league/rival ownership helpers; `PlayerExposure` rows | ✅ |
| `differential.py` | `DifferentialScorer`: min-max normalises 7 features (xPts, expected minutes, fixture attractiveness, inverse ownership, transfer velocity, price movement, rotation risk), then applies **config-driven weights** (`config/league_intelligence/league_intelligence_v1.yaml`); `xpts` carried through unchanged | ✅ |
| `mini_league.py` | `MiniLeagueAnalyzer`: common players, league differentials, captain overlap, ownership overlap, risk profile, Jaccard squad similarity, competitive threats — **analysis only** | ✅ |
| `rivals.py` | `RivalTracker`: per-rival squad diff, captain comparison, differential opportunities, transfer divergence, weak positions by xPts, aggregate xPts totals — **analysis only** | ✅ |
| `game_theory.py` | `GameTheoryEngine` Protocol + `get_game_theory_engine()` guard returning an unimplemented engine while `game_theory.enabled: false` — **architecture & interfaces only** | ✅ interfaces |

## 7.3 Current capabilities

Phase 1 shipped the full **foundation**: orchestrator, typed models, provider interfaces,
effective-ownership engine, config-driven differential scoring, mini-league analyzer, rival
tracker, and game-theory interfaces — with **16 tests** (synthetic, no network) and a
versioned config category registered in `active.yaml`. The Assistant Manager
(`run_assistant`) already calls `run_league_intelligence` with V3 production projections and
exposes exposures/differentials on the `AssistantReport.league_intelligence` field.

## 7.4 Future roadmap

1. **Community Intelligence wiring (Phase 2)** — a `CommunityStatsProvider` pulling live
   effective-ownership / top-10k data into the existing interface; captain polls into
   captaincy-hedge recommendations.
2. **Mini-league data pipeline (Phase 3)** — persist league standings + per-entry squads so
   the analyzer runs historically.
3. **Rival tracking persistence (Phase 4)** — store per-rival transfer history for true
   `transfer_divergence`.
4. **Live EO engine calibration (Phase 5)** — validate EO against league-standings
   outcomes; tune `exposure_tiers`.
5. **Differential weight tuning (Phase 6)** — back-test differentials against actuals via
   the validation platform; tune weights in a new config version.
6. **Game Theory Engine (Phase 7)** — implement `ExpectedLeaguePositionGain` once
   differential scoring is validated and ≥1 gameweek of mini-league data exists; flip
   `game_theory.enabled: true`.
7. **UI integration** — a dedicated League Intelligence tab on the roadmap.

**Data-source rule:** no source is hard-coded. A new source = a new provider class
implementing the existing Protocol, injected at the call site. Candidate sources
researched: fantasyfootballpundit.com EO tables (~30 min after deadline), official FPL
bootstrap ownership (already in the Feature Store), LiveFPL / fpl.page / fpl.team top-10k
samples (label as estimates), community captain polls (soft signals), FPL API league
standings and rival squad picks.

**Risks & mitigations:** garbage league data → providers degrade to empty and the report's
`inputs` records exactly what was available (never trust a figure computed from an empty
sample); EO contamination fear → the layer never writes to the ledger and carries `xpts`
unchanged (enforced by test); over-fitting differential weights → config versions +
validation platform; per-entry API rate limits → reuse `fpl_get` retry/backoff and cache per
gameweek.

---

# 8. Security Evolution

**Contributed by:** Security Manager (posture & findings), Platform Engineer (fixes)

## 8.1 Original security posture

The original codebase had good instincts and serious gaps. **Good:** no secrets/API keys in
source; 100% SQLAlchemy ORM (no raw SQL / injection risk); no dangerous builtins (`eval`,
`exec`, `pickle`); `yaml.safe_load`; `.gitignore` excluded `.env`/DB/logs; TEAM_ID is public
FPL data (not sensitive). **Gaps:** the API client silently disabled TLS verification on
error (with the warning globally suppressed) — a live MITM risk; the SQLite DB file was
world-readable (0644); pages used `unsafe_allow_html=True` with interpolated data (stored
XSS); logging dropped everything; dependencies were loosely pinned; and there was no
version control, so nothing could be reviewed or rolled back.

## 8.2 The Executive Audit (2026-07-28) — findings by severity

**Overall:** 62/100, confidence 5/10, verdict **NOT READY**. Scope: 60 Python source files,
7 YAML configs, 2 test files.

### Critical (7)

| # | Finding | Why it mattered |
|---|---|---|
| C-01 | No database migration system (`create_all()` on startup) | Any schema change required data loss; no incremental deploys |
| C-02 | API error handling nonexistent (no retry / rate-limit handling) | A single 429 or 5xx crashed the whole app — worst during GW deadlines |
| C-03 | `ManualSquad` model imported but missing | `save_manual_squad()` would crash at runtime |
| C-04 | Test suite provided false confidence (zero-assertion test) | Developers believed untested code worked |
| C-05 | Validation engine tightly coupled to DB/CRUD | Couldn't unit test without a live DB; brittle to schema changes |
| C-06 | Projection/confidence variance duplicated with identical weights | Two uncertainty implementations that would diverge |
| C-07 | Fixture features duplicated between Feature Store and engine | Silent divergence guaranteed over time |

### High (18) — selected highlights

- **H-01** no indexes on 5 FK columns → full table scans on every join.
- **H-02** 27 `iterrows()` loops across 6+ engines → O(N×E) pipeline, slow pandas.
- **H-05** **SSL verification silently disabled on failure** → MITM risk with no alert.
- **H-06** four V1 engines still active alongside V2 equivalents → divergent results;
  minutes projection existed in **three** implementations.
- **H-09** `min()`/`max()` on empty dict crashes insight generation.
- **H-10** invalid YAML crashes the entire application (no fallback).
- **H-13** market engine hardcoded "1M FPL players" → wrong transfer velocity at scale.
- **H-14** bookmaker engine always returns zero (dead code path).
- **H-15** in-place projection mutation breaks reproducibility.
- **H-16** 7 pages + 1 component manage DB sessions directly.
- **H-17** database world-readable (0644).
- **H-18** snapshot `player_id` defaults to 0 → invalid FK / silent corruption.

### Medium (18) — selected highlights

- **M-01** no unique constraints on 4 core tables → duplicate rows on repeated ingestion.
- **M-07** stored XSS risk via `unsafe_allow_html=True` in 5 files.
- **M-08** no SQLite connection pooling limits → `database is locked` under concurrency.
- **M-13** hardcoded `TEAM_ID` → single-user only, no env fallback.
- **M-18** Monte Carlo engine unseeded → non-reproducible simulations.

### Low (12) — selected highlights

- **L-02** JSON-in-Text columns; **L-04** missing FKs on team_id columns; **L-06**
  exception leakage to logs; **L-08** "differentails" typo; **L-09** dead `weights_v1.yaml`;
  **L-11** config cache no TTL; **L-12** silent fixture fallback (flat 3.0).

### Positive findings (worth preserving)

No circular imports crashing; no memory leaks; no unclosed file handles/connections; no
hardcoded credentials; no debug endpoints; no monkey-patching; safe YAML; WAL mode;
config-driven design; append-only ledger; `Depends(get_store)` dependency injection;
`from __future__ import annotations` everywhere; dataclass result types.

**Why these fixes mattered:** C-02 and H-11 (retry/rate-limit) are the difference between
"crashes during the most important week of the season" and "survives GW1 API load." H-05
was a live MITM vulnerability where an attacker on the network could have intercepted the
data feed. C-03 and H-18 were guaranteed runtime crashes. C-04 was the most insidious —
the suite *passing* gave false confidence.

## 8.3 Completed security work

### Phase 1 security remediation (2026-08-03, commit `fdd7439`)

- **API hardening** — silent `verify=False` fallback replaced by an explicit,
  default-off `FPL_API_ALLOW_INSECURE_SSL` flag; when off, non-HTTPS requests are refused
  outright and SSL failures are logged as errors and re-raised (no insecure retry).
- **Dependency scanning** — `pip-audit` added to dev dependencies; `pip check` in CI.
- **DB path consistency** — default database path resolved identically across entry points
  (previously the app and `alembic` could target different files).
- **HTML escaping** — stored-XSS mitigation began.
- **Fail-secure logging** — logging configured via `utils/logging_setup.py`
  (`LOG_LEVEL`/`LOG_FILE`), so warnings/errors are no longer silently dropped.
- **Dependency pinning** — `requirements.txt` / `requirements-dev.txt` pinned to exact
  versions (`==`), eliminating drift between environments.
- **Env-driven config** — `utils/env.py` loads `.env` at import; `_env_int/_env_float/
  _env_bool` helpers; every deployment-specific value (timeouts, retries, backoff, SSL
  flag, staleness) externalized.

### Phase 2 security & operations (2026-08-06, current work)

- **ADMIN_TOKEN gate** (`utils/access.py`) — optional write-action protection. When set,
  mutating actions (result ingestion, validation cycles, persist-to-ledger, manual data
  refresh) require a sidebar admin unlock. Constant-time comparison
  (`hmac.compare_digest`); no token = single-owner mode preserved. On Streamlit Cloud,
  the token comes from `.streamlit/secrets.toml`.
- **Append-only audit log** — `AuditLog` table (Alembic `b7c8d9e0f1a2`),
  `services/audit.py`; `log_audit()` records *who did what* (ingest, validate, refresh,
  persist) with actor attribution from Team Context (`team:<id>` or `unknown`); failures
  are logged and swallowed so audit logging never breaks the primary action. Visible under
  *Recent Activity* on the Model Analytics page.
- **CI secrets scan** — the workflow runs `git grep` for private keys, AWS keys, GitHub
  tokens, Slack tokens, and `sk-*` keys, and fails on any match.
- **Database file permissions** — the app no longer leaves the SQLite file world-readable
  (owner-scoped, in `.gitignore`).
- **TLS posture** — only `certifi` CA bundle is used for verification; `urllib3` pinned.
- **Log redaction** — `api_client._redact_url()` redacts `/entry/<id>` path segments so
  FPL Team IDs never reach logs (supports the onboarding privacy model).

## 8.4 Current remaining risks

| Risk | Severity | Mitigation / roadmap |
|---|---|---|
| No authentication yet — Team ID is public data and sessions are anonymous | MEDIUM | Team Context is the future login seam (Chapter 11); no PII stored |
| SQLite single-writer under concurrent public load | MEDIUM | Documented; migrate to PostgreSQL for public hosting |
| No log aggregation / monitoring (self-host) | MEDIUM | Add uptime monitoring + log shipping when hosted (Phase 3) |
| Stored-XSS class not fully closed on legacy pages | LOW/MEDIUM | Design-system presenter boundary closes it as pages migrate; legacy `player_card.py`/`fixture_widget.py` consolidation pending |
| `fetch_all_picks()` up to 38 sequential API calls (Team History) | MEDIUM | Rate-limit risk under public load; monitor 429s; parallelize/cache (post-launch) |
| No per-page `db_session()` context manager yet | LOW | Consolidation documented (`docs/database.md`) |
| Secrets scan is regex-based (gitleaks is stronger) | LOW | Optional upgrade in CI |

## 8.5 Future security roadmap

1. **Authentication & user profiles** — via the Team Context seam (no call-site refactor).
2. **PostgreSQL migration** for concurrent multi-user writes + proper row-level isolation.
3. **Monitoring & log aggregation** (uptime checks against `/_stcore/health`, log
   shipping/rotation), alerts on API failure bursts.
4. **Rate limiting / caching** for the FPL API surface under public load.
5. **Data-access layer** (`with db_session()`) to guarantee session closes under
   exceptions.
6. **Harden legacy pages** onto the escaping component layer; remove `player_card.py` /
   `fixture_widget.py`.
7. **Upgrade secrets scan** to a maintained tool (e.g. gitleaks) in CI.
8. **Periodic dependency audit** (`pip-audit`) as a scheduled/CI gate.

---

# 9. Infrastructure Evolution

**Contributed by:** Platform Engineer (deployment/config/session), Data Engineer (DB/API)

## 9.1 Deployment readiness

The Deployment Readiness audit (2026-08-02) scored the project **45/100 — NOT READY
("Foundation is Sound, Wrapping Is Not")**. The core architecture was already strong; what
was missing was almost entirely infrastructure. Its highest-severity risks:

| # | Risk | Severity | Resolution |
|---|---|---|---|
| R1 | No version control | CRITICAL | Initial commit 2026-07-30 → GitHub |
| R2 | No migration system (`create_all()` on start) | CRITICAL | Alembic baseline `129653672751` (17 tables, zero drift) |
| R3 | Single-user hardcoding (`TEAM_ID=472930`) | HIGH | Phase 2 onboarding — team ID is now per-session runtime state |
| R4 | `.env` support declared but never wired | HIGH | `utils/env.py` loads `.env` at import |
| R5 | Silent SSL downgrade | HIGH | `FPL_API_ALLOW_INSECURE_SSL=false` default, refuse non-HTTPS |
| R6 | Logging black hole | HIGH | `utils/logging_setup.py` wired into app startup |
| R7 | Loose pins (`>=`) | MEDIUM | Exact `==` pins + dev/prod split |
| R8 | SQLite single-writer | MEDIUM | Documented; PostgreSQL for public hosting (Phase 2+) |

Phase 1 executed the audit's recommended change list (config externalization, dependency
hardening, documentation, production-readiness fixes, repository preparation). The success
criteria — application functionally identical, prediction behaviour unchanged, validation
unchanged — were met, verified by 33 tests and an HTTP-200 boot.

## 9.2 Configuration management evolution

The configuration system evolved in three layers, in strict precedence order:

```
Environment Variables (.env)   ← loaded once by utils/env.py
        ↓
config/*.yaml  (versioned, active version chosen in config/active.yaml)
        ↓
Safe Defaults (utils/constants.py)
```

- **Phase 1** externalized every deployment-specific value out of source: `DATABASE_URL`,
  `FPL_API_BASE_URL`, `FPL_USER_AGENT`, `FPL_API_TIMEOUT`, `FPL_API_MAX_RETRIES`,
  `FPL_API_BACKOFF_BASE`, `FPL_API_ALLOW_INSECURE_SSL`, `DATA_STALENESS_SECONDS`,
  `LOG_LEVEL`, `LOG_FILE`, and later `ADMIN_TOKEN` and `DB_ALLOW_CREATE_ALL`.
- **Versioned YAML** — `weights_v1/v2/v3`, `prediction_v1`, `expected_points_v1`,
  `expected_minutes_v1`, `features_v1`, `fixtures_v1`, `minutes_v1`, `bookmaker_v1`,
  `league_intelligence_v1`, `production_v1` — selected by `config/active.yaml`. Switching
  behaviour is a one-line edit + restart; old versions are preserved for historical
  comparison.
- **`config/production/production_v1.yaml`** is the single source of truth for which model
  is primary (`expected_points_v1`) and which run as shadow (`projection_v2`).
- **Invariant enforcement** — the loader requires `value_score` weights sum to 1.0; a
  permanent test guards it.
- **Security posture** — no secrets in the repo; future secrets go to `.streamlit/secrets.toml`
  (gitignored) or env vars; `.env.example` is the authoritative environment contract and
  is validated for drift.

**Team identity is explicitly *not* configuration.** There is no `FPL_TEAM_ID` variable;
the viewer's Team ID is per-session runtime state (see 9.6).

## 9.3 Database & schema evolution (Data Engineer)

**Original design** — 17 SQLAlchemy tables in a single SQLite file, created with
`Base.metadata.create_all()` on every startup. No migrations, no unique constraints on
several tables, no indexes on key FKs, world-readable permissions, and an `id` vs
`player_id` column-name ambiguity that caused a silent data-corruption bug.

**Phase 1 — Alembic.** Baseline migration `129653672751_baseline_schema` recreates the
full schema and was verified against the live database (identical table sets, zero drift).
`create_all()` remains only as a bootstrap convenience, gated by `DB_ALLOW_CREATE_ALL`.
Migration policy: **new schema changes ship as Alembic migrations, never `create_all()`.**

**Phase 2 — AuditLog migration** `b7c8d9e0f1a2_add_audit_log` added the operational audit
table, bringing the schema to **17 user tables + `alembic_version`** (18 total, matching
the 18 model classes).

**Today's tables** (17 user tables): `teams`, `players`, `gameweeks`,
`player_gameweek_stats`, `price_history`, `snapshots`, `player_snapshots`,
`prediction_versions`, `projections`, `experiment_runs`, `decision_log`,
`recommendation_outcomes`, `validation_metrics`, `error_classifications`,
`engine_accuracy`, `chip_state`, `audit_log`.

**CRUD improvements** — consistent upsert patterns; bulk projection writes; validation
CRUD; idempotency guards on the ledger. Rollback strategy: every migration has a
`downgrade()`; SQLite is a single file so a file copy is a complete backup.

**API reliability improvements** — the FPL client now provides a 30s configurable timeout,
exponential-backoff retries (3 by default), retry on 429 (honouring `Retry-After`, clamped
to 60s) and 5xx, retry on connection errors/timeouts, TLS verification on by default, and
per-team log redaction. The onboarding validator uses a fail-fast override (10s, 1 retry).

**Data validation** — the Feature Store and snapshot service were fixed to use one column
naming convention; engine empty-input guards were added across the engine layer so empty
data produces empty/zero output instead of crashes.

**Session handling** — the app uses one SQLite engine (WAL, `check_same_thread=False`) with
per-request sessions; pages still call `get_session()` individually (a documented
simplification to be consolidated into a `with db_session()` context manager).

**Performance improvements** — Phase 2's ruff cleanup resolved the lint debt and
documented the latent `iterrows()` hot-loop work (TD-5) for the post-GW1 performance pass.

**Remaining database roadmap**

1. Add missing FK indexes (`Player.team_id`, legacy tables) — accept full scans until data
   grows.
2. Unique constraints on `(player_id, gameweek_id)`-style natural keys (requires a
   migration and real-ingestion validation).
3. Replace JSON-in-Text columns with proper `JSON` type.
4. Add `db_session()` context manager; remove direct `get_session()` from pages.
5. Migrate to PostgreSQL for public multi-user hosting (Alembic-ready; URL + volume change).
6. Persist data-freshness timestamp in the DB so staleness survives restarts.
7. Paginate `get_prediction_versions()` as the ledger grows.

## 9.4 UX foundation — the design system

The UX discovery audit (August 2026) found a high-quality but *under-utilized* component
layer: several pages bypassed shared components, hand-rolled markup, hid filter labels,
and showed engineering jargon to end users. Phase 1 UX built the foundation:

- **3-tier design tokens** (`components/design_tokens.py`): `PALETTE` (raw hex) →
  `COLORS` (semantic mapping) → state groups & primitives (evidence/confidence/risk/
  fixture levels, typography, spacing, radii, breakpoints). Components ask *what meaning*,
  never *which hex*; unknown tokens raise `KeyError` so typos fail fast. The legacy CSS
  variable block is emitted byte-for-byte and pinned by regression test.
- **Component layering contract** — `services/` (backend) → `components/domain/models.py`
  (Streamlit-free dataclasses) → `components/domain/*.py` (presenters, HTML with escaping)
  → `components/ui/*.py` (primitives/renderers) → `pages/` (adapters). Only renderers touch
  Streamlit; **all dynamic values are escaped at the presenter boundary**; pages never build
  `unsafe_allow_html=True` strings.
- **Trust Layer (mandatory)** — every recommendation renders with a `TrustSection`
  (evidence level + gameweek count, confidence %, reasoning, model agreement, historical
  accuracy, data quality). **Never fabricate** — a missing measure stays `None` and the
  slot is omitted; a truthful missing badge is preferred to an invented number.
- **Assistant Manager migrated** onto the system as the first page; regression-tested.

## 9.5 Environment & tooling

- **Python 3.12** (`uv` managed at `.venv`), pinned deps, no system libraries required.
- **Lint/format**: ruff 0.16.1 — `ruff check .` clean across the whole repo.
- **Tests**: pytest 9.1.1 — **162 passed**.
- **Dev container** (`.devcontainer/`) added so a contributor can spin up a consistent
  environment.
- **Git**: GitHub `MambonMangos/Manny-s-Mind`, `main` branch, 10 commits (07-30 → 08-05);
  Phase 2 + onboarding work is uncommitted pending final review.
- **CI** (`.github/workflows/ci.yml`): lint → pip check → secrets scan → pytest on
  Ubuntu + Python 3.12, on every push/PR.
- **Backups**: `scripts/backup_db.py` — WAL-consistent online backup (`sqlite3.backup()`),
  `--keep N` retention, optional `--offsite-dir`, timezone-aware microsecond stamps
  (microseconds fix a same-second prune collision).

## 9.6 Session management & public onboarding

This is the milestone that turns Manny's FPL House from a personal tool into a **public
application**. Before it: `TEAM_ID=472930` was a constant; then a `?team_id=` URL param and
a sidebar widget drove team selection but still defaulted to Manny's team and trusted the
URL. The final design:

```
Anonymous Visitor
        ↓
Enter Team ID  (components/onboarding.py)
        ↓  validated against the FPL API (services/team_validation.py)
Session Team Context  (utils/team_context.py ↔ session_state.team_id)
        ↓
Every personalized service reads get_current_team_id()
```

**Design rules (documented in `docs/onboarding.md`):**

1. **No default team.** An unvalidated visitor has no team, never Manny's team.
2. **Validation is mandatory and fail-fast.** Input sanitized to digits-only within
   `1..99_999_999` before any API call; 10s timeout, single retry; structured result
   (VALID / INVALID_INPUT / NOT_FOUND / ERROR) with friendly, safe messages; the validator
   never raises and never leaks exception details.
3. **URL params are hints, never identity.** `?team_id=` only pre-fills the onboarding
   input.
4. **Session-scoped, nothing persisted, nothing logged.** Team ID lives in Streamlit
   session state; `api_client` redacts `/entry/<id>` segments from logs; sessions are
   isolated by Streamlit.
5. **Page gating via `require_team()`.** Gated (team-specific): About (onboarding host),
   pages 1 (My Team), 4 (Team History), 6 (Assistant Manager), 8 (Model Comparison).
   Public (browse/explore): pages 2, 3, 5. Page 7 (Model Analytics) is admin-scoped and
   ungated.
6. **Change Team.** Sidebar shows the current team with a **Change Team** button that
   clears the session team and returns to onboarding (`st.switch_page("About.py")`, rerun
   fallback) — no manual browser-state clearing.

**Future compatibility.** The Team Context layer is the foundation for authentication: a
future login system can populate the same provider from a persistent user profile
(Anonymous → Team ID → Session Team Context → Future Login → Persistent User Profile)
without refactoring any call site.

---

# 10. Quality Assurance

**Contributed by:** QA Engineer

## 10.1 Testing history

| Milestone | Suite | Notes |
|---|---|---|
| Pre-Phase 1 | 17 tests (3 files) | One file was exception-only — **zero assertions**, printed "ALL TESTS PASSED!" |
| Phase 1 (2026-08-02) | **33 tests** (5 files) | Rewrote `test_v2_pipeline.py` assertion-based; added smoke, scoring-weights, migration tests |
| V3 + League Intelligence | **111 tests** | Expected-minutes/points/projection engines, comparison reports (14), league intelligence (16) |
| Phase 2 (2026-08-06) | **141 tests** | Post-ruff-cleanup baseline, incl. admin-access + audit-log + backup tests |
| Onboarding (2026-08-06) | **162 tests** | Rewritten `test_team_id.py` + new `test_team_validation.py` (29 tests total in the two) |

Today: **162 passed**, `ruff check .` clean, whole repo.

## 10.2 Testing philosophy

1. **Assertions over exceptions.** The original suite's false confidence (C-04) was the
   single most damaging finding. Every test asserts real behaviour.
2. **Hermetic where possible.** New tests use synthetic data and injected dependencies
   (e.g. the onboarding smoke tests mock `services.team_validation.fpl_get`); migration and
   smoke tests use scratch/in-memory databases. Known debt (M-11/M-12): some legacy tests
   read live `config/` and share a file DB — documented for cleanup.
3. **Behaviour-preserving refactors must stay green.** The prediction freeze (development
   rule) is enforced by the suite.
4. **Invariant guards.** `value_score` weights sum to 1.0; active config matches
   `weights_v3`; schema parity between Alembic and models; exactly one migration head;
   the CSS token block pinned byte-for-byte.
5. **Smoke coverage for boot.** Every `pages/*.py` parses/compiles; `active.yaml` + all
   referenced version files load; DB initializes from models; logging setup idempotent.

## 10.3 Test inventory

| File | Covers |
|---|---|
| `test_v2_pipeline.py` | End-to-end V2 pipeline behaviour (assertion-based) |
| `test_scoring_weights.py` | Weights integrity + active config selection |
| `test_smoke.py` | Boot, page parse, config load, DB init |
| `test_migrations.py` | Alembic upgrade, schema parity, single head |
| `test_validation.py` | Validation engine metrics / CI calibration / persistence |
| `test_validation_platform.py` | 6 integration tests: schema integrity, full validation cycle, version comparison, error-classifier rules, persistence idempotency, pipeline regression |
| `test_expected_*_engine.py` (×3) | V3 engines: expected points, expected minutes, expected projection |
| `test_comparison_reports.py` | 14 tests: ranking/agreement/recommendation differences, evidence thresholds, report + persistence |
| `test_league_intelligence.py` | 16 tests: EO, differentials, mini-league, rivals, provider degradation (synthetic, no network) |
| `test_ui_components.py` | Design system: token CSS block pin, badge/primitives, Trust Layer |
| `test_production_predictor.py` | Primary + shadow dispatch, model selection, error isolation |
| `test_production_fixes.py` | Regression guards for production-path fixes |
| `test_access.py` | Admin token gate (constant-time compare, unlock/lock, unset-token mode) |
| `test_audit.py` | Audit log append-only, actor attribution, never-breaks-primary |
| `test_backup.py` | WAL-consistent backup, retention, offsite copy, same-second stamp uniqueness |
| `test_team_id.py` | Team Context: session persistence, no default team, change team, multi-change, refresh, sidebar reset, URL seeding, `require_team()` gate |
| `test_team_validation.py` | Valid / not-found / 5xx / timeout / connection / unexpected-hidden, sanitization cases |

## 10.4 Major bugs discovered

| Bug | Found by | Severity | Status |
|---|---|---|---|
| `ManualSquad` model missing → runtime crash (C-03) | Executive Audit | Critical | Fixed |
| `id` vs `player_id` snapshot alias → silent data corruption (H-18/M-09) | Validation self-audit | Critical (silent) | Fixed + documented alias |
| Zero-assertion test suite (C-04) | Executive Audit | Critical | Rewritten |
| SSL silent downgrade (H-05) | Executive Audit | High (security) | Fixed (gated) |
| Same-second backup stamp collision → prune test failure | Phase 2 QA | Medium | Fixed with `%f` microseconds |
| `minutes_season` typo in Feature Store accessor | V3 implementation | Latent | Fixed (was never hit by V2) |
| Player Rankings crash — cost-change columns missing | Runtime (00d215e) | High | Fixed |
| Player Comparison fixture-slider bounds bug (`min_value=5, value=(1,10)`) | UX discovery audit | Latent (raises at runtime) | Documented in migration order (page 5) |
| N+1 query in error classifier (H-03) | Executive Audit | High | Documented post-GW1 |
| `fetch_all_picks()` 38 sequential calls (H-04) | Executive Audit | High | Documented; monitor under load |

## 10.5 Critical audit findings → resolution status

The Executive Audit's 8 pre-GW1 action items and their status:

| Item | Status |
|---|---|
| API retry + rate-limit handling (exponential backoff, 429 `Retry-After`) | ✅ Done (Phase 1 + onboarding fail-fast override) |
| Fix false-positive test suite (real assertions + edge cases) | ✅ Done (assertion-based rewrite; empty-input guards in engines) |
| Config file fallback / safe defaults | ✅ Done (constants fallbacks + `config` hierarchy) |
| Handle empty DataFrames gracefully | ✅ Done (guard clauses with logging across engine layer) |
| Fix `min()` on empty dict crash | ✅ Done |
| Critical FK indexes | ⏳ Documented as debt (acceptable at current scale; migrate-with-postgres) |
| `id` vs `player_id` ambiguity | ✅ Done |
| Rollback on data-loader error | ✅ Done |

Post-GW1 recommendations (validate with real data, then refactor): V1 engine retirement,
single uncertainty source, immutable projections, unique constraints, seeded Monte Carlo,
`iterrows()` vectorization, index+measure — all tracked in `docs/prediction.md` TD-1..9.

## 10.6 Coverage improvements & current status

Coverage grew from "the pipeline runs without crashing" to **per-engine, per-service,
per-component unit and integration coverage** across prediction, validation, league
intelligence, UI, security, and onboarding. Remaining thin spots (documented): per-engine
unit tests for legacy V1 engines (planned to be added as they are touched during the
post-GW1 refactors); legacy tests that share a file DB or read live config.

## 10.7 Testing roadmap

1. **CI enforcement** — the workflow (ruff → pip check → secrets scan → pytest) becomes the
   release gate once the repo is pushed and PRs flow.
2. **Statistical significance tests** for version comparison (paired t-test / bootstrap) —
   after GW3–5.
3. **Per-engine unit tests** as engines are refactored (behaviour-preserving + tests).
4. **AppTest UI regressions** for remaining page migrations onto the design system
   (onboarding + gated pages already covered).
5. **Hermeticize legacy tests** (config fixtures, in-memory DBs).
6. **PostgreSQL + container smoke tests** when hosting is chosen.

---

# 11. Public Launch Preparation

**Contributed by:** Platform Engineer (with Security Manager and UX Engineer)

## 11.1 What has already been completed

| Readiness item | Status |
|---|---|
| Multi-user identity | ✅ Onboarding + per-session Team Context; no default team; no personal data stored/logged |
| Validation & gating | ✅ `require_team()` on personalized pages; public browse pages stay open |
| Admin write protection | ✅ `ADMIN_TOKEN` gate (optional; constant-time compare) |
| Audit trail | ✅ Append-only `audit_log` (ingest/validate/refresh/persist) |
| Backup & recovery | ✅ `scripts/backup_db.py` (WAL-consistent, retention, offsite) + manual procedures documented |
| CI/CD | ✅ Workflow ready (lint, pip check, secrets scan, tests) — activate on push/PR |
| Dependency security | ✅ Pinned exact versions + `pip-audit` |
| Logging | ✅ Configured (`LOG_LEVEL`, `LOG_FILE`); redaction of team IDs |
| Documentation | ✅ `docs/deployment.md`, `docs/operations.md`, `docs/configuration.md`, `docs/onboarding.md` |
| Secrets management | ✅ None in source; `.streamlit/secrets.toml` path documented; `.env.example` authoritative |
| License | ✅ MIT |

## 11.2 What remains before production

| Item | Notes |
|---|---|
| **Hosting decision + deployment** | Dockerfile/compose documented; needs a host, persistent volume for `data/`, TLS termination |
| **Database for concurrency** | SQLite is single-writer; migrate to PostgreSQL for multi-user writes (Alembic-ready) |
| **Monitoring** | External uptime check on `/_stcore/health`; log aggregation + rotation |
| **GW1 validation checkpoint** | Confirm `event_points` per-gameweek with real data; run first full validation cycle |
| **Performance under load** | `fetch_all_picks()` (38 sequential calls); boot-time API burst on cold start |
| **Auth decision** | Team IDs are public data today; optional login via the Team Context seam |
| **Git hygiene** | Commit Phase 2 + onboarding work; push to GitHub; enable CI; add `gitleaks` |
| **Domain/availability** | `mannysfplhouse.com` referenced in onboarding docs as the target public URL |

## 11.3 Hosting roadmap

1. **Containerise** — Python 3.12 image, pinned deps, persistent volume at `data/`,
   migrations as a one-time container step (`alembic upgrade head`), expose port 8501
   behind a reverse proxy terminating TLS.
2. **Choose platform** — Streamlit Community Cloud (simplest; secrets via
   `.streamlit/secrets.toml`) or self-hosted (Docker on a VPS).
3. **Migrate to PostgreSQL** when concurrent multi-user traffic demands it (URL + volume
   change; schema is Alembic-managed).
4. **CI/CD** — lint + tests + secrets scan on every PR; deploy on merge to `main`.

## 11.4 Monitoring & operational readiness

- Health checks: `/_stcore/health` (returns `ok`); external uptime monitor recommended.
- Log monitoring: `LOG_LEVEL=INFO` minimum; `DEBUG` while investigating; ship rotated logs
  when hosted.
- Audit log: watch *Recent Activity* on Model Analytics for write actions.
- Backup schedule: cron `0 3 * * *` `scripts/backup_db.py --keep 14 [--offsite-dir …]`.
- Release checklist: the 12-step pre-release/deploy/post-release checklist in
  `docs/operations.md` is the canonical gate.

## 11.5 The UX story of going public

The product shifted from a personal tool to a public application along a clear arc:

1. **Personal** — hardcoded `TEAM_ID=472930`; one user; about page confessed "a personal
   project by a beginner."
2. **URL-parameter bridge** — `?team_id=` let visitors select a team but still defaulted to
   Manny's and trusted the URL.
3. **Public onboarding** — validated, session-scoped identity; help expander explaining how
   to find a Team ID; trust footer ("No account, no ads, no personal data stored"); Change
   Team in the sidebar; the app never shows Manny's team to anyone who hasn't asked for it.

Remaining UX roadmap toward launch: migrate pages 8, 5, 1–4, 7 onto the design system +
Trust Layer; a **"This Week"** briefing (squad fixtures + captain with projected points and
reasoning + chips + deadline countdown); explainability on every score; player detail view;
decision-log "receipts" (how accurate was our advice?); guided validation wizard on page 7;
and accessibility fixes (label visible filters, text+colour risk semantics).

---

# 12. Lessons Learned

**Contributed by:** all disciplines (synthesized by Technical Writer)

## 12.1 What worked well

1. **Audit-first.** Three independent audits (security, deployment, validation) produced
   prioritized, effort-estimated work plans that the team executed almost verbatim. The
   project spent a small amount of effort on assessment and saved far more on misdirection.
2. **Behaviour-preserving phases.** Phase 1 changed zero prediction logic and still moved
   the project from "undeployable" to "deployable with moderate risk." Isolating
   infrastructure from model work de-risked everything.
3. **The prediction freeze.** Forbidding model changes until GW1 evidence kept the platform
   honest and prevented tuning-to-synthetic-data.
4. **Shadow/control + append-only ledger.** Keeping V1/V2 alive as validated control models
   turned "replace the model" into "promote a model under measurement." Every production
   claim is auditable.
5. **Config-driven everything.** Weights, model selection, API behaviour, logging — all
   versioned and switchable without code changes. `production_v1.yaml` means promoting V3
   was a config bump.
6. **Test invariants.** Weights-sum-to-1, schema parity, migration single-head, pinned CSS
   block — cheap permanent guards that catch whole classes of regressions.
7. **Honest documentation.** The self-audit explicitly downplayed its own confidence
   ("no amount of synthetic testing can substitute for real data") — that honesty
   structured the post-GW1 plan.

## 12.2 Mistakes made

1. **Built a lot without version control.** The pre-audit codebase was a large, unreviewable
   artifact with no rollback. Git should have been the first commit, literally.
2. **The zero-assertion test suite.** A suite that passes without asserting anything was
   worse than no suite — it manufactured confidence. The most expensive bug in the project
   was the belief that things worked.
3. **Silent degradation.** The SSL `verify=False` fallback and the flat-3.0 fixture
   fallback both "helped" by hiding failures — and both produced plausible-but-wrong
   output. The "zero silent failures" rule came directly from these.
4. **Splitting one responsibility across files.** Minutes projection existed in three
   places; confidence variance in two; fixture features in two. Every duplicate is a
   future divergence.
5. **Column-name ambiguity** (`id` vs `player_id`) caused silent data corruption. Naming
   conventions are data-integrity controls, not style.
6. **Intermediate state shipped** (URL-param team selection) before the real solution
   (validated session onboarding). It worked as a bridge but defaulted to Manny's team —
   a privacy hazard if it had reached public hosting.

## 12.3 Architectural decisions & trade-offs

| Decision | Trade-off accepted |
|---|---|
| Append-only ledger over mutable store | Storage growth + query complexity in exchange for reproducibility and auditability |
| Human-in-the-loop validation over automatic learning | Slower improvement loop in exchange for no self-inflicted model harm (and no false-confidence automation) |
| SQLite now, PostgreSQL later | Single-writer ceiling today in exchange for zero-ops complexity; Alembic keeps the door open |
| Streamlit for everything (temporarily) | Rerun-model latency and no client-side state in exchange for a single Python codebase; design-system layering preserves a REST/React migration path |
| Keep V1/V2 as shadow models | Ongoing compute + dual code paths in exchange for a control group and auditable claims |
| Team ID as runtime state (no default) | Slightly more onboarding friction in exchange for privacy and multi-user correctness |
| Rule-based error classifier | Rigid until tuned in exchange for simple, explainable, testable rules |

## 12.4 How engineering philosophy evolved

The philosophy moved from *"make it work for me"* to *"make claims I can defend."* In
practical terms:

- From **"it didn't crash"** to **"it is asserted, measured, and reproducible."**
- From **"silently keep going"** to **"fail loudly, never degrade."**
- From **"replace the old thing"** to **"run it in parallel until the evidence says."**
- From **"one user, one config"** to **"runtime state is not configuration, and no
  personal data is the default."**
- From **"build features"** to **"build the machinery that tells you whether the features
  work"** — the Validation Platform, the evidence ladder, and the Trust Layer are all
  expressions of the same idea.

---

# 13. Future Roadmap

**Contributed by:** Platform Engineer (immediate/short-term), Data + ML (mid-season),
Security + UX + QA (cross-cutting)

## 13.1 Immediate work (pre-GW1 / current sprint)

1. **Commit & push** the Phase 2 + onboarding work; enable CI on the GitHub remote; add
   `gitleaks`.
2. **Run the V2/V3 pipeline with real fixtures** before the GW1 deadline (30 minutes) and
   confirm reasonable projections (explicitly requested in the validation self-audit).
3. **Post-GW1 5-minute checkpoint**: confirm `event_points` matches real GW scores.
4. **Validate onboarding under a real visitor session** (multi-user smoke) and confirm the
   audit log captures write actions with team attribution.
5. **Finalize hosting decision** (Streamlit Cloud vs self-hosted Docker) and stand up
   `/_stcore/health` monitoring.

## 13.2 Short-term roadmap (GW1–GW5)

1. **First full validation cycle** on real actuals; review scatter, CI80 coverage, per-model
   MAE. Do **not** change config unless MAE is outside 2–6 points.
2. **Statistical significance** on version comparison (paired t-test / bootstrap) once ≥3
   gameweeks exist.
3. **UX**: migrate pages 8 and 5 onto the design system (also fixes the page-5 fixture
   slider bounds bug); ship "This Week" briefing on the Assistant Manager.
4. **League Intelligence Phase 2**: CommunityStatsProvider with live effective-ownership /
   top-10k data.
5. **Persist data-freshness** timestamp in the DB (TD-8); add `db_session()` context manager.
6. **Performance pass** on `iterrows()` hot loops (TD-5) with before/after runtime
   measurement.

## 13.3 Mid-season roadmap (GW5–GW15)

1. **ML consolidation** — V1 engine retirement into V3-driven paths (TD-1) once V2>V1 is
   evidenced; single uncertainty source (TD-3); Feature Store de-duplication (TD-2);
   config-driven player rating (TD-4).
2. **Error classifier tuning** to real error distributions; consolidate duplicate metric
   computation (one source of truth).
3. **League Intelligence Phases 3–5** — mini-league data pipeline, rival tracking
   persistence, live EO calibration.
4. **Unique constraints + indexes** migration once real ingestion confirms no duplicates.
5. **Audit-log surfacing**: operational dashboard views (who did what, when).
6. **Hosting hardening**: PostgreSQL migration readiness, monitoring dashboards, rate-limit
   and caching strategy for the FPL API surface.

## 13.4 Long-term roadmap (GW15+ / offseason)

1. **League Intelligence Phase 6–7** — differential weight calibration against actuals;
   Game Theory Engine (`game_theory.enabled: true`).
2. **Authentication** — persistent user profiles via the Team Context seam.
3. **REST/JSON layer** over services (the documented prerequisite for a dedicated frontend)
   for high-intent decision surfaces.
4. **Reproducible, automated config-change policy** — bounded automatic weight shifts with
   human oversight for risky changes.
5. **PostgreSQL in production**; background jobs for pipeline/league data; scheduled
   backups with offsite copies.
6. **Model V4+ research** — see 13.5.

## 13.5 Vision for Version 4+

V4 will not be a re-write; it will be the payoff of the validation machinery. Candidates,
each gated by evidence from the validation platform:

- **Position-aware calibration** — per-position error models feeding a single, unified
  uncertainty engine (replacing TD-3 duplication).
- **Learned minutes model** — replace the blended start-probability heuristic with a
  model trained on observed starts/substitutions once enough per-GW data accumulates.
- **Expected value of a transfer/league position** — the Game Theory Engine
  (`ExpectedLeaguePositionGain`) making recommendations in league-position terms, not raw
  points.
- **Live EO-aware projections** — feed post-deadline effective ownership back into
  captaincy hedging through League Intelligence (never into objective projections).
- **Optional automatic micro-tuning** of safe parameters under the evidence ladder
  (e.g. bounded weight drift on 3 consecutive gameweeks of >5% MAE improvement).

The constant across V4 ideas: **nothing is adopted because it looks better; everything is
adopted because the validation platform says it is better with enough gameweeks to know.**

---

# 14. Current State Assessment

**Contributed by:** all disciplines (synthesized by Technical Writer)

## 14.1 Architecture

Layered, config-driven, multi-model, multi-user Streamlit application. Pages sit on
services/engines; features are centralized in the Feature Store; predictions flow through
`production_predictor` (V3 primary + V2 shadow) into an append-only ledger; League
Intelligence layers context on top read-only; Team Context makes identity per-session. The
design system enforces the presenter boundary. **Maturity:** strong, with documented debt
(TD-1..9, page-session boilerplate).

## 14.2 Prediction engines

Three generations coexist deliberately. **V3 (Expected Points)** is production: xPts/90
from xGI/CS/bonus/saves/cards/set-pieces × expected minutes (start prob × minutes-if-starting
× (1 − sub risk)), with heteroscedastic 80%/95% CIs and full explainability. **V2** (7-step
pipeline) is the shadow/control. **V1** (value-score layer) is the fallback. Comparison and
evidence ladder live in `comparison_reports.py` + page 8.

## 14.3 Feature Store

Single source of truth for derived per-player features (minutes, xGI, fixtures, market,
regression, set pieces, availability, trends), consumed through accessors. Known
divergence debt (TD-2: engines recomputing fixture features) is documented and scheduled
for de-duplication after GW1.

## 14.4 Validation Platform

Fully implemented and integration-tested: append-only `validation_metrics` +
`engine_accuracy`, rule-based error classifier (7 rules), version comparison, weekly
report, evidence ladder (weak→statistically_significant). **Awaiting its first real
actuals** — MAE and CI calibration are unproven until GW1.

## 14.5 League Intelligence

Foundation shipped: EO engine, config-driven differential scorer, mini-league analyzer,
rival tracker, provider protocols, game-theory interfaces (disabled). Integrated into
`run_assistant`. Phases 2–7 (live providers, persistence, calibration, game theory, UI)
are the roadmap.

## 14.6 Testing

**162 passed**, assertion-based, invariants guarded, ruff clean. Coverage spans pipeline,
engines, validation, league intelligence, UI/design system, security (admin gate, audit
log, backups), migrations, and onboarding. Gaps documented: legacy V1 engine unit tests,
hermeticity of some legacy tests.

## 14.7 Security

Posture is fundamentally sound: no secrets in source, TLS verification on by default with
no silent downgrade, admin-gated writes (optional token), append-only audit log, secrets
scan + dependency scan in CI, escaping enforced at the UI presenter boundary, log
redaction of team IDs, owner-scoped DB file. Remaining: auth (future seam ready), log
aggregation/monitoring when hosted, PostgreSQL for concurrency.

## 14.8 Outstanding engineering items & technical debt

| ID | Item | Owner | Blocked on |
|---|---|---|---|
| TD-1 | Four V1 engines still active (fallback/parallel) | ML | GW1+ evidence (V2>V1) before retirement |
| TD-2 | Fixture features duplicated (Feature Store vs engine) | ML | Post-GW1 validation before de-dup |
| TD-3 | CI/variance weights duplicated across engines | ML | Behaviour-preserving refactor, then validate |
| TD-4 | `compute_player_rating` hardcodes rating split | ML | Config-driven fix (smallest win) |
| TD-5 | `iterrows()` hot loops across engines | ML | Measure runtime, then vectorize |
| TD-6 | Validation engine coupled to DB/CRUD | ML | Refactor with dependency injection |
| TD-7 | Missing FK indexes / unique constraints | Data | Migration + real-ingestion validation |
| TD-8 | Staleness tracked in-process | Platform | Persist last-refresh in DB |
| TD-9 | Silent fixture fallback (flat 3.0/50.0) | ML | Fail loudly with warning |
| — | **Latent bug: `fixture_map` undefined** in `services/assistant_manager/engine.py` (~line 170) | ML | `build_feature_store()` call NameErrors → V3 never persists via `run_assistant`; fix by building `fixture_map` before the production-prediction block (annotated `noqa: F821` + TODO) |
| — | **Latent bug: undefined names** in `services/assistant_manager/transfer_engine.py` (~108–156) — `transfers_in`, `transfers_out`, `selected`, `_build_reasoning` don't exist | ML | Transfer loop NameErrors; annotate intended derivations in the TODO |
| — | Page 5 fixture-slider bounds bug (`min_value=5, value=(1,10)`) raises at runtime | UX | Fix during page-5 design-system migration |
| — | `fetch_all_picks()` up to 38 sequential calls | Data | Parallelize/cache; monitor 429s |
| — | No `db_session()` context manager (pages call `get_session()` directly) | Data | Consolidate |
| — | No statistical significance in version comparison | ML | GW3–5 |
| — | JSON-in-Text columns; missing `__init__.py` in some packages; "differentails" typo | Data/Platform | Low-priority cleanup |

## 14.9 Operational maturity

| Capability | Maturity |
|---|---|
| Version control | ✅ GitHub, `main`, linear history via squash/rebase |
| CI | ✅ Workflow ready; pending push + PR enablement |
| Migrations | ✅ Alembic (baseline + audit-log), rollback documented |
| Backups | ✅ Scripted, WAL-consistent, retention + offsite |
| Logging | ✅ Configured + redaction; aggregation pending |
| Monitoring | ⚠️ Health endpoint ready; external uptime + log shipping pending |
| Secrets | ✅ None in source; secrets.toml path documented; CI scan |
| Docs | ✅ 14-file package incl. onboarding, ops, deployment |
| Release process | ✅ 12-step checklist in `docs/operations.md` |

**Overall maturity verdict:** *ready to validate, ready to deploy with monitoring; not yet
proven on real data.* The honest summary remains the self-audit's: the plumbing is
verified, the schema is sound, and the first real gameweek is the missing experiment.

---

# 15. Appendices

**Contributed by:** Technical Writer (diagrams from all disciplines)

## Appendix A — Major architectural diagrams

### A.1 Initial architecture

```
Streamlit pages → services → engines (+Feature Store) → database(SQLite, create_all)
                                                                        ↓
                                                    FPL API (no retries, silent SSL downgrade)
```

### A.2 Current architecture (see Chapter 4.2)

Layered: Streamlit + design system → Team Context / services → Feature Store → engines →
database (Alembic, WAL, backups) → FPL API (retry/backoff/TLS/redaction). Two model
generations run in parallel (V3 primary, V2 shadow), both persisted to the append-only
ledger; League Intelligence reads projections only; audit log records operations.

### A.3 Future architecture (see Chapter 4.4)

Browsers/future frontend → REST/JSON layer → services (with auth via Team Context seam) →
PostgreSQL → FPL API + community EO providers + monitoring.

## Appendix B — Prediction pipeline

```
FPL bootstrap → data_loader → scoring → Feature Store
                                            │
                     production_predictor.run_production_predictions(store, gw, persist)
                        ├── PRIMARY  expected_points_v1 (V3)
                        │     expected_points_engine  → xPts_per_90
                        │     expected_minutes_engine → expected_minutes
                        │     expected_projection_engine → xPts = xPts/90 × min/90 (+ CIs)
                        └── SHADOW   projection_v2 (V2 7-step pipeline)
                                      minutes → projection → regression → bookmaker →
                                      confidence → snapshot → opportunity
                        both → persist_expected_version / insert_projections_bulk
                                 → prediction_versions (config_hash, weights_snapshot)
```

## Appendix C — League Intelligence pipeline

```
FPL API ─► ingestion ─► Feature Store ─► Prediction Layer (V3+V2, objective)
                                              │ (read-only projections)
                                              ▼
   run_league_intelligence(store, projections, team_id, gw, providers=…)
        ├─ effective_ownership  selected%+captained%+tc%
        ├─ differential         min-max 7 features × config weights (xpts unchanged)
        ├─ mini_league          overlap, captain/ownership overlap, Jaccard, threats
        ├─ rivals               squad diff, captain compare, differentials, transfer div.
        └─ game_theory          interface (disabled) → ExpectedLeaguePositionGain
                                              │
                                              ▼
        typed StrategicRecommendations (xpts + strategy_score) → run_assistant
```

## Appendix D — Feature Store pipeline

```
players_df + team_name_map + fixture_map + config_hash
        → build_feature_store()
           ├─ scoring.normalise (add_derived_columns, value_score)
           ├─ minutes features     starts_rate, minutes_season, reliability, rotation
           ├─ xGI features         xg/xa/xgi per 90, form, xGI score
           ├─ fixture features     difficulty score, avg 1/3/6 GW, swing, home/easy/hard
           ├─ market features      net transfers, transfer velocity, ownership tier,
           │                       price direction, value_form/season
           ├─ regression features  over/underperformance flags
           ├─ set-piece features   penalty/fk/corner taker flags
           └─ availability features status, chance of playing
        → store.df + accessors (single source of truth for engines)
```

## Appendix E — Validation workflow

```
post-GW: result_ingestion_service (mark_actuals)
   → validate_version(session, version_id, gameweek_id)
        MAE, RMSE, bias, median_ae, CI80/95 coverage, width, per-position breakdown
        → validation_metrics (append-only) + engine_accuracy
   → error_classifier (7 rules → ErrorClassification rows)
   → compare_versions(baseline, treatment)  [+ significance test (future)]
   → learning_service → Weekly Report + Candidate Improvements (human review)
   → evidence_status(n_gameweeks) → weak/needs_more_data/moderate/strong/stat_sig
```

## Appendix F — Deployment & backup workflow

```
git pull → uv pip install -r requirements.txt → python scripts/backup_db.py --keep 14
   → alembic upgrade head → streamlit run About.py --server.headless true
   → health check (/_stcore/health) → confirm first data load → monitor logs
   → record release (git tag, config hash)
backup: sqlite3 online backup → data/backups/moneyball-<stamp>.db → prune --keep → offsite copy
```

## Appendix G — Session architecture (Team Context)

```
Anonymous Visitor
   → onboarding (components/onboarding.py)
   → validate_team_id(raw)  [sanitize digits 1..99,999,999; fpl_get /entry/<id>/;
                             10s timeout, 1 retry; never raises]
   → set_current_team_id(id, team_name) → session_state.team_id
   → require_team() gates pages 1/4/6/8 (+ About host)
   → every service reads get_current_team_id() (int | None; no default)
   → Change Team → clear_current_team_id() → switch_page(About) → re-onboard
   → future: login system → same provider, persistent profile
   [no persistence, no logging of team ids (api_client redacts /entry/<id>)]
```

## Appendix H — Decision records (abridged)

| # | Decision | Date | Rationale |
|---|---|---|---|
| DR-1 | Keep V1/V2 as shadow/control models; never delete | 08-05 | Control group + auditable production claims |
| DR-2 | Promote V3 via config (`production_v1.yaml`), not code | 08-05 | Model selection is config; revert = YAML bump |
| DR-3 | Append-only ledger; idempotent version tags | earlier | Forecasts are experiments; reproducibility |
| DR-4 | Human-in-the-loop learning (no automatic retraining) | earlier | False confidence is the biggest risk; evidence ladder |
| DR-5 | Team ID is runtime state, not configuration; no default | 08-06 | Privacy + multi-user correctness; login seam |
| DR-6 | TLS insecure fallback opt-in, default off; refuse non-HTTPS | 08-03 | Remove silent MITM class permanently |
| DR-7 | Alembic baseline; `create_all()` bootstrap only | 08-02 | Schema evolution without data loss |
| DR-8 | Exact version pins + dev/prod split | 08-02 | Reproducible installs |
| DR-9 | SQLite now, PostgreSQL at public scale | 08-02 | Zero-ops now; Alembic-ready migration |
| DR-10 | Presenter boundary escapes all dynamic values | 08-04 | Close stored-XSS; enable future frontend |
| DR-11 | League Intelligence never writes to the ledger; `xpts` untouched | earlier | Prediction objectivity is non-negotiable |

## Appendix I — Roadmap tables (see Chapter 13)

Immediate (GW1): commit+push, CI on, real-fixture pipeline run, GW1 checkpoint, hosting
decision.
Short (GW1–5): first real validation, significance testing, UX page 8/5 migrations, "This
Week" briefing, League Intelligence Phase 2, freshness persistence, vectorization.
Mid (GW5–15): V1 consolidation, single uncertainty source, classifier tuning, LI Phases
3–5, unique constraints, PostgreSQL readiness, monitoring.
Long (GW15+/offseason): LI Phases 6–7, auth, REST layer, automated bounded tuning, V4
research.

## Appendix J — Glossary

| Term | Definition |
|---|---|
| **xPts / Expected Points** | The V3 production projection: `xPts_per_90 × (expected_minutes / 90)`. |
| **xPts_per_90** | Expected FPL points per 90 minutes from xGI, clean-sheet prob, bonus, saves, cards, set pieces. |
| **Expected Minutes** | `start_probability × minutes_if_starting × (1 − substitution_risk)`. |
| **xG / xA / xGI / xGC** | Expected goals / assists / goal involvements / goals conceded. |
| **CI80 / CI95** | Confidence intervals; coverage = fraction of actuals inside the interval. |
| **MAE / RMSE** | Mean absolute error / root mean squared error of projections vs actuals. |
| **Bias** | `mean(actual − projected)`; positive = systematic underprediction. |
| **Ledger** | Append-only `prediction_versions` + `projections`; every forecast is a version with a config hash. |
| **Shadow / control model** | A non-production model persisted and validated against actuals alongside the primary (V1/V2 vs V3). |
| **Evidence ladder** | weak(1) → needs_more_data(2) → moderate(3–4) → strong(5+) → statistically_significant(10+) — sample-size maturity tiers, not formal significance tests. |
| **Feature Store** | `features/store.py` — single source of truth for derived per-player features. |
| **Team Context** | `utils/team_context.py` — per-session runtime team identity (`session_state.team_id`). |
| **Effective Ownership (EO)** | selected% + captained% + triple-captained% for a player. |
| **Differential** | A player few rivals own; scored from xPts, minutes, fixtures, inverse ownership, transfers, price, rotation risk. |
| **Trust Layer** | Mandatory recommendation metadata (evidence, confidence, reasoning, agreement, accuracy, data quality). |
| **Prediction freeze** | No projection/weight/validation changes until GW1+ evidence. |
| **Zero silent failures** | Fail loudly with a log; never silently degrade (e.g. TLS, fixture fallbacks). |
| **Shadow validation** | Running V3 alongside V2 pre/post-GW and comparing (alignment + ledger A/B). |
| **xGI** | Expected goal involvement (xG + xA). |
| **BPS** | FPL's Bonus Points System; `E[bonus] = clip(bps_per_90/160, 0, 3)`. |

---

## Source map

Primary source documents referenced by this report:

- `EXECUTIVE_AUDIT_REPORT.md` (2026-07-28) — security/production audit
- `VALIDATION_PLATFORM_AUDIT_REPORT.md` (2026-07-27) — validation self-audit
- `DEPLOYMENT_READINESS_PHASE1.md` (2026-08-02) — deployment audit
- `MEDIUM_ISSUES_SENIOR_MANAGER.md`, `LOW_ISSUES_SENIOR_MANAGER.md` — audit detail
- `reports/*_phase1.md` — Phase 1 per-workstream reports
- `docs/` — architecture, deployment, configuration, database, development, operations,
  prediction, expected_points, validation, league_intelligence, design-system,
  ui-guidelines, onboarding, ux_discovery_audit, stakeholders
- `README.md`, `.env.example`, `.github/workflows/ci.yml`, `requirements*.txt`
- Git history (`git log`, 2026-07-30 → 2026-08-05) and code inventory

*Assembled 2026-08-06. This document should be updated at each phase boundary (post-GW1
validation, hosting launch, V4 research kickoff) to remain the authoritative engineering
history.*
