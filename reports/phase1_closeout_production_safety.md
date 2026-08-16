# Phase 1 Closeout & Production-Safety Verification Report

**Role:** ML / Analytics Engineer · **Mode:** read-only verification (no application code, schema, config, or engine modified during this closeout) · **Date:** 2026-08-13
**Scope:** Independent verification of the Phase 1 "Real FPL Starts Data Foundation" workstream, the test-suite isolation fix, and production-safety posture. Every claim below was re-derived from the live database or live FPL API during this session; "Reported" items that could not be reproduced are flagged explicitly.

---

## 1. Verification Methodology

| Check | Method |
|---|---|
| Ingestion / schema / feature store | Direct file inspection + live DB queries (read-only `sqlite3`, `PRAGMA`) |
| V3 projection behaviour | In-memory recompute from live DB via `FeatureStore` + V3 engines (no persistence) |
| Test-suite isolation | SHA-256 + row counts of `data/moneyball.db` recorded **before and after** a full `pytest` run |
| Migration safety | Fresh temp SQLite DB: `alembic upgrade head` → `downgrade -1` → `upgrade head` (throwaway file) |
| API limitations | Live `element-summary/1/` fetch (read-only GET) |
| Model integrity | `git diff --name-only` restricted to `engines/` and `config/` |
| App boot | Streamlit headless boot + HTTP 200 `/` + `/_stcore/health` |

No destructive command was run against the real database. The only writes performed were to a throwaway DB in `/tmp`.

---

## 2. Phase 1 Acceptance Review (Part 1)

### 2.1 Real FPL starts data flows API → DB → Feature Store — VERIFIED
- `services/data_loader.py:28` — `"starts"` present in `_PLAYER_FIELDS`; `_parse_player` coerces to `int`, defaults `0`.
- `database/models.py:78` — `Player.starts = Column(Integer, default=0)` (real matches-started).
- `database/crud.py:95` — `"starts": player.starts or 0` exposed to the dataframe layer.
- `features/store.py:458-463` — fabrication removed; missing starts degrade to `0`; real values preserved.
- `features/store.py:168-198` — `minutes_per_game` capped at `90.0` (`np.minimum`); `starts_rate` computed on **real** starts; `starts` carried through as integer.

### 2.2 Database schema — VERIFIED
- Migration `alembic/versions/c4d3e2f1a5b6_add_starts_to_players.py`: `op.add_column("players", sa.Column("starts", Integer, nullable=False, server_default="0"))`, downgrade drops the column.
- Live DB: `PRAGMA table_info(players)` → `54|starts|INTEGER|1|'0'|0` (NOT NULL, default `'0'`).
- `alembic heads` == `alembic current` == `c4d3e2f1a5b6` — single linear head, DB at head.

### 2.3 Prediction engine integrity — VERIFIED
- `git diff --name-only -- engines/ config/` → **empty**. V3 engines and all config files are untouched; `expected_minutes_v1.yaml`, `expected_points_v1.yaml`, `production_v1.yaml` unmodified.

---

## 3. Data Validation (Part 2) — all claims reproduced

| Claim | Reproduced |
|---|---|
| `players`=584, `teams`=20, `gameweeks`=38, DB at migration head | ✓ |
| `starts > 0` | ✓ **365** |
| `starts = 0` | ✓ 219 |
| sub-only (`starts=0` AND `minutes>0`) | ✓ **35** |
| V3 differentiates starters vs sub-only | ✓ Dubravka 35 starts → exp_min **64.1** (start_prob 0.95, dq good); Konsa 34 → **63.2**; Sosa 0 → **23.1** (0.35); Kusi-Asare 0 → **23.6** — exact match with report §2.2 table |
| Projections: 584, 0 NaN, 0 negatives | ✓ |
| `expected_minutes` bounds [0, 90] | ✓ min 0.0, max 66.2 |
| xPts (minute-weighted composition) 0–1.72 | ✓ min 0.0, max **1.718**; `xpts_per_90` max 3.744, 0 NaN/neg |
| `starts_rate` no longer collapses to 1.0 | ✓ max **1.44** on live data (fabricated version was ≡ 1.0) |

