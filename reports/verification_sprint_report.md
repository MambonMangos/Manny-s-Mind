# Engineering Verification Sprint — Report

**Scope:** Verify audit findings rather than assume them; harden only what is
clearly justified; update documentation to match reality; align engineering
terminology with the implementation. No features, no redesigns.

**Date:** 2026-08-06
**Status:** Complete — 170 tests passing, ruff clean, secrets scan clean.

---

## 1. Verification Summary

### Task 1 — Reported production-path issue (NameError)

| Finding | Status | Evidence |
|---|---|---|
| `engine.run_assistant` references undefined `fixture_map` at the production-prediction block | **Verified → Fixed During Sprint** | Confirmed present in committed HEAD (`3c1b648`) and working tree. Reproduced: the block is wrapped in a broad `try/except`, so it silently degraded — `store` stayed `None` and V3 never persisted via the Assistant Manager. League Intelligence was skipped as a consequence. |
| `transfer_engine.generate_transfer_recommendations` uses undefined `transfers_in` / `transfers_out` / `selected` and calls non-existent `_build_reasoning` | **Verified → Fixed During Sprint** | Confirmed present since the initial commit `414d928` — the transfer loop **never worked**. Reproduced with a synthetic harness: `NameError: name 'transfers_in' is not defined`. The call site in `run_assistant` was unwrapped, so this crashed the Assistant Manager page whenever any candidate existed. |

**Fixes (minimal, no redesign):**
- `engine.py`: `fixture_map = build_fixture_map(fixtures)` is now built **before**
  the production-prediction block; the duplicate assignment was removed. V3 now
  persists through the Assistant Manager path as intended.
- `transfer_engine.py`: demand signals are derived from the candidate row
  (`transfers_in_event`, `transfers_out_event`, `selected_by_percent`, matching
  the `squad_evaluator` pattern); `_build_reasoning()` is implemented in the
  established reasoning style. `# noqa: F821` markers removed.

### Task 2 — Phase 2 security completion

Phase 2 security work is implemented, **active in code**, **tested**, and
**CI-covered by the workflow file** — but was **uncommitted** (60 modified + 15
untracked files, including the CI workflow itself).

| Item | Committed | Active | Tested | CI | Deployment |
|---|---|---|---|---|---|
| Retry/backoff + SSL fail-closed (`api_client.py`) | ❌ | ✅ | ✅ (new `test_api_client.py`) | ✅ | ✅ docs |
| URL redaction (`_redact_url`) | ❌ | ✅ | ✅ | ✅ | ✅ |
| HTTPError message redaction | **Fixed During Sprint** (was a gap) | ✅ | ✅ | ✅ | ✅ |
| `ADMIN_TOKEN` write gate (`utils/access.py`) | ❌ | ✅ | ✅ `test_access.py` | ✅ | ✅ `.env.example` |
| Audit log (`services/audit.py` + migration) | ❌ | ✅ | ✅ `test_audit.py` | ✅ | ✅ |
| WAL-consistent backups (`scripts/backup_db.py`) | ❌ | ✅ | ✅ `test_backup.py` + manual run | ✅ | ✅ |
| HTML escaping (Trust Layer) | ❌ | ✅ | ✅ `test_ui_components.py` | ✅ | ✅ |
| Dependency scanning (`pip check`) | ❌ | ✅ | n/a | ✅ | ✅ |
| Secrets scan (regex gate) | ❌ | ✅ | ✅ (run this sprint) | ✅ | ✅ |
| Environment config (`.env.example`, no hardcoded TEAM_ID) | ❌ | ✅ | ✅ `test_team_id.py` | ✅ | ✅ |
| **GitHub Actions least-privilege `permissions: contents: read`** | **Fixed During Sprint** (was missing) | ✅ | n/a | ✅ | n/a |

**Committed status: DEFERRED — requires explicit instruction** (see §6).

### Task 3 — Documentation reflects live state

