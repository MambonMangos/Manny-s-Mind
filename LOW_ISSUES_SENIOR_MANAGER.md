# Low-Priority Findings — Technical Summary

**To:** Technical Senior Manager  
**From:** Production Audit  
**Date:** July 2026  
**Project:** Manny's FPL House  
**Topic:** 12 low-severity findings identified during the pre-GW1 audit (L-01 through L-12)

---

### L-01: `or 0` Redundancy

Several files use the pattern `row.get("field", 0) or 0`, where the default `0` in `.get()` already handles the `None` case. The trailing `or 0` is redundant — it only triggers if the column value is literally `0` (falsy), which would incorrectly override a valid zero. No functional impact currently since no meaningful metric is legitimately zero, but it's a code smell that suggests misunderstanding of `.get()` semantics.

---

### L-02: JSON Columns Use `String` Instead of `JSON` Type

Five model fields (`chip_plays`, `snapshot_json`, `features_used`, `weights_snapshot`, `notes`) are declared as `String` but store serialised JSON. SQLAlchemy's `JSON` type provides automatic serialisation/deserialisation and is portable across backends. This works today because we manually `json.dumps()` before write and `json.loads()` after read, but it adds unnecessary boilerplate and loses type enforcement.

---

### L-03: Inline Imports

Two modules import `numpy` and `pandas` inside function bodies rather than at the top of the file. This works but violates Python convention. It slightly obscures module dependencies and can cause a minor performance penalty if the function is called repeatedly, since the import is re-executed each time.

---

### L-04: Missing Foreign Key Constraints

Three tables (`DecisionLog`, `ChipState`, `RecommendationOutcome`) store `team_id` without a foreign key to the `teams` table. SQLite does not enforce FK constraints by default anyway (it requires `PRAGMA foreign_keys = ON`), so this has no runtime effect. However, if we ever migrate to PostgreSQL, the missing FK declarations would cause migration failures and orphaned rows.

---

### L-05: `update_prediction_version_metrics` Overwrites Without Check

The function that writes MAE, RMSE, and bias back to the `PredictionVersion` row overwrites whatever value is there with no guard or audit trail. If validation runs twice for the same version, the old metrics are silently replaced. This is correct behaviour for our append-only design, but adding a log warning on overwrite would help debug unexpected re-runs.

---

### L-06: Exception Leakage to Logs

The result ingestion service logs `logger.error("Result ingestion failed: %s", e)`, which prints the exception's `__str__` directly. If the exception contains user data or internal state, it leaks to the log. Standard practice is to `logger.exception(...)` which includes the full traceback in a controlled format, or to sanitise the message before logging.

---

### L-07: No `__init__.py` in 5 Packages

Five package directories lack `__init__.py` files. Python 3.3+ supports namespace packages without them, so imports work fine. However, most tooling (linters, type checkers, IDEs) assumes explicit `__init__.py` files exist. Missing them can cause false-positive import errors in development environments and makes the package structure less explicit.

---

### L-08: Typo "differentails"

`market_intelligence_engine.py` line 90 has a return key `"differentails"` instead of `"differentials"`. This means any code reading `get_market_summary()["differentails"]` would need to match the typo. It's cosmetic but creates a trap for future developers who naturally type the correct spelling.

---

### L-09: Dead Config File

`config/weights/weights_v1.yaml` exists but `active.yaml` points to `weights_v2`. The V1 file is never loaded. It's harmless but adds confusion — a developer browsing the config directory can't tell which files are live. Removing it would simplify the config surface area.

---

### L-10: No Pagination on Version Queries

`get_prediction_versions()` returns every row in the `prediction_versions` table with no LIMIT or pagination. The ledger currently has few entries, so this is fine. Over a full season (~38 weekly runs × N versions), the query will grow linearly and eventually consume unnecessary memory on the Streamlit server for a list that's always displayed in a dropdown.

---

### L-11: Config Cache Has No TTL

The config loader caches parsed YAML in a module-level dict with no time-to-live. During a single process lifetime, the first `load_config()` call wins and subsequent calls return the cached version. If the config file is updated on disk (e.g., a weights tweak mid-season), the running process won't pick it up until restart. Adding a simple age check would allow hot-reload.

---

### L-12: Empty `fixture_map` Silent Fallback

When no `fixture_map` is provided to `build_feature_store()`, fixture difficulty defaults to a flat 3.0 across all players with no log warning. Downstream projections produce plausible-looking output based on fake data, making it easy to miss the fact that fixtures aren't actually being factored in. A `logger.warning` on this fallback would make the gap visible.
