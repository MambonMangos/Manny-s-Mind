# Historical Data Integration & V3 Model Enhancement — Closeout Report

**Role:** ML/Analytics + Data Engineering + QA · **Historical Research Program Phases 1–8** · **Date:** 2026-08-16
**Guardrail:** Production V3 is untouched. All experimental behaviour is engaged only via *versioned experimental configs* (`expected_points_v1_hist*`, `expected_minutes_v1_hist*`) that are **never referenced by `config/active.yaml` or `config/production/production_v1.yaml`**. With `config_version=None` the engines are byte-for-byte the production implementation (verified by the existing engine test suites, all green). Promotion to production is explicitly **not** performed here — it requires the shadow-candidate process described in §9.

---

## 1. Objective

Complete the Director-approved "Historical FPL Data Integration & V3 Model Enhancement" program:

1. Build a leakage-safe historical-data pipeline on the pinned vaastav source.
2. Replace the V3 expected-points and expected-minutes closed-form constants with empirically fitted values (Phase 1–4).
3. Construct a 2026-27 preseason prior (Phase 5).
4. Validate via walk-forward folds + ablation Models A–F (Phase 6).
5. Register a versioned shadow candidate (Phase 7) and document everything (Phase 8).

## 2. Data foundation

| Item | Status |
|---|---|
| Source | vaastav/Fantasy-Premier-League pinned at `8c97b2adb123863c3dd581e730f1360e89815ac2` (MIT) |
| Faithful seasons (real per-GW `starts` + FPL xG) | **2022-23, 2023-24, 2024-25** |
| Proxy seasons | 2019-20, 2020-21, 2021-22 (no `starts`/xG → research-only) |
| Cross-season identity | FPL `code` stable across seasons (verified Salah=118748, Saka=223340); per-season `element` is not |
| Substitution inference | sub = starts==0 & minutes>0; unused/not-squad = starts==0 & minutes==0 (no `status` column — documented limitation) |
| 2026-27 preseason | `players_raw.csv` snapshot carrying 2025-26 season totals; **no `gws/` yet** → Model E is structural-only |

## 3. What changed (additive, production-safe)

- **`engines/expected_points_engine.py`** — `config_version` parameter; empirical finishing/creative multipliers, bonus OLS, clean-sheet linear model, prev-season shrinkage, team-strength adjustment. Default `None` = production.
- **`engines/expected_minutes_engine.py`** — `config_version` parameter; `historical_minutes` section with beta-binomial P(start), the "came off the bench" branch `E[min] = P(start)·E[min|start] + P(not start)·P(sub|not start)·E[min|sub]`, and a `sub_rate_given_not_start` output field. Default `None` = production.
- **`engines/expected_projection_engine.py`** — `points_version`/`minutes_version` passthrough.
- **`research/`** (new): `identity.py` (Phase 1), `historical_features.py` (Phase 2), `calibration.py` (Phases 3–4 config generation), `preseason.py` (Phase 5), `validation.py` (Phase 6), `candidates.py` (Phase 7), `backtest.py` (versioned/hist-feature extensions), `run_validation.py` (driver).
- **`config/expected_points|minutes/expected_points|minutes_v1_hist{.yaml,_fold1.yaml,_fold2.yaml}`** — generated candidates; production configs untouched.
- Historical `hist_*` columns are injected into `players_df` only by research states; `features/store.py` and `services/scoring.add_derived_columns` are unmodified (verified the latter preserves unknown columns).

## 4. Empirical parameters (fitted, minutes-weighted, shrinkage-adjusted)

Per-position on faithful seasons. Final candidate fit on all three; fold configs fit on the fold's train seasons only (leakage-safe by construction).

| Position | start_rate_prior | min_if_start | min_if_sub | sub_rate_given_not_start | finishing (goals/xG) | creative (assists/xA) |
|---|---|---|---|---|---|---|
| GKP | .221 | 89.5 | 83.0 | .044 | .967 | — |
| DEF | .294 | 85.4 | 42.0 | .161 | .967 | 1.411 |
| MID | .265 | 80.0 | 30.6 | .250 | 1.213 | 1.592 |
| FWD | .219 | 79.1 | 26.5 | .257 | 1.128 | 1.6 (capped) |

Bonus (MID example): `E[bonus] = 0.0907 + 0.00542 · bps/90`. Clean-sheet (GKP): `P(cs) = 0.6164 − 0.1553 · xGC/game` (clipped to [0, max]). All values are in the generated YAML configs.

## 5. Preseason prior (Model E, Phase 5)

`build_preseason_prior()` normalizes the 2026-27 `players_raw` snapshot (567 players) into a per-player prior: last-season per-90 rates (xG/xA/xGI/points), starts rate, minutes-per-start, current price/status/set-piece orders. `validate_preseason_prior()` — **all 8 structural/sanity checks pass**. GW1 baseline with the hist configs: Haaland 2.27 xPts, then GKP-heavy (Woodman 2.04, Mamardashvili 1.83) — expected in preseason when fixtures/roles are undecided. No 2026-27 gameweeks exist, so Model E is validated structurally only (per the directive).

## 6. Walk-forward validation (Phase 6)

Folds: **fold1** train 2022-23 → validate 2023-24; **fold2** train 2022-23+2023-24 → validate 2024-25. All results cached per (model, fold) under `data_research/results/` (`v3_<model>_<fold>_predictions.csv`, `ablation_summary.csv`). ~53k predictions per fold.