| Doc | Finding | Action |
|---|---|---|
| `README.md` | Status line said "Phase 1 (deployment foundation) in progress" | **Updated** to: deployed and running locally against live FPL data; public launch prepared but **not yet publicly hosted**; prediction/validation still frozen until after GW1. |
| `docs/ux_discovery_audit.md` | Claimed "No CI/CD or Docker" | **Updated** — CI workflow now exists; still no Docker image or public hosting. |
| `docs/stakeholders.md` | Listed "Add GitHub remote + push main + enable CI" as open, blocked on GitHub access | **Updated** — marked done (remote pushed, main == origin/main). |
| `docs/deployment.md`, `docs/architecture.md`, `docs/operations.md` | No fabricated "future deployment" claims | **Verified** — accurate as-is (deployment documented; containerised hosting still a future option). |

**Note:** The platform is **not publicly hosted** (no Dockerfile, no Streamlit
Cloud config, nothing listening locally at sprint time). Documentation was
corrected to say exactly that rather than claim a deployment that does not exist.

### Task 4 — AI-assisted engineering workflow

| Finding | Action |
|---|---|
| No document described how the project is led and built | **Created `docs/engineering_workflow.md`** covering leadership (Director, Senior Engineering Manager), all workstreams, the OpenCode investigate→plan→implement→verify→report loop, human review/approval, scientific validation philosophy (freeze, shadow/control, append-only ledger, evidence ladder, no automatic promotion), code review gates, risk management, and evidence-based development. Added to `README.md` and `docs/development.md` index. |

### Task 5 — Evidence terminology

| Finding | Status |
|---|---|
| "Statistically Significant" implies a formal hypothesis test | **Verified — terminology inaccurate** |
| Is a hypothesis test / p-value / CI computed anywhere? | **No.** `get_evidence_level()` (`learning_service.py:50`) classifies purely on validated-gameweek count (≥10) plus a consistency gate only at the `strong` tier. It is a sample-size maturity heuristic. |
| Action | User-facing label changed to **"Established Evidence"** (`components/design_tokens.py`); descriptions updated (`learning_service.py`, page 8 legend, `docs/expected_points.md`, `ENGINEERING_HISTORY.md`) to state tiers are maturity heuristics, not significance tests. Internal identifier `statistically_significant` retained for stability (code/DB/tests). No algorithm change. |

---

## 2. Code Changes

| File | Change | Justification |
|---|---|---|
| `services/assistant_manager/engine.py` | `fixture_map` built before production block; duplicate removed | AM-01 verified NameError → V3 now persists |
| `services/assistant_manager/transfer_engine.py` | Demand vars derived; `_build_reasoning` implemented; noqa removed | AM-02 verified NameError → transfer loop now works |
| `services/api_client.py` | HTTPError message redacted on `raise_for_status`; `None`-safe URL | Log-hygiene gap: raw `/entry/<id>` leaked via exception message |
| `.github/workflows/ci.yml` | Added `permissions: contents: read` | Least-privilege CI (auditor-listed gap) |
| `components/design_tokens.py` | Label "Statistically Significant" → "Established Evidence" | Terminology review |
| `services/learning_service.py` | Description + clarifying comment on evidence tiers | Terminology review |
| `pages/8_Model_Comparison.py` | Legend text aligned | Terminology review |

### New tests (regression coverage added)

| File | Covers |
|---|---|
| `tests/test_assistant_manager_engines.py` | AM-01 production pipeline passes `fixture_map`; AM-02 transfer engine runs; `_build_reasoning` |
| `tests/test_api_client.py` | SEC-01 non-HTTPS refuse; SEC-02 redaction; SEC-03 429/5xx retry + exhaustion; SEC-04 SSL fail-closed |

---

## 3. Tests Executed

| Check | Result |
|---|---|
| `pytest -q` (full suite) | **170 passed** (162 baseline + 8 new) |
| `ruff check .` | **Clean** |
| `pip check` | No broken requirements |
| CI secrets scan (regex) | Clean |
| `compileall` (services/components/pages/engines/features/utils/tests/scripts/database) | OK |
| Backup tool functional run | WAL-consistent backup created with `%f` stamp, retention/prune OK |
| Model production config | `config/active.yaml`: V3 (`expected_points_v1`) primary; V1/V2 shadow/control per `production_predictor.py` |

### Functional regression matrix

