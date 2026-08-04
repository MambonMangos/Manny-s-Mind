# Prediction System — Architecture, Ownership & Roadmap

**Owner:** ML / Analytics Engineer
**Phase 1 scope:** Architecture review only. **No prediction behaviour changed.**

## 1. Prediction Architecture

The prediction platform is a **probabilistic forecasting pipeline** (V2) orchestrated by `services/pipeline.py`:

```
Feature Store (features/store.py)
   ↓  per-player, per-GW derived features
services/pipeline.py  (7 steps)
   1. minutes_engine          → projected minutes with rotation risk
   2. projection_engine       → base point projection with CIs
   3. regression_engine       → over/underperformance flags
   4. bookmaker_engine        → odds-based adjustment (when available)
   5. confidence_engine       → uncertainty quantification & tiering
   6. (snapshot/persistence)  → Projection ledger (append-only)
   7. opportunity_engine      → undervalued player detection
```

Every output is written to the **append-only prediction ledger** (`prediction_versions`, `projections`) with a `config_hash` and `weights_snapshot`, enabling reproducible, comparable forecasts.

### Design principles

- **One source of truth for features** — `features/store.py`.
- **Versioned config** — projection parameters live in `config/prediction/prediction_v1.yaml`; weights in `config/weights/`.
- **Append-only ledger** — forecasts are never overwritten; validation compares versions against actuals.
- **Uncertainty is explicit** — every projection carries 80%/95% confidence intervals from the confidence engine.

## 2. Engine Ownership Map

| Engine | File | Responsibility | Status |
|---|---|---|---|
| Feature Store | `features/store.py` | Derived features (single source of truth) | V2 |
| Minutes Engine | `engines/minutes_engine.py` | Minutes projection + rotation risk | V2 |
| Projection Engine | `engines/projection_engine.py` | Points projection + CIs | V2 |
| Expected Points Engine | `engines/expected_points_engine.py` | xPts/90 rate model (V3) | V3 candidate |
| Expected Minutes Engine | `engines/expected_minutes_engine.py` | Probability-weighted expected minutes (V3) | V3 candidate |
| Expected Projection Engine | `engines/expected_projection_engine.py` | V3 compositor: xPts = xPts/90 × minutes/90 | V3 candidate |
| Expected Pipeline | `services/expected_pipeline.py` | Side-by-side V2-vs-V3 comparison + persistence | V3 candidate |
| Regression Engine | `engines/regression_engine.py` | Over/underperformance detection | V2 |
| Bookmaker Engine | `engines/bookmaker_engine.py` | Odds integration | V2 |
| Confidence Engine | `engines/confidence_engine.py` | Uncertainty quantification | V2 |
| Opportunity Engine | `engines/opportunity_engine.py` | Undervalued detection | V2 |
| Market Intelligence | `engines/market_intelligence_engine.py` | Transfer/ownership trends | V2 |
| Monte Carlo Engine | `engines/monte_carlo_engine.py` | Simulation-based uncertainty | V2 |
| Squad Optimizer | `engines/squad_optimizer.py` | Budget-constrained optimization | V2 |
| Validation Engine | `engines/validation_engine.py` | Accuracy metrics, CI calibration | V2 |
| Value Engine | `engines/value_engine.py` | Value score + player rating | **V1 (legacy)** |
| Fixture Engine | `engines/fixture_engine.py` | Fixture difficulty, windows, swings | V1+V2 merged |
| Market Engine | `engines/market_engine.py` | Transfers, ownership, price trends | **V1 (legacy)** |
| Prediction Engine | `engines/prediction_engine.py` | V1 points/minutes projection | **V1 (legacy)** |
| Captain Engine | `engines/captain_engine.py` | Captaincy analysis | **V1 (legacy)** |

The V3 engines (marked *candidate*) run side-by-side with V2 and do not change
production behaviour. See `docs/expected_points.md` for the architecture, math,
minutes methodology and validation strategy.

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

1. **Consolidate V1 engines** — retire `value_engine`, `market_engine`, `prediction_engine`, `captain_engine` once V2 equivalents are proven by validation (TD-1).
2. **Single uncertainty source** — extract CI/variance computation into one module used by projection and confidence engines (TD-3).
3. **Feature Store de-duplication** — move fixture-window features fully into the Feature Store; engines consume, never recompute (TD-2).
4. **Config-driven player rating** — read `player_rating` weights from `config/weights/` (TD-4).
5. **Performance pass** — replace `iterrows()` hot loops with vectorised operations (TD-5).
6. **Validation evidence loop** — use GW1..N actuals to score engines, prioritise the highest-ROI engine improvements.
7. **Persistent freshness** — store last-refresh timestamp in the DB (TD-8).

Each item is a behaviour-preserving refactor followed by validation, not a model change.