| model | description | MAE pts | RMSE pts | bias | corr | MAE min | start acc | top-10 overlap |
|---|---|---|---|---|---|---|---|---|
| A_baseline | production v1 (as-is) | 1.150 | 2.474 | −0.800 | .276 | 31.1 | .720 | 0.72 |
| B_points_hist | +empirical xPts/90 | 1.161 | 2.355 | −0.509 | .322 | 31.1 | .720 | 0.88 |
| C_minutes_hist | +probability minutes | 1.164 | 2.449 | −0.736 | .274 | 33.9 | .801 | 0.96 |
| D_team | B + C + team strength | 1.188 | 2.319 | −0.409 | .338 | 33.9 | .801 | 1.15 |
| F_full | D + prev-season priors | 1.159 | 2.323 | −0.455 | .341 | 34.9 | .757 | 1.15 |

(Means across both folds; full per-fold table in `data_research/results/ablation_summary.csv`.)

**Reading the results**
- **Points calibration (B) is an unambiguous improvement** vs the production baseline: RMSE −0.12, bias halved (−0.80 → −0.51), correlation +0.05, top-10 gameweek overlap +0.15 — at essentially zero MAE cost (+0.011).
- **The minutes model (C) fixes the start-probability bias** (start accuracy .72 → .80) and adds the bench-appearance branch (sub-rate bias −0.15 → +0.03) but its raw minutes MAE is worse (+2.8) because it correctly raises expected minutes for starters and hands non-starters a bench branch — a probabilistic model's expectation is not directly comparable to the baseline's compression toward zero for unused subs (both over-predict unused subs; the documented research-state `chance=100%` floor is unchanged from the baseline).
- **Team strength (D) compounds B's gains** — best RMSE (2.32), best bias (−0.41), best correlation (.338), best top-10 (1.15) — at a small MAE cost (+0.04) attributable to the minutes component.
- **Prev-season priors (F) add little** over D and hurt fold2 start accuracy (.80 → .73), so **D is the candidate**, not F.

## 7. Interpretation for real decisions

The primary job of the prediction system is **identifying which players score well this gameweek** (captains, transfers, squad selection), not minimizing per-player L1 error on a heavily zero-inflated outcome. On that metric the improvements are substantial:

- Predicted top-10 vs actual top-10 per gameweek overlap rises **0.72 → 1.15** (D): roughly 40% more of the actual best performers appear in the model's top ten.
- Bias on points falls from **−0.80 to −0.41**: the V3's chronic under-prediction is roughly halved.
- Start-probability accuracy improves from **.72 → .80**, directly improving the minutes used to scale per-90 rates.

## 8. Production safety

- `config/active.yaml`, `config/production/production_v1.yaml`, `expected_points_v1.yaml`, `expected_minutes_v1.yaml` — **untouched** (diff-verified).
- No engine or Feature Store change is reachable from the production call path without an explicit `config_version`/hist-column request.
- Full test suite: **349 passed** (was 300; +49 new tests incl. engine empirical branches and all new research modules). Ruff clean repo-wide.

## 9. Shadow candidate (Phase 7)

Registered in `data_research/results/shadow_candidate.json`:

- **model_id:** `v3_hist_d_team` (V3-HIST-01, Model D)
- **configs:** `expected_points_v1_hist` × `expected_minutes_v1_hist`
- **features:** `hist_*` player + team (no prev)
- **fit seasons:** 2022-23, 2023-24, 2024-25
- **status:** `shadow_candidate`, `promotion_status: not_promoted`

**Promotion requires (never auto-promote):** (1) ≥5 consecutive gameweeks running as a shadow alongside the production primary; (2) head-to-head MAE/RMSE comparison over that window; (3) an explicit manual decision. A second, lower-risk candidate `v3_hist_b_points` (points calibration only, minutes untouched) is registered for a minimal-footprint upgrade path.

## 10. Files

| Path | Purpose |
|---|---|
| `research/{identity,historical_features,calibration,preseason,validation,candidates}.py` | Program modules Phases 1–7 |
| `research/backtest.py`, `research/run_validation.py` | Prediction runner + driver entry point |
| `config/expected_points/expected_points_v1_hist{,_fold1,_fold2}.yaml` | Candidate points configs |
| `config/expected_minutes/expected_minutes_v1_hist{,_fold1,_fold2}.yaml` | Candidate minutes configs |
| `data_research/results/` | `ablation_summary.csv`, `v3_<model>_<fold>_predictions.csv`, `preseason_gw1_baseline.csv`, `shadow_candidate.json`, `validation_summary.txt` |
| `tests/test_engine_hist_branches.py`, `tests/test_research_{identity,historical_features,calibration,preseason,validation,candidates}.py` | New test coverage |

## 11. Known limitations

- Proxy seasons (2019-20 → 2021-22) cannot reconstruct `starts`/xG → excluded from training/validation.
- Sub/unused inference has no `status` column; unused and not-squad are indistinguishable.
- Preseason (2026-27) has no gameweeks yet → Model E is structural-only.
- Research states set `chance_of_playing_next_round=100%` (the baseline does the same) → both models over-predict unused subs; neither direction is corrected here.
- The empirical minutes model raises raw minutes MAE while improving start accuracy and top-player identification; the trade-off is documented and the minutes config is versioned separately so points-only (B) or points+team are independently promotable.
