# Prediction System — Architecture, Ownership & Roadmap

**Owner:** ML / Analytics Engineer
**Current state:** Version 3 (Expected Points / xPts) is the **primary production
model**. V1 and V2 remain as **shadow / control** models — they are validated
against V3 over time and are never removed.

## 1. Prediction Architecture

The prediction platform has three generations of models:

- **V1 (legacy)** — value-score engine layer (`value_engine`, `market_engine`,
  `prediction_engine`, `captain_engine`). Still the fallback for recommendation
  engines when no projection data is available.
- **V2** — the deterministic 7-step forecasting pipeline orchestrated by
  `services/pipeline.py` (ledger model `projection_v2`). Runs as a **shadow /
  control** model.
- **V3 (production)** — Expected Points / xPts (`engines/expected_projection_engine.py`,
  ledger model `expected_points_v1`). `xPts = xPts/90 × expected minutes / 90`.
  This is the production model every recommendation path consumes by default.

The primary/shadow split is **config-driven** (`config/production/production_v1.yaml`):

```yaml
primary_model: expected_points_v1
shadow_models:
  - projection_v2
```

```
Feature Store (features/store.py)
   ↓  per-player, per-GW derived features
Production Predictor (services/production_predictor.py)
   ├── PRIMARY: expected_points_v1  → xPts/90 × minutes/90 (V3, persisted)
   └── SHADOW:  projection_v2       → 7-step pipeline (V2, persisted, control)
        ↑
   services/pipeline.py (7 steps)
   1. minutes_engine          → projected minutes with rotation risk
   2. projection_engine       → base point projection with CIs
   3. regression_engine       → over/underperformance flags
   4. bookmaker_engine        → odds-based adjustment (when available)
   5. confidence_engine       → uncertainty quantification & tiering
   6. (snapshot/persistence)  → Projection ledger (append-only)
   7. opportunity_engine      → undervalued player detection
```

Every output is written to the **append-only prediction ledger** (`prediction_versions`, `projections`) with a `config_hash` and `weights_snapshot`, enabling reproducible, comparable forecasts. Shadow-model versions are persisted the same way so both generations stay validated.

### Design principles

- **One source of truth for features** — `features/store.py`.
- **Versioned config** — projection parameters live in `config/prediction/prediction_v1.yaml`; xPts parameters in `config/expected_points/`; the production model selection in `config/production/`.
- **Append-only ledger** — forecasts are never overwritten; validation compares versions against actuals.
- **Uncertainty is explicit** — every projection carries 80%/95% confidence intervals from the confidence engine.
- **Config-driven model selection** — production paths read `get_primary_model_id()` / `get_shadow_model_ids()`; they never hard-code a model id.

## 2. Engine Ownership Map

| Engine | File | Responsibility | Status |
|---|---|---|---|
| Feature Store | `features/store.py` | Derived features (single source of truth) | V2/V3 shared |
| Minutes Engine | `engines/minutes_engine.py` | Minutes projection + rotation risk | V2 (shadow) |
| Projection Engine | `engines/projection_engine.py` | Points projection + CIs | V2 (shadow) |
| Expected Points Engine | `engines/expected_points_engine.py` | xPts/90 rate model (V3) | **V3 (production)** |
| Expected Minutes Engine | `engines/expected_minutes_engine.py` | Probability-weighted expected minutes (V3) | **V3 (production)** |
| Expected Projection Engine | `engines/expected_projection_engine.py` | V3 compositor: xPts = xPts/90 × minutes/90 | **V3 (production)** |
| Production Predictor | `services/production_predictor.py` | Runs primary + shadow models, persists append-only | **V3 (production)** |
| Expected Pipeline | `services/expected_pipeline.py` | Comparison + persistence helpers | V3 (production) |
| Regression Engine | `engines/regression_engine.py` | Over/underperformance detection | V2 (shadow) |
| Bookmaker Engine | `engines/bookmaker_engine.py` | Odds integration | V2 (shadow) |
| Confidence Engine | `engines/confidence_engine.py` | Uncertainty quantification | V2 (shadow) |
| Opportunity Engine | `engines/opportunity_engine.py` | Undervalued detection | V2 (shadow) |
| Market Intelligence | `engines/market_intelligence_engine.py` | Transfer/ownership trends | V2 (shadow) |
| Monte Carlo Engine | `engines/monte_carlo_engine.py` | Simulation-based uncertainty | V2 (shadow) |
| Squad Optimizer | `engines/squad_optimizer.py` | Budget-constrained optimization | V2 (shadow) |
| Validation Engine | `engines/validation_engine.py` | Accuracy metrics, CI calibration | Shared (all versions) |
| Value Engine | `engines/value_engine.py` | Value score + player rating | **V1 (legacy/fallback)** |
| Fixture Engine | `engines/fixture_engine.py` | Fixture difficulty, windows, swings | V1+V2 merged |
| Market Engine | `engines/market_engine.py` | Transfers, ownership, price trends | **V1 (legacy/fallback)** |
| Prediction Engine | `engines/prediction_engine.py` | V1 points/minutes projection | **V1 (legacy/fallback)** |
| Captain Engine | `engines/captain_engine.py` | Captaincy analysis | **V1 (legacy/fallback)** |

