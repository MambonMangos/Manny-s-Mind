# Validation Platform — Manny's FPL House

**Purpose:** measure how accurate past predictions were, enabling **evidence-based model improvement**. This is validation *infrastructure*, not prediction logic.

## 1. Core Workflow

```
predictions (append-only ledger)          actuals (result ingestion)
        ↓                                          ↓
        └──────────→  ValidationEngine  ──────────→┘
                        validate_version(session, version_id, gameweek_id)
                                    ↓
                       ValidationReport (metrics)
                                    ↓
                  persisted to validation_metrics + engine_accuracy
```

- `engines/validation_engine.py` — the engine.
- `services/result_ingestion_service.py` — ingests actual GW results.
- `services/learning_service.py` — learning loop that drives improvement.
- `services/error_classifier.py` — rule-based error categorisation.

## 2. Metrics Computed

Per version + gameweek, `validate_version()` produces a `ValidationReport`:

**Overall accuracy**
- `MAE` — mean absolute error.
- `RMSE` — root mean squared error (penalises large misses).
- `bias` — mean(actual − projected); positive = systematic underprediction.
- `median_ae` — robust central error.

**CI calibration**
- `coverage_80` / `coverage_95` — fraction of actuals inside the 80%/95% CIs. Drift from the target coverage means the confidence engine's variance is mis-scaled.
- `ci_width_avg` — average interval width.

**Breakdowns**
- `mae_by_position` / `rmse_by_position` / `n_by_position` — per-position (GKP/DEF/MID/FWD) accuracy.
- `best_predicted_player_id` / `worst_predicted_player_id` / `worst_error` — outlier spotting.
- `engine_scores` — per-engine contribution metrics (via `validate_engine_contributions`).

**Version comparison**
- `compare_versions(...)` — head-to-head accuracy between two weight/config versions (e.g., `weights_v2` vs `weights_v3`).

## 3. Persistence

- `ValidationMetrics` rows → `validation_metrics` table (append-only).
- `EngineAccuracy` rows → `engine_accuracy` table.
- Results are tied to a `version_id` (from `prediction_versions`, which snapshots the `config_hash` and `weights_snapshot`) — so every validation is reproducible against the exact config that produced it.

## 4. How Validation Drives Improvement

1. Run predictions → ledger (with config hash).
2. Ingest actuals after each GW (`result_ingestion_service.py`).
3. `validate_version()` → metrics.
4. `learning_service.py` compares versions and flags which engines/configs improve accuracy.
5. The **post-GW1 roadmap** (`docs/prediction.md`) prioritises engine work based on these scores — no tuning without evidence.

## 5. Testing

- `tests/test_validation.py` — engine unit tests (CI calibration, metric computation, persistence).
- Validation logic is the safety net that lets the platform evolve predictions without regressing.

## 6. Known Gaps (Phase 1, no fixes applied)

| Gap | Impact |
|---|---|
| No baseline "v1 vs v2" benchmark yet — needs GW1 actuals | Cannot yet prove V2 > V1; retirement of V1 engines (TD-1) blocked on evidence |
| Validation couples directly to DB CRUD (`engines/validation_engine.py`) | Harder to unit-test without a live DB (TD-6) |
| Error classification is rule-based | Requires manual review as categories evolve |
