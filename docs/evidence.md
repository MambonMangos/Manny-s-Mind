# Evidence Layer

Current-season evidence → trust-weighted blend of historical priors and current-season observations for the V3 engines. **Experimental path only — never wired into production selection.**

**Validation verdict:** walk-forward shows the evidence model (G) does **not** beat the incumbent candidate D on any points metric. D remains the shadow candidate; the evidence layer is retained for its explainability metadata and as the reference implementation for continuous-time weighting. See `reports/evidence_framework_validation.md`.

## Model

`effective_minutes = w_min·minutes + w_start·starts + w_app·appearances`

`strength = floor + (1 − floor)·(1 − exp(−effective_minutes / saturation))`, capped at `max_strength`.

Per-group current weight: `w_current = clip(strength ^ exponent, min_current_weight, 1.0)`.

`value_used = w_current · value_current + (1 − w_current) · value_historical`

| group | exponent | min_current_weight | historical source | fallback |
|---|---|---|---|---|
| rate_attack | 2.0 | 0.60 | prev xGI/90 | position avg |
| starting | 0.6 | 0.85 | prev starts_rate | position avg |
| minutes | 0.8 | 0.60 | prev minutes per start | position avg |
| bonus | 2.5 | 0.40 | prev bps/90 | league avg |
| team | 0.7 | 0.50 | prev-season team adj | none |

`min_current_weight` is the fix that stopped the prior from dominating low-evidence players (it caps the prior at the shares D's fixed rule already uses).

## Config

`config/evidence/evidence_v1.yaml` (version `evidence-v1.0.0`). Loaded only by explicit `evidence_version` — **not** in `config/active.yaml`. Never modify production configs.

## Pipeline

1. `research.backtest.predict_gameweek(..., evidence_version="evidence_v1")` (optional `evidence_cfg` override for grids) injects 28 `ev_*` columns onto `players_df` via `research.evidence.add_evidence_features`.
2. Engines read `ev_*` columns **only when present**; the production path never injects them, so production is byte-identical.
3. Points engine: evidence mode uses `ev_xg_per_90`/`ev_xa_per_90` × `ev_team_attack_mult`/`ev_team_defense_mult` (team adj replaces `_team_strength_adjust`), `ev_bps_per_90` for bonus, and skips its fixed prev-season + historical-team blocks.
4. Minutes engine: `observed = ev_w_starting·posterior + (1 − ev_w_starting)·clip(ev_prior_starts_rate, 0, 1)`; `minutes_if_starting` uses `ev_minutes_per_start` (min starts 1).
5. Evidence requires the hist configs (`expected_points_v1_hist`/`expected_minutes_v1_hist`).

## Leakage safety

- Each gameweek uses only rounds `< gw_n` (cumulative `players_df`) plus the **completed** previous season.
- Personal prior keyed by stable FPL `code`; trusted only when prev games ≥ 3 and prev minutes ≥ 90; otherwise position-average fallback (players with prev games ≥ 10); unresolved → `ev_prior_type = none`.
- Proxy seasons (no xG) contribute no rate/team prior — no blend toward zero.

## Usage

```python
from research.backtest import predict_gameweek
from research.loader import SeasonData

sd = SeasonData.load("2023-24")
out = predict_gameweek(sd, 5,
    points_version="expected_points_v1_hist",
    minutes_version="expected_minutes_v1_hist",
    hist_features=("player",),
    evidence_version="evidence_v1")
```

Grid / folds: `research/evidence_grid.py` (`run_grid_fold1`, `run_best_on_fold2`); Model G registered in `research/validation.py::MODELS`; `run_fold`/`build_ablation_table` include it.

Explainability per player: `research.evidence.evidence_breakdown(player_id, players, sd, gw)` → strength + per-group `{current_value, historical_value, blended_value, weight_current}`.