The V3 engines are **production**: the assistant manager, league intelligence,
comparison platform and dashboards consume V3 projections by default. V1/V2
continue running as the control group. See `docs/expected_points.md` for the
architecture, math, minutes methodology and validation strategy.

## 3. Technical Debt Report (Phase 1)

Identified during review. **No fixes applied in Phase 1** — all items below are documented for prioritisation.

### HIGH

| ID | Debt | Location | Impact |
|---|---|---|---|
| TD-1 | Four V1 engines remain active alongside V2 equivalents | `value_engine`, `market_engine`, `prediction_engine`, `captain_engine` | Parallel computation paths produce divergent results |
| TD-2 | Feature logic duplicated between Feature Store and engines | `fixture_engine.compute_fixture_windows()` vs `features/store.py` | Silent divergence risk |
| TD-3 | CI/variance weights duplicated across engines | `projection_engine` vs `confidence_engine` | Two independent uncertainty implementations |
| TD-4 | `compute_player_rating` hardcodes rating split instead of reading `player_rating` config | `engines/value_engine.py` | Config not the single source of truth |

### MEDIUM

| ID | Debt | Location | Impact |
|---|---|---|---|
| TD-5 | `iterrows()` loops across engines | `minutes_engine`, `projection_engine`, etc. | Slow, O(N×E) pipelines |
| TD-6 | Validation engine couples to DB/CRUD directly | `engines/validation_engine.py` | Hard to unit test without a live DB |
| TD-7 | Missing indexes on some FKs | `Player.team_id` etc. | Full-table scans as data grows |

### LOW

| ID | Debt | Location | Impact |
|---|---|---|---|
| TD-8 | Staleness tracked in-process | `services/data_loader.py` | Freshness resets on restart |
| TD-9 | Fixture fallback of flat 3.0/50.0 when no fixture data | `services/scoring.py` | Plausible-but-fake projections, no warning |

## 4. Confidence & Fixture Calculations (Reviewed)

- **Confidence intervals**: built from per-component variance sources defined in `config/prediction/prediction_v1.yaml` (`variance_sources`). Reviewed as internally consistent; the **duplication** (TD-3) is the risk to fix, not the math.
- **Fixture calculations**: difficulty → score conversion (`(5-difficulty)/4 × 100`) is consistent between `services/fixture_service.py` and the engine. The Feature Store duplication (TD-2) is the risk.
- **No weight tuning, no model changes, no optimization** were performed in Phase 1, per the engineering directive.

## 5. Post-GW1 Improvement Roadmap

Prioritised after GW1 validation data is available:

1. **Consolidate V1 engines into V3-driven paths** — fold `value_engine`, `market_engine`, `prediction_engine`, `captain_engine` into the V3 recommendation pipeline as documented fallbacks; V1/V2 remain as validated shadow/control models, never removed (TD-1).
2. **Single uncertainty source** — extract CI/variance computation into one module used by projection and confidence engines (TD-3).
3. **Feature Store de-duplication** — move fixture-window features fully into the Feature Store; engines consume, never recompute (TD-2).
4. **Config-driven player rating** — read `player_rating` weights from `config/weights/` (TD-4).
5. **Performance pass** — replace `iterrows()` hot loops with vectorised operations (TD-5).
6. **Validation evidence loop** — use GW1..N actuals to score engines, prioritise the highest-ROI engine improvements.
7. **Persistent freshness** — store last-refresh timestamp in the DB (TD-8).

Each item is a behaviour-preserving refactor followed by validation, not a model change.

## 6. Historical-Data Shadow Candidate (registered, not promoted)

The historical-data program (Phases 1–8, `docs/historical_data.md`, closeout
`reports/historical_data_integration.md`) produced an empirically calibrated
candidate: **`v3_hist_d_team`** (`expected_points_v1_hist` ×
`expected_minutes_v1_hist`, with `hist_*` player + team features). Walk-forward
validation shows it improves RMSE, bias and per-gameweek top-10 identification
over the production V3 baseline. It is registered as a **shadow candidate**
(`research/candidates.py`, `data_research/results/shadow_candidate.json`) with
`promotion_status: not_promoted`.

**Promotion is deliberately not automatic** — it requires:
1. ≥5 consecutive gameweeks running as a shadow alongside the production primary,
2. a head-to-head MAE/RMSE comparison over that window,
3. an explicit manual decision to point `config/active.yaml` (or a new
   `production_vN.yaml`) at the candidate.

Until then production V3 (`expected_points_v1` × `expected_minutes_v1`) is
unchanged and remains the primary model.
