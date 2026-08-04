# Expected Points (xPts) — V3 Prediction Model

**Owner:** ML / Analytics Engineer
**Status:** Candidate model — runs **side-by-side** with V2, does **not** change production behaviour.

## 1. Architecture Summary

The V3 model estimates expected fantasy points as the product of a per-90
points rate and a probability-weighted minutes expectation:

```
xPts = xPts_per_90 * (expected_minutes / 90)
```

It is implemented as **three independently testable engines** plus one
orchestration service. **No existing code path is modified** — the V2 pipeline,
ledger and UI continue to run untouched. The V3 output is a *separate*
append-only prediction version that the existing validation platform can score
and compare.

| Component | File | Responsibility |
|---|---|---|
| Expected Points Engine | `engines/expected_points_engine.py` | `xPts_per_90` from underlying xGI, CS probability, bonus, saves, cards, set pieces |
| Expected Minutes Engine | `engines/expected_minutes_engine.py` | `expected_minutes` = start prob × minutes-if-starting × (1 − sub risk) |
| Expected Projection Engine | `engines/expected_projection_engine.py` | Compositor: the xPts formula, CIs, and V2-compatible output shape |
| Expected Pipeline | `services/expected_pipeline.py` | Side-by-side run: V3 + V2 baseline + alignment report + persistence |
| Config | `config/expected_points/`, `config/expected_minutes/` | Versioned parameters (registered in `config/active.yaml`) |

**Design constraints honoured:**
- **Feature Store is the single source of truth.** The new engines read only
  through `store.*` accessors (`xgi_features()`, `set_piece_features()`,
  `availability_features()`, `minutes_features()`) or `store.df`. No feature is
  recomputed in an engine.
- **No breaking API changes.** `ExpectedPlayerProjection` mirrors the V2
  `PlayerProjection` attribute names, so `insert_projections_bulk()` and
  `validate_version()` work unchanged.
- **Append-only, idempotent persistence.** Re-running the same gameweek returns
  the same version IDs.
- **Zero production behaviour change.** Nothing in `services/pipeline.py` or the
  UI is altered.

### 1.1 Data flow

```
FeatureStore
   ├── xgi_features()          ─┐
   ├── set_piece_features()     ├─→ Expected Points Engine ─→ xPts_per_90 ─┐
   ├── store.df (bps/saves/cards) ┘                                        ├─→ Expected Projection Engine → xPts
   ├── minutes_features()      ─┐                                            ─→ ExpectedPlayerProjection (V3 version)
   ├── availability_features() ├─→ Expected Minutes Engine → expected_minutes ┘
   └── store.df (status/form)  ┘
```

## 2. Math — Expected Points per 90

All event expectations are **per 90 minutes**, so they are comparable across
players regardless of minutes played. The minutes decision is deliberately left
to the Expected Minutes Engine.

```
games_played = max(1, round(season_minutes / 90))
xg_90  = season_xG  / games_played
xa_90  = season_xA  / games_played
xgc_90 = season_xGC / games_played          # team-conceded adjustment, see 2.2

xPts_per_90 =
      xg_90  × fixture_multiplier × position[goal_value]      (FPL points per goal)
    + xa_90  × fixture_multiplier × position[assist_value]
    + P(clean_sheet) × position[clean_sheet_value]
    + E[bonus]
    + E[save points]                     (GKP only)
    + E[card deductions]                 (negative)
    + set_piece_bonus                    (penalty / FK / corner primary taker)
```

The position values are the FPL scoring rules mirrored from
`config/prediction/prediction_v1.yaml` into the self-contained
`config/expected_points/expected_points_v1.yaml`.

### 2.1 Fixture multiplier

```
multiplier = (5 − difficulty) / 4,  floored at 0.5
```