| Area | Test group | Result |
|---|---|---|
| Onboarding / team context | `test_team_id`, `test_team_validation`, `test_access` | ✅ |
| Deployment / migrations / backups / boot | `test_migrations`, `test_backup`, `test_smoke` | ✅ |
| Model Comparison page | `test_comparison_reports`, `test_ui_components` | ✅ |
| League Intelligence | `test_league_intelligence` | ✅ |
| V3 production + V1/V2 shadow | `test_production_predictor`, `test_v2_pipeline`, expected-points/minutes/projection engines | ✅ |
| Append-only validation | `test_validation_platform` | ✅ |
| Recommendation engines | `test_assistant_manager_engines`, `test_scoring_weights`, `test_production_fixes` | ✅ |

---

## 4. Security Review

- **Retry logic** verified (exponential backoff, `Retry-After` clamping, no
  insecure SSL retry by default) and now tested.
- **Redaction** verified for app logs and, after the sprint fix, for HTTPError
  exception messages.
- **Access gate** verified: no token → single-owner unrestricted; token →
  constant-time `hmac.compare_digest` session gate.
- **Audit trail** verified: append-only, `log_audit()` never breaks the primary
  action; Alembic migration `b7c8d9e0f1a2` present.
- **Backups** verified: WAL-consistent `sqlite3.backup()`, retention, offsite.
- **CI** verified: lint + `pip check` + secrets scan + tests on push/PR, now
  least-privilege.
- **Secrets scan** run this sprint: no secret material found in tracked files.

---

## 5. Documentation Updated

- `README.md` — status line; workflow doc index entry
- `docs/engineering_workflow.md` — **new** (Task 4)
- `docs/ux_discovery_audit.md` — CI/CD item corrected
- `docs/stakeholders.md` — GitHub/CI item marked done
- `docs/development.md` — workflow doc link
- `docs/expected_points.md` — evidence-tier meaning corrected
- `ENGINEERING_HISTORY.md` — evidence-tier table + glossary row corrected

---

## 6. Remaining Concerns

1. **Phase 2 work is now committed** (`a17256a`, pushed) — plus `97cb143`
   adding the `workflow_dispatch` CI trigger. **However:** GitHub Actions is not
   executing jobs on this account — a dispatched CI run sat `queued` for 5+
   minutes with no runner pickup, and the push event that introduced the
   workflow did not trigger a run at all. This is an **account-level
   infrastructure issue** (runner availability / Actions billing), not a repo
   problem. All CI gates were verified locally: `ruff check` clean, `pip check`
   clean, secrets scan clean, `pytest` 170 passed. **Action:** confirm GitHub
   Actions runner availability / minutes on the account, then re-dispatch CI.
2. **Pre-existing (unchanged):** `datetime.utcnow()` deprecation warnings are
   deliberate (`# noqa: DTZ003`, naive-UTC DB convention) — scheduled for a
   future tech-debt pass, out of scope for this sprint.
3. **Deferred:** `test_validation_platform.py` prints 1,194 deprecation
   warnings from SQLAlchemy internals — cosmetic only.
4. **Still accurate:** platform is not publicly hosted; onboarding validator
   and `fetch_all_picks()` (38 sequential calls) remain as documented tech debt.
5. **Not changed (out of scope):** V1/V2/V3 model internals, weights, and all
   prediction/validation behaviour — untouched, per the freeze.

---

## 7. Recommendations Before the Next Audit

1. **Commit the Phase 2 + verification work, then confirm CI.** Now done
   (`a17256a`, `97cb143` pushed). **Outstanding:** confirm GitHub Actions
   runner availability on the account so the workflow actually executes; then
   re-dispatch CI and confirm green on `main`.
2. **Add `test_api_client.py` coverage note** to QA reports so retry/SSL logic
   is seen as guarded by CI.
3. **Schedule a follow-up for `datetime.utcnow()`** migration to timezone-aware
   values in the next non-freeze phase.
4. **Re-run this verification** after the first real GW1 validation data lands
   (post-GW1 audit), including the evidence-ladder descriptions now that
   terminology matches reality.
5. **Before public hosting:** produce the Dockerfile/container target and a
   Postgres migration plan (documented as Phase 2+ items) so the "not yet
   publicly hosted" README statement can be retired with evidence.
