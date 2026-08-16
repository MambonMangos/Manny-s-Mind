# Historical FPL Data Integration & V3 Model Enhancement

**Owner:** ML / Analytics Engineer · **Status:** Research program complete; production **unchanged**; shadow candidate registered (not promoted).

This is the operational home of the historical-data program (Phases 1–8). It documents what was built, how to reproduce it, and the strict production-safety contract that governs the experimental configs. The closeout report with full results is in `reports/historical_data_integration.md`.

## 1. What exists

- **`research/identity.py`** (Phase 1) — cross-season player identity via FPL `code` (stable across seasons; `element` is not). Exposes leakage-safe previous-season priors.
- **`research/historical_features.py`** (Phase 2) — `add_historical_features(players_df, sd, gw_n, include=("player","team","prev"))` injects `hist_*` columns built strictly from rounds `< gw_n` and fully completed seasons. Never used by the production pipeline.
- **`research/calibration.py`** (Phases 3–4) — fits empirical per-position params (finishing, creative, bonus, clean-sheet, minutes incl. beta-binomial alpha/beta) from faithful train seasons and writes them to **new versioned YAML configs** (`write_config_yaml` never overwrites).
- **`research/preseason.py`** (Phase 5) — 2026-27 preseason prior (Model E) from the `players_raw` snapshot; structural validation only (no 2026-27 gameweeks exist).
- **`research/validation.py`** (Phase 6) — walk-forward folds and the A–F ablation; metrics + cache management.
- **`research/candidates.py`** (Phase 7) — shadow-candidate registry.
- **`research/backtest.py`**, **`research/run_validation.py`** — prediction runner and reproduction driver.
- **Experimental configs** — `config/expected_points/expected_points_v1_hist{,_fold1,_fold2}.yaml` and `config/expected_minutes/expected_minutes_v1_hist{,_fold1,_fold2}.yaml`.

## 2. Data contract

| Concept | Rule |
|---|---|
| Source | vaastav pinned `8c97b2adb123863c3dd581e730f1360e89815ac2` (MIT) |
| Faithful seasons | 2022-23, 2023-24, 2024-25 (real per-GW `starts` + FPL xG) |
| Proxy seasons | 2019-20, 2020-21, 2021-22 (no `starts`/xG; research-only) |
| Leakage safety | aggregates use rounds `< gw_n`; previous season always completed; fixtures snapshots ≤ `gw_n − 1` |
| Sub inference | sub = `starts==0 & minutes>0`; unused/not-squad = both zero (no `status` column — documented) |
| Stack | numpy + pandas only (no sklearn/scipy/polars) |

## 3. How the experimental configs engage (production safety)

The engines (`engines/expected_points_engine.py`, `engines/expected_minutes_engine.py`) accept an optional `config_version`. With `config_version=None` (the production call path) the code is **byte-for-byte the production implementation** — the empirical sections are config-gated. The hist feature columns are only present when a research state injects them. Therefore:

- `config/active.yaml`, `config/production/production_v1.yaml`, `expected_points_v1.yaml`, `expected_minutes_v1.yaml` are never touched by this program.
- Nothing experimental is reachable from the app without an explicit version/hist request.

## 4. Results (walk-forward, means across folds)

| model | RMSE pts | bias | corr | MAE min | start acc | top-10 overlap |
|---|---|---|---|---|---|---|
| A baseline | 2.474 | −0.800 | .276 | 31.1 | .720 | 0.72 |
| B +points-hist | 2.355 | −0.509 | .322 | 31.1 | .720 | 0.88 |
| C +minutes-hist | 2.449 | −0.736 | .274 | 33.9 | .801 | 0.96 |
| **D +team (candidate)** | **2.319** | **−0.409** | **.338** | 33.9 | .801 | **1.15** |
| F +prev | 2.323 | −0.455 | .341 | 34.9 | .757 | 1.15 |

The candidate **D** (points-hist + minutes-hist + team strength) improves RMSE, bias, correlation and per-gameweek top-10 identification vs production, at a small MAE cost driven by the minutes model's bench branch. See the report (§6–7) for the interpretation and trade-offs.

## 5. Reproduce

```bash
python -m research.run_validation [--fold fold1|fold2] [--models A_baseline,...] [--no-cache] [--force-configs]
```

Writes/uses caches in `data_research/results/`:
- `v3_<model>_<fold>_predictions.csv` — per-(model, fold, season) prediction rows
- `ablation_summary.csv` — fold × model metrics table
- `preseason_gw1_baseline.csv`, `validation_summary.txt`, `shadow_candidate.json`

The 2026-27 GW1 baseline can also be produced directly: `research.preseason.run_preseason_baseline()`.

## 6. Shadow candidate & promotion

`research.candidates.py` registers `v3_hist_d_team` (points `expected_points_v1_hist` × minutes `expected_minutes_v1_hist`, features `player`+`team`) and a minimal-footprint alternative `v3_hist_b_points`. **Promotion requires ≥5 consecutive gameweeks shadow-running against the production primary, a head-to-head metric comparison, and an explicit manual decision** — never auto-promotion. Until then `promotion_status` stays `not_promoted` in `data_research/results/shadow_candidate.json`.

## 7. Known limitations

See report §11. Notable: proxy seasons excluded from training; unused/not-squad indistinguishable; 2026-27 preseason structural-only; research states use `chance_of_playing_next_round=100%` (same as baseline) so both models over-predict unused subs.