Difficulty is read from the Feature Store fixture map (team's next fixture).
An easy fixture (difficulty 1) → 1.0, neutral (3) → 0.5, hard (5) → 0.5 (floor).

### 2.2 Clean-sheet probability

Anchored to the league-average team xGC/90 so an average defence lands near the
real FPL clean-sheet rate (~25%):

```
P(CS) = clip( (league_avg_xgc_90 − xgc_90_adjusted) / league_avg_xgc_90 × 0.5, 0, 0.6 )
```

`xgc_90_adjusted` blends the team's raw conceded rate with its squad strength:

```
xgc_90_adjusted = xgc_90 × (team_strength_anchor / team_strength_raw)
```

A defence stronger than the anchor concedes less than its raw xGC/90 suggests.
GKP/DEF only; MID receives the 1-pt CS value; FWD receives 0.

### 2.3 Bonus

Expected BPS per 90 converts linearly to bonus points, capped at 3:

```
E[bonus] = clip( bps_per_90 / 160, 0, 3 )
```

### 2.4 Saves and cards

```
E[save points] = clip( saves_per_90 / 2, 0, 6 )      # GKP only, 1 pt per 2 saves
E[cards]       = −( yellow_per_90 × 1 + red_per_90 × 3 )
```

### 2.5 Set-piece bonus

A primary penalty taker earns +0.25 xPts/90, FK +0.05, corner +0.05
(configurable). Flags come from the Feature Store set-piece features.

### 2.6 Final gameweek projection

```
xPts          = xPts_per_90 × (expected_minutes / 90)
```

Confidence intervals are propagated from the variance of both estimates
(rate uncertainty, minutes uncertainty, base randomness), weighted per
`variance_sources` and scaled by expected points (heteroscedastic), matching
the V2 convention. `confidence` blends the two engine confidences.

## 3. Minutes Methodology

`expected_minutes` is an **expectation**, not a point estimate of any single
outcome. It is the probability-weighted sum over the possible minutes outcomes:

```
expected_minutes = start_probability × minutes_if_starting × (1 − substitution_risk)
```

### 3.1 Start probability

```
status unavailable (i/s/u)      → 0
status doubtful (d)             → 0.40
otherwise:
  start_prob = 0.60 × starts_rate        (observed starts / games)
             + 0.40 × chance_next        (chance_of_playing_next_round)
  ± form adjustment (±0.05 for hot/cold form)
  clipped to [0.05, 0.97]
```

`starts_rate` comes from the Feature Store minutes features (starts ÷ games).
`chance_next` is the FPL-declared chance of playing next round.

### 3.2 Minutes if starting

Blend of the player's own history and a positional baseline:

```
E[minutes | start] = 0.60 × historical_minutes_per_start + 0.40 × positional_baseline
                     (history only trusted when starts ≥ 3)
positional_baseline = {GKP: 90, DEF: 88, MID: 78, FWD: 75}
```

For players with little history the positional baseline dominates, which is
the correct fallback (defenders and keepers rarely get subbed).

### 3.3 Substitution risk

```
sub_risk = 0.25 if E[minutes|start] ≥ 78   # expected to play ~90 → more likely subbed
         = 0.10 otherwise
```

### 3.4 Outputs

Each player gets `expected_minutes`, `start_probability`,
`minutes_if_starting`, `substitution_risk` and a rotation-risk label
(Low/Medium/High from start probability thresholds), plus a data-quality tier
and confidence score.

## 4. Validation Strategy

The V3 model is validated **side-by-side** with V2 through the existing
validation platform. There are two layers:

### 4.1 Pre-gameweek alignment (no actuals needed)

`run_expected_points_comparison()` runs V3 alongside the V2 baseline and
returns an in-memory alignment report:

- number of common players
- mean points for each model
- mean difference (V3 − V2) and mean absolute difference
- **correlation** between V2 and V3 rankings

This catches structural disagreement early (e.g. a position the two models rank
completely differently) before any real data is involved.

### 4.2 Post-gameweek A/B through the ledger

When `persist=True` and a DB session is provided, the V3 forecast is written as
its own append-only prediction version:

- `version_tag = "xpts-gw{id}-{config_hash[:8]}"`, `model_name = "expected_points_v1"`
- idempotent — re-running the same gameweek returns the same `version_id`
- the V2 baseline is persisted at the same time (the existing pipeline version)

Once actuals arrive, the standard flow applies with no new machinery:

1. `mark_actuals()` on both versions (or inject directly).
2. `validate_version()` on each → MAE, RMSE, bias, CI calibration per version.
3. `compare_expected_vs_baseline()` → `compare_versions()` from the validation
   engine → improvement %, per-version metrics, winner.

### 4.3 Evidence-based promotion

The engineering directive requires **evidence before adoption**. V3 becomes the
production model only after it demonstrates a sustained improvement over V2 on
real gameweeks:

- **≥ 3 gameweeks** of validation data before any weight or calibration change
- MAE and RMSE both strictly better than V2, with no bias regression
- CI coverage within tolerance (80% interval covering ~80%, 95% covering ~95%)
- consistency across positions (no single-position regression paying for a
  headline gain)

Until then V3 remains a shadow candidate — computed, validated and compared,
but never wired into the UI or the existing pipeline.

## 5. Bug fix note

`features/store.py` had a latent bug in `_build_minutes_features()`
(`df["minutes_season"]` instead of `f["minutes_season"]`). It was never hit by
the V2 pipeline because `compute_minutes_features()` reads `store.df` directly
instead of the accessor. The V3 engine uses the accessor, so the typo was fixed.
Behaviour is unchanged for the existing pipeline; `store.minutes_features()` now
works as documented.

## 6. Comparison & Explainability Layer

A scientific-validation UI layer wraps the shadow-model comparison so that
**every** V2-vs-V3 claim is backed by evidence and every V3 forecast is
explainable. This is evaluation infrastructure only — it adds no prediction
logic and touches no production path.

| Component | File | Responsibility |
|---|---|---|
| Comparison Reports | `services/comparison_reports.py` | Largest disagreements, agreement rates, captain/transfer/undervalued differences, evidence bridge, insights |
| Comparison Dashboard | `pages/8_Model_Comparison.py` | Streamlit UI: evidence banner, alignment metrics, scatter, disagreement table, explainability panel, evidence ladder |
| Tests | `tests/test_comparison_reports.py` | 14 tests covering ranking, agreement, recommendation differences, evidence thresholds, full report + persistence |

### 6.1 Report structure

`build_comparison_report()` runs V3 alongside V2 (via the Expected Pipeline) and
produces a single `ComparisonReport`:

- **alignment** — correlation, mean/mean-absolute difference (from
  `compare_to_v2`).
- **disagreements** — the top-N players by `|V3 − V2|`, each with direction
  (`v3_higher`/`v3_lower`) and the V3 `contributing_factors` that explain *why*
  (minutes factor, start probability, rotation risk, data quality).
- **agreement** — overall rate and per-position rate of `|V3 − V2| ≤ threshold`
  (default ±0.75 pts).
- **captain / transfers / undervalued** — the same recommendation logic
  (`rank_captains`, `find_transfer_opportunities`, `find_undervalued_players`)
  re-run against each model's projections, plus shared-pick counts.
- **evidence** — the number of gameweeks where **both** versions were validated,
  mapped through the learning-service threshold framework.
- **insights** — human-readable sentences generated from the above.

### 6.2 Evidence-threshold bridge

`evidence_status(n_validated_gameweeks)` is the single bridge to
`services/learning_service.py` thresholds:

| Level | Gameweeks | Meaning |
|---|---|---|
| weak | 1 | Preliminary — could be noise. Observe only. |
| needs_more_data | 2 | Early signal — not yet reliable. |
| moderate | 3–4 | Consistent pattern emerging — monitor. |
| strong | 5+ | Reliable pattern (requires consistency ≥ 0.6). |
| statistically_significant | 10+ | High confidence — actionable. |

The dashboard renders this as an evidence **ladder**; reaching the next tier is
always explicit (`gameweeks_to_next_level`) and promotion is never automatic.

### 6.3 Explainability panel

For any player, the panel shows:

- the headline `xPts` plus the formula inputs: `xPts_per_90`,
  `expected_minutes`, `minutes_factor`, `start_probability`, `rotation_risk`.
- the component breakdown (goals, assists, clean-sheet, bonus, other).
- `confidence`, data-quality tier, and the 80%/95% confidence intervals.

This satisfies the requirement that a V3 forecast is never a black box: when V3
disagrees with V2, the driver (usually the minutes model) is visible per player.

### 6.4 How to run

```bash
python -m pytest tests/test_comparison_reports.py   # 14 tests

streamlit run app.py                                # then open "Model Comparison"
```

In the dashboard: pick a gameweek, optionally check **Persist V3 version to
ledger**, then **Run Comparison**. The report, evidence banner, disagreements,
explainability panel and recommendation differences render below. To feed the
evidence counter, validate both versions in the Model Analytics page after
actuals are ingested.