Fabrication-removal corroboration: `Adingra` 9 starts / 649 min, `Rigg` 11 / 758, `Estêvão` 12 / 839 — cases a minutes-derived approximation could never represent.

---

## 4. Test-Suite Isolation (Part 3) — VERIFIED empirically

- Full suite: **187 passed, 0 failed, 0 errors** (5.09 s). 2653 warnings — all pre-existing `datetime.utcnow()` deprecations, none new.
- **DB integrity guard:** SHA-256 of `data/moneyball.db` identical **before and after** the run (`84b95699…`); 584 players and `alembic_version = c4d3e2f1a5b6` unchanged.
- `ruff check .` → clean (exit 0).
- App boot: Streamlit headless HTTP 200 on `/`, `/_stcore/health` → `ok`.

Root cause of the pre-existing hazard (confirmed): `tests/test_production_predictor.py`, `tests/test_validation_platform.py`, `tests/test_comparison_reports.py`, `tests/test_expected_projection_engine.py` import the module-level engine bound to the default `DATABASE_URL` and call `drop_all`/`create_all`. Fix in place: root `conftest.py` sets `os.environ["DATABASE_URL"] = "sqlite://"` before any test module import.

---

## 5. Production-Safety Review (Part 4)

### 5.1 Residual risk assessment — REMAINING

1. **`tests/test_validation_platform.py:635-647`** — an `if __name__ == "__main__":` block deletes `instance/moneyball.db` (path relative to the tests dir) when the file is run **directly**. Not executed under `pytest`. The real DB is `data/moneyball.db`; no `instance/` directory exists. Severity: **Low** — self-consistent manual-runner, but a destructive `os.remove` in test code should be hardened (see Part 12, Finding F-1).
2. **In-memory engine is a module-level singleton** shared across the session. SQLAlchemy's in-memory `sqlite://` uses a per-thread pool; cross-thread tests could theoretically see different empty DBs. No test exercises threads; the suite is deterministic. Severity: **Low / informational**.
3. **`.env` interplay** — `utils/env.py` loads `.env` with `load_dotenv(..., override=False)`, so even a future `.env` with `DATABASE_URL` cannot clobber conftest's earlier-set value. Currently no `.env` exists. No residual risk.

### 5.2 Isolation guarantee chain (verified end-to-end)
`conftest.py` (runs before all imports) → `os.environ["DATABASE_URL"]="sqlite://"` → `database.database._DATABASE_URL = os.getenv("DATABASE_URL", default)` honours env → `create_engine("sqlite://")` (in-memory) → `reset_db()` in the four hazard files drops/creates tables **only in the in-memory DB**. CI sets no `DATABASE_URL`, so CI is protected identically. Empirically proven by the byte-identical DB hash.

---

## 6. Security Controls Review (Part 5)

| Control | Status | Evidence |
|---|---|---|
| 1. Failed-setup detection (tests + lint) | **Verified** | 187 pass, `ruff check .` clean, both re-run this session |
| 2. Peer / code review | **Not evidenced** | No reviewer recorded; Phase 1 is self-reviewed. See Part 12, Finding F-2 |
| 3. CI (push / PR / manual) | **Verified (config)** | `.github/workflows/ci.yml`: `ruff check .`, `pip check`, secrets scan (private keys, AWS `AKIA`, `ghp_`, Slack `xox`, `sk-`), `pytest -q`; triggers on push→main, PR, `workflow_dispatch`; `permissions: contents: read`. Live run status not independently confirmed (no network write allowed in this closeout) |
| 4. Launch/burn + restore | **N/A this change** | Migration is additive (`server_default='0'`); no data mutation. No backup existed at migration time (see Part 8) |
| 5. Regression / acceptance | **Verified** | 12 new data-integrity tests + 4 migration tests; V3 outputs re-derived from live DB this session |

---

## 7. Migration Safety (Part 6) — VERIFIED

On a throwaway temp SQLite DB:
- `alembic upgrade head` → success; `players.starts` present, NOT NULL; `alembic_version = c4d3e2f1a5b6`.
- `alembic downgrade -1` → success; `starts` dropped; `alembic_version = b7c8d9e0f1a2`.
- `alembic upgrade head` (re-apply) → success.

