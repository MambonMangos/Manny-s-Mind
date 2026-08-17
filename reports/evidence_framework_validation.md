# Evidence Framework — Walk-Forward Validation Result

**Role:** Senior ML/Analytics Engineer · **Date:** 2026-08-16 · **Phase 4 of the evidence-framework program**
**Status:** COMPLETE — documented negative result. The evidence layer as configured does not beat the incumbent candidate; **Model D remains the shadow candidate.**

---

## 1. What was validated

Model G = V3 points + minutes engines fed by the evidence layer (`research/evidence.py` + `config/evidence/evidence_v1.yaml`): per-group current-season weights driven by accumulated evidence volume (effective minutes), blended with historical priors (previous completed season, personal then position-average fallback).

- **Folds (unchanged, walk-forward discipline):** train 2022-23 → validate 2023-24 (fold1); train 2022-23 + 2023-24 → validate 2024-25 (fold2).
- **Baselines:** A (production V3), B/C (hist features one-sided), D (points+minutes hist, `hist_features=(player, team)`), F (full hist features). D is the incumbent candidate (best honest performer on fold-mean).
- All metrics from `research.validation.summarize_model` on per-GW predictions (`predicted_points`, `expected_minutes`, `start_probability`).

## 2. Result: G does not beat D

Official G rows use the config defaults that were fold1-tuned via the grid (§4) — starting floor 0.85, rate_attack floor 0.60 — run honestly on both folds.

| fold | model | MAE | RMSE | bias | corr | minutes MAE | start acc | top10 overlap |
|---|---|---|---|---|---|---|---|---|
| fold1 | D_team | 1.147 | **2.243** | -0.325 | **0.362** | 34.90 | 0.801 | 1.06 |
| fold1 | F_full | **1.106** | 2.244 | -0.386 | **0.371** | 35.68 | 0.783 | 1.08 |
| fold1 | G_evidence | 1.205 | 2.322 | -0.391 | 0.272 | 35.35 | 0.799 | 0.64 |
| fold2 | D_team | 1.229 | **2.394** | -0.492 | **0.313** | **32.88** | 0.800 | 1.25 |
| fold2 | F_full | **1.212** | 2.401 | -0.524 | 0.312 | 34.18 | 0.731 | 1.22 |
| fold2 | G_evidence | 1.305 | 2.455 | -0.497 | 0.225 | 33.64 | 0.790 | 0.86 |

Pooled: D RMSE 2.319 / corr 0.338 / MAE 1.188 vs G RMSE 2.388 / corr 0.249 / MAE 1.255. G loses on **every** points metric on both folds; its one bright spot (fold2 minutes MAE 33.6) is marginal.

## 3. Root-cause analysis

1. **Start-accuracy collapse at default floors (fixed).** At strength floor 0.10, `w_starting = 0.10^0.6 ≈ 0.25` → the model leaned 75% on the previous-season starts rate for no-current-data players, over-predicting starts (gw3-8 start acc fell 0.842 → 0.631). Fix: per-group `min_current_weight` floors (starting 0.85, rate_attack 0.60, minutes 0.60, bonus 0.40, team 0.50) — the prior can never exceed the shares D's fixed rule already uses. This restored start accuracy to D's level (0.799/0.790) but did **not** restore points correlation.
2. **Persistent prior pull on rates.** Because evidence-strength never fully "turns off" the prior, G blends 30–40% previous-season xGI into attack rates for the first ~5 GWs and a material fraction mid-season, where D is 100% current after 3 games. This dampens differentiation → lower correlation and top-10 identification (the decision-relevant metric).
3. **Diagnostic isolating the cause.** With `rate_attack` floor = 1.0 (attack rates pure current, evidence only for starting/minutes/team/bonus) corr was still 0.279 vs D 0.362 — the drag comes from the **team/bonus/minute blending**, not the rate blend. D's simpler fixed-rule approach extracts more signal from the same data.

## 4. Parameter grid (fold1 only, then honest fold2)

**Grid 1** (8 combos: saturation 200/450 × starting exponent 1.0/2.0 × rate exponent 2.0/3.0): all worse than D. Notably, starting exponent 2.0 made start accuracy *worse* (0.55) — at the floor, `0.10^2 → 0.01` current weight ⇒ 99% previous-season starts (opposite of the hypothesis).

**Grid 2** (4 combos, floors after the `min_current_weight` fix; saturation/exponents at defaults):

| combo | RMSE | MAE | corr | start acc |
|---|---|---|---|---|
| stf0.70_raf0.60 | 2.322 | 1.193 | 0.279 | 0.794 |
| stf0.70_raf0.75 | 2.323 | 1.190 | 0.276 | 0.794 |
| stf0.85_raf0.60 | **2.319** | 1.187 | **0.284** | **0.798** |
| stf0.85_raf0.75 | 2.321 | 1.184 | 0.282 | 0.798 |

Best fold1 combo (stf0.85_raf0.60) folded into the config defaults, then run honestly on fold2 → §2. Fold1 D reference: RMSE 2.243 / MAE 1.147 / corr 0.362 / start acc 0.801.

## 5. Decision

- **Do not register G as a shadow candidate.** The decision rule (§10 of the discovery report) requires G to be no worse than the incumbent on fold-mean metrics *and* better on at least one decision-relevant metric. G fails the first criterion on every points metric; its minutes-MAE edge is too small to count.
- **D_team remains the candidate** (ablation unchanged: D pools best across RMSE 2.319 and start acc 0.801; F_full is comparable and retains a role in feature-group analysis).
- The evidence layer is **kept in the codebase as an instrumented experimental path**, not because it wins on predictions, but because it delivers the explainability metadata (`ev_strength`, per-group weights, `prior_type`, breakdown) the Assistant Manager will consume later, and it is a fully leakage-safe reference implementation for any future continuous-time weighting. It remains out of `active.yaml`; production is byte-identical.

## 6. Engineering rule honored

"Use more data only when it demonstrably improves prediction." The evidence layer demonstrably did **not** improve prediction over D's fixed shrinkage. This is the honest, recorded outcome; no promotion, no silent config change.

## 7. Artifacts

- `data_research/results/ablation_summary.csv` — now includes G rows (all folds, all models A–G).
- `data_research/results/ablation_summary_evidence.csv` — D/F/G comparison.
- `data_research/results/evidence_grid_fold1.csv`, `data_research/results/v3_G_evidence_{stf0.85_raf0.60}_fold1_predictions.csv` — grid record.
- `data_research/results/v3_G_evidence_fold1/fold2_predictions.csv` — official G rows.
- Tests: `tests/test_research_evidence.py` (17), identity prior rate-columns test, engine integration/gating tests. Full suite 367 passing.
