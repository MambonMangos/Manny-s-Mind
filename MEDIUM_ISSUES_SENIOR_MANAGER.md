# Medium-Priority Findings — Technical Summary

**To:** Technical Senior Manager  
**From:** Production Audit  
**Date:** July 2026  
**Project:** Manny's FPL House  
**Topic:** 18 medium-severity findings identified during the pre-GW1 audit (M-01 through M-18)

---

### M-01: No Unique Constraints on 4 Core Tables

Four tables (`PlayerGameweekStat`, `PriceHistory`, `PlayerSnapshot`, `Snapshot`) lack composite unique constraints on natural keys like `(player_id, gameweek_id)`. This means repeated data ingestion can produce duplicate rows silently. The fix is straightforward — add `UniqueConstraint` declarations to the ORM models, but it requires a migration.

---

### M-02: Mixed Flush/Commit Transaction Boundaries

Individual upsert operations in `crud.py` use `session.flush()` while their callers use `session.commit()`. If a bulk operation fails partway through, flushed rows remain in the session transaction but never commit, creating a partial-update risk. The caller must remember to rollback manually — easy to forget.

---

### M-03: No Rollback on Error in Data Loader

The data loader's exception handler closes the session without calling `session.rollback()`. If an API fetch fails mid-ingestion, the session is left in a potentially dirty state. Entering subsequent operations with an unclean session risks constraint violations or stale data leaking into the next request.

---

### M-04: `setattr()` on ORM Models with Arbitrary Dict Keys

The upsert helpers iterate over every key in the incoming API response dict and call `setattr(model, key, value)`. If the FPL API ever adds an unexpected field that shadows an SQLAlchemy internal attribute, it could corrupt ORM state. Defensive whitelisting would prevent this.

---

### M-05: Engine Accuracy Insert Without Idempotency Guard

The validation engine calls `insert_engine_accuracy` inside a loop without checking whether a record already exists for that `(version_id, gameweek_id, engine_name)`. Running validation twice produces duplicate accuracy rows, which skews downstream metrics and reports.

---

### M-06: Validation Cycle Has No Per-Version Savepoints

The validation loop commits once at the end. If a single version's validation fails, all successfully validated versions in that batch are rolled back. No partial progress is preserved, wasting computation on each re-run.

---

### M-07: Stored XSS Risk via `unsafe_allow_html=True`

Five files use `st.markdown(..., unsafe_allow_html=True)` with f-string-interpolated player names, team names, and news text. While the current data source (FPL API) is trusted, any future ingestion path that allows non-FPL content could inject malicious HTML/JS into the dashboard.

---

### M-08: No SQLite Connection Pooling Limits

The database connection string has no `pool_size` or `max_overflow` configured. SQLite only supports one writer at a time. Under concurrent access — multiple Streamlit sessions or background threads — this can produce `database is locked` errors.

---

### M-09: `id` vs `player_id` Column Name Ambiguity

Snapshot persistence used `row.get("id", 0)` while the DataFrame column is named `player_id` (canonicalised upstream by `build_feature_store()`). This caused all snapshots to be stored with `player_id=0`. **Already fixed** as part of H-18.

---

### M-10: Unnecessary DataFrame Copy in `scoring.py`

`add_derived_columns()` calls `df.copy()` upfront, and `compute_value_score()` calls `add_derived_columns()` internally — meaning every pipeline run copies the player DataFrame twice. On a ~600-player dataset this is negligible, but it doubles memory for no functional benefit.

---

### M-11: Tests Use Live Config Files

Both test files load YAML configs from the live `config/` directory. This makes tests non-hermetic — they can fail due to unrelated config changes, typos, or missing files. Tests should supply their own config fixtures.

---

### M-12: Tests Share Mutable File-Based Database

`reset_db()` drops and recreates tables in the same on-disk SQLite file. Test ordering matters because data residue can bleed between tests. Parallel execution is impossible. An in-memory SQLite database per test would solve this.

---

### M-13: Hardcoded TEAM_ID

The user's team ID (`472930`) is hardcoded in `constants.py` with no environment-variable fallback. The app cannot be deployed for another user without modifying source code. A `TEAM_ID` env var with this value as default is the recommended path.

---

### M-14: Feature Store Has No Cache Invalidation

Feature Store accessors cache their results lazily with no TTL or invalidation mechanism. If the underlying DataFrame changes between pipeline runs without rebuilding the store, engines read stale features. This is safe within a single pipeline run but risky if the store instance is reused.

---

### M-15: `fixture_engine.py` Has Too Many Responsibilities

At 410 lines, this file bundles fixture-map building, difficulty scoring, window analysis, swing detection, heatmap generation, and summary tables. Violates single-responsibility principle. Difficult to test, maintain, or extend without unintended side effects.

---

### M-16: `projection_engine.py` Duplicates Confidence Engine Logic

85 lines in `projection_engine.py` compute variance and confidence metrics that already exist in `confidence_engine.py`. Two implementations of the same logic will inevitably diverge during maintenance, producing inconsistent projection widths and confidence tiers.

---

### M-17: Stale Features Computed But Never Consumed

The Feature Store computes `value_form`, `value_season`, `ict_index`, `influence`, `creativity`, and `threat` but no engine reads them. This is wasted CPU per pipeline run and misleading for future developers reading the code.

---

### M-18: Monte Carlo Engine Not Seeded

Simulations use `np.random.normal()` without a fixed seed. Results differ on every run, making it impossible to reproduce, debug, or compare simulation outcomes across runs. A configurable seed parameter would resolve this.