Additive, reversible, order-safe. The migration tests (`tests/test_migrations.py`) run Alembic in a subprocess against `tmp_path` DBs with an overridden `DATABASE_URL` — fully isolated. The live DB is already at head with 584 players intact.

---

## 8. SQLite / WAL (Part 7) — VERIFIED

- `PRAGMA journal_mode` → `wal` (live DB). `database/database.py` sets WAL + foreign keys on connect (`database.py:70-72`).
- `create_engine(..., connect_args={"check_same_thread": False})` (`database.py:37-40`) — required for Streamlit's threaded access.
- Single SQLite file (`data/moneyball.db` + `-wal`/`-shm`); no other `.db` files exist.

---

## 9. Backup Readiness (Part 8) — NOT OPERATIONAL (required before destructive work)

- `scripts/backup_db.py` exists and is correct: SQLite **online backup API** (WAL-consistent, not a raw file copy), `--keep` retention (default 14), optional `--offsite-dir`.
- `docs/operations.md` documents the script, retention, offsite copy, and cron line (`0 3 * * * …`).
- **However:** `data/backups/` has never been created (no backups exist), and `crontab` has no backup entry. `docs/operations.md:34` runbook checkbox remains unchecked.
- **Assessment:** tooling + docs ready; **backup execution/automation is not yet in place.** Backups must be operational before any destructive migration, schema change, or production deployment.

---

## 10. Outstanding Findings (Part 9)

### 10.1 Bench optimizer (`engines/squad_optimizer.py:412`) — UNCHANGED, classified as Phase 2 scope
- `git diff -- engines/squad_optimizer.py` → empty. Line 412 is captain selection inside the greedy squad builder — untouched.
- **Classification:** not a Phase 1 defect. Phase 1 scope was the data foundation only. A substitute-reliability/bench optimizer is designed (but not built) in `reports/substitute_reliability_workstream.md` §3.5 and explicitly parked behind Phase 2 evidence collection. **Recommended owner: Phase 2, decision layer.**

### 10.2 Per-gameweek data limitation — VERIFIED, documented, not fabricated
- Live API check (`element-summary/1/`): `history` = **0 rows** in preseason (per-GW data unavailable until GW1); `history_past` = 5 seasons including real per-season `starts`. Events C/D (unused substitute vs not in squad) are **not exposed by the public API at all**.
- Documented at `reports/substitute_reliability_workstream.md` §3.1 (event table) and §1.1. No fabricated fields introduced. ✓

### 10.3 NEW — Documentation count discrepancy (Finding F-3)
- `reports/substitute_reliability_workstream.md:25` claims "22 real players have `starts > minutes/90 + 1`".
- **Not reproducible** on the current DB: the count is **72** under the literal expression, and **41** under `starts > round(minutes/90) + 1` (128 for `>` without `+1`). The qualitative claim (starts can exceed minutes-derived starts for players subbed off early) **holds** — see §3 examples.
- **Action:** correct the count in the report; the underlying finding and the fix are unaffected.

---

## 11. Documentation Review (Part 10) — VERIFIED

`reports/substitute_reliability_workstream.md` exists and covers every required section: §1 data audit (origin, loss, verification, production-safety finding), §2 expected-minutes audit (methodology unchanged + corrected-data impact), §3 substitute/minutes design (API limits, dataset, MCRM, three-event shadow model, bench optimizer), §4 validation plan (metrics + promotion discipline), §5 production-safety report. Companion `reports/model_audit_substitute_selection.md` (12-phase audit) is present.

---

## 12. Security Manager Assessment (Part 11)

**Finding F-1 (Low):** destructive `os.remove("instance/moneyball.db")` in `tests/test_validation_platform.py` `__main__` block. Runs only when the file is executed directly; does not touch the real DB under `pytest`. **Recommendation:** guard the delete behind an explicit `--cleanup` flag or remove it.

