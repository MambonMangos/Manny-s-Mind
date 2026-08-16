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

## 5.5 Offline / historical validation (research)

Separate from the DB-backed platform validation, the historical-data program runs
**walk-forward** validation on reconstructed past gameweek states
(`research/validation.py`, Model A–F ablation):

- **fold1** train 2022-23 → validate 2023-24; **fold2** train 2022-23+23-24 → validate 2024-25.
- Metrics per (fold, model): points MAE/RMSE/bias/correlation, minutes MAE, start
  probability accuracy, sub-rate MAE/bias on non-starters, and per-gameweek
  predicted-vs-actual top-10 overlap.
- Reproduce with `python -m research.run_validation`; results cached in
  `data_research/results/` (`ablation_summary.csv`, per-model prediction CSVs).
- The strongest model is registered as a **shadow candidate** (`research/candidates.py`,
  `data_research/results/shadow_candidate.json`) and is **not promoted** — promotion
  requires ≥5 GWs of live shadow comparison and a manual decision.

Full details: `docs/historical_data.md`, closeout `reports/historical_data_integration.md`.

## 6. Known Gaps (Phase 1, no fixes applied)

| Gap | Impact |
|---|---|
| No baseline "v1 vs v2" benchmark yet — needs GW1 actuals | Cannot yet prove V2 > V1; retirement of V1 engines (TD-1) blocked on evidence |
| Validation couples directly to DB CRUD (`engines/validation_engine.py`) | Harder to unit-test without a live DB (TD-6) |
| Error classification is rule-based | Requires manual review as categories evolve |