**Finding F-2 (Medium):** no independent peer/code review recorded for Phase 1 changes (self-reviewed). **Recommendation:** obtain a second review of the 6 changed files + migration + conftest before merge; this closeout report is independent verification but is not a code review.

**Finding F-3 (Low):** non-reproducible "22 players" count in the workstream report §1.2. **Recommendation:** correct to the actual value.

**Finding F-4 (Low):** `.github/workflows/ci.yml` secrets scan covers common patterns but not all (e.g. no `DATABASE_URL`-style connection-string scan). Non-blocking.

**Security verdict: CONDITIONAL PASS** — no security defects in the shipped change; residual risks are low-severity hardening items (F-1) and process items (F-2). No secrets introduced, no new attack surface, CI least-privilege (`contents: read`).

---

## 13. IT Manager Assessment (Part 12)

**Verified good:** migration is additive + reversible (temp-DB cycle proven); DB at head; test isolation proven byte-identical; WAL + `check_same_thread=False` correct for the Streamlit/SQLite stack; backup tooling exists and is WAL-consistent.

**Blocking gap — backups not operational.** No `data/backups/` contents, no cron entry. Before any **destructive** migration or production deployment, backups must be taken and scheduled per `docs/operations.md`. For this Phase 1 change the risk was already fully realised (the pre-fix test runs had destroyed the dev DB) and then mitigated; the restored DB is at head with the additive migration already applied.

**IT verdict: CONDITIONAL PASS** — operations safe as of this session; **backup automation is a required Phase 2 prerequisite** before any further migration or deploy.

---

## 14. Phase 1 Final Verdict (Part 13)

**PASS (with conditional Phase 2 prerequisites)**

All acceptance criteria reproduced independently:
- Real FPL `starts` flows API → DB → Feature Store → Expected Minutes → V3 xPts; `round(minutes/90)` fabrication removed.
- 584 players, 365 starters, 35 sub-only; V3 now separates them (64.1 vs 23.1); 0 NaN/negatives; bounds [0,90]; xPts 0–1.718.
- 187 tests pass, `ruff` clean, app boots (HTTP 200), real DB untouched by the suite (hash-proven).
- V3 engines and config **unchanged**; bench optimizer untouched (correctly out of scope).
- Per-GW limitation documented and live-verified, nothing fabricated.

Conditions (carried into Phase 2, non-blocking for Phase 1 sign-off):
1. Backup automation operational before next destructive migration / deploy.
2. Peer review of the Phase 1 diff before merge.
3. Correct the "22 players" count in the workstream report.
4. Harden F-1 (destructive `__main__` cleanup) opportunistically.

---

## 15. Phase 2 Recommendations (Part 14)

**Data & operations (priority):**
1. Stand up scheduled backups: create `data/backups/`, cron `0 3 * * * cd repo && .venv/bin/python scripts/backup_db.py --keep 14 [--offsite-dir …]`; add a pre-migration backup hook to the runbook.
2. Begin per-GW observation ledger the moment `element-summary/{id}/history` populates (GW1) — the evidence base for calibration, MCRM thresholds, and the three-event shadow model.
3. Add `history_past` (real per-season starts) to the ingested schema for multi-season reliability context.

**Engineering:**
4. Add GitHub Actions CI status enforcement (required checks) so the existing workflow gates merges.
5. Add a backup-recentness assertion to CI smoke tests (`data/backups/` non-empty or script dry-run), turning the operational gap into a tested invariant.
6. Peer-review gate for model/engine changes; record reviewer in the PR.
7. Extend the secrets scan to connection-string patterns (e.g. `sqlite://` is fine, but `postgres://user:pass@` / URI-encoded credentials).

**Model (after GW evidence):**
8. Build the substitute/minutes intelligence per the design (bench optimizer in the decision layer, MCRM threshold from observed ≥60-min reliability, three-event minutes candidate as a shadow) — promotion only on multi-GW evidence, per §4 discipline.

**Non-goals (carried):** keep V3 as production; do not collapse prediction/minutes/decision responsibilities; no Monday model churn.

---

*Prepared by ML/Analytics Engineering during a read-only verification session. All numbers re-derived from the live database and live FPL API on 2026-08-13.*
