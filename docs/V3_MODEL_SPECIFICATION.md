# V3 Model Specification — Expected Points (xPts)

> **Status**: Production Primary (GW1+)
> **Ledger Model ID**: `expected_points_v1`
> **Shadow Models**: `projection_v2` (V2), `v3_hist_d_team` (Model D)
> **Last Updated**: 2026-08-20
> **Source Commit**: Reverse-engineered from codebase — all line references checked against current HEAD

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Core Formula](#2-core-formula)
3. [Expected Points Engine (xPts/90)](#3-expected-points-engine-xpts90)
4. [Expected Minutes Engine](#4-expected-minutes-engine)
5. [Expected Projection Engine (Compositor)](#5-expected-projection-engine-compositor)
6. [Feature Store (Inputs)](#6-feature-store-inputs)
7. [Configuration Files](#7-configuration-files)
8. [Data Flow Pipeline](#8-data-flow-pipeline)
9. [Persistence Layer](#9-persistence-layer)
10. [Primary/Shadow Dispatch](#10-primaryshadow-dispatch)
11. [Confidence & Variance](#11-confidence--variance)
12. [Position-Specific Scoring](#12-position-specific-scoring)
13. [Fixture Multiplier](#13-fixture-multiplier)
14. [Team Strength Adjustment](#14-team-strength-adjustment)
15. [Empirical Calibration (Hist Configs)](#15-empirical-calibration-hist-configs)
16. [Evidence Layer Integration](#16-evidence-layer-integration)
17. [NaN / Missing Data Behavior](#17-nan--missing-data-behavior)
18. [Failure Modes](#18-failure-modes)
19. [Model Assumptions](#19-model-assumptions)
20. [Decision Intelligence Boundary](#20-decision-intelligence-boundary)
21. [Validation Framework](#21-validation-framework)
22. [Known Issues & Limitations](#22-known-issues--limitations)

---

## 1. Architecture Overview

V3 decomposes FPL point prediction into **two independent engines** that are composed:

```
┌─────────────────────┐    ┌─────────────────────┐
│  Expected Points     │    │  Expected Minutes    │
│  Engine (xPts/90)    │    │  Engine              │
│                      │    │                      │
│  Reads: xGI, BPS,   │    │  Reads: starts,      │
│  saves, cards, set-  │    │  minutes, status,    │
│  pieces, team str,   │    │  chance_of_playing,  │
│  fixture difficulty  │    │  form                │
└──────────┬──────────┘    └──────────┬──────────┘
           │                          │
           ▼                          ▼
    ┌──────────────────────────────────────┐
    │     Expected Projection Engine       │
    │     (Compositor)                     │
    │                                      │
    │  xPts = xPts_per_90 × (E[min] / 90)│
    └──────────────────┬───────────────────┘
                       │
                       ▼
              ExpectedPlayerProjection
              (mirrors V2 PlayerProjection
               for ledger compatibility)
```

**Key design principle**: The points engine projects *rates* (per-90), the minutes engine projects *volume* (probability-weighted minutes). They are statistically independent — neither engine's output affects the other.

**Why two engines?** V2 projected raw event counts (goals, assists, CS) scaled by minutes — coupling rate estimation with volume estimation in one pipeline. V3 decouples them so each can be calibrated, validated, and debugged independently.

---

## 2. Core Formula

The final gameweek projection:

```
xPts = xPts_per_90 × (expected_minutes / 90)
```

- `xPts_per_90`: from Expected Points Engine (`engines/expected_points_engine.py:208-216`)
- `expected_minutes`: from Expected Minutes Engine (`engines/expected_minutes_engine.py:164-167`)
- Applied in compositor at `engines/expected_projection_engine.py:145`

---

## 3. Expected Points Engine (xPts/90)

**File**: `engines/expected_points_engine.py` (485 lines)
**Entry point**: `project_expected_points()` (line 69)
**Config**: `config/expected_points/expected_points_v1.yaml`

### 3.1 xPts/90 Summation

Computed at lines 208-216:

```
xpts_per_90 = (
    xg_90 × fixture_multiplier × position.goal
  + xa_90 × fixture_multiplier × position.assist
  + clean_sheet_prob × position.clean_sheet
  + expected_bonus
  + expected_saves
  + expected_cards          # negative value
  + set_piece_bonus
)
xpts_per_90 = max(xpts_per_90, 0.0)   # floor at zero (line 217)
```

### 3.2 Component: xG/90 and xA/90

**Lines 119-120**:
```
xg_90 = xg_raw / games_played
xa_90 = xa_raw / games_played
```

Where:
- `xg_raw` = `store.xgi_features()["xg_raw"]` (FeatureStore fills NaN → 0)
- `games_played = max(1, int(minutes_season / 90))` (line 286-288)

**Empirical scaling** (lines 124-129): When `empirical.finishing` config is present:
```
xg_90 *= finishing[position]   # e.g. MID: 1.131
xa_90 *= creative[position]   # e.g. MID: 1.508
```

**Evidence layer override** (lines 136-148): If `ev_xg_per_90` and `ev_xa_per_90` columns are present (injected by `research/evidence.py` in ablation studies only — never in production):
```
xg_90 = ev_xg_per_90 × ev_team_attack_mult
xa_90 = ev_xa_per_90 × ev_team_attack_mult
xgc_90 *= ev_team_defense_mult
```

**Previous-season shrinkage** (lines 150-159): When evidence is inactive and `games_played < min_current_games` (default 3):
```
xg_90 = (1 - prev_weight) × xg_90 + prev_weight × hist_prev_xg_per_90
xa_90 = (1 - prev_weight) × xa_90 + prev_weight × hist_prev_xa_per_90
```
`prev_weight` default: 0.35 (hist config).

**Historical team adjustment** (lines 162-170): When `empirical.historical_team` config is present:
```
xg_90 *= 1 - attack_weight + attack_weight × hist_team_attack_adj
xa_90 *= 1 - attack_weight + attack_weight × hist_team_attack_adj
xgc_90 *= 1 - defense_weight + defense_weight × hist_team_defense_adj
```

### 3.3 Component: xGC/90 (Expected Goals Conceded)

**Line 121**: `xgc_90 = xgc_raw / games_played`

**Team strength adjustment** (lines 310-324, only when evidence is inactive):
```
xgc_90_adjusted = xgc_90 × (team_strength_anchor / team_strength_raw)
```
- `team_strength_anchor` = 1000 (config `clean_sheet.team_strength_anchor`)
- `team_strength_raw` = `(strength_overall_home + strength_overall_away) / 2` (scoring.py:63-65)
- If `team_strength_raw <= 0`: returns raw `xgc_90` (no adjustment)

### 3.4 Component: Clean Sheet Probability

**Lines 177-181**: Only computed for GKP and DEF. MID and FWD get `clean_sheet_prob = 0.0`.

**Empirical model** (lines 338-346): When `empirical.clean_sheet` config exists:
```
cs_prob = clip(intercept + slope × xgc_90, min_prob, max_prob)
```
Defaults from hist config (GKP/DEF/MID/FWD all share same):
- `intercept` = 0.6103
- `slope` = -0.1564
- `min_prob` = 0.0
- `max_prob` = 0.6

**Default model** (lines 348-353): Anchored to league average:
```
cs_prob = clip((league_avg_xgc_per_90 - xgc_90) / league_avg_xgc_per_90 × cs_rate_multiplier, 0, max_prob)
```
- `league_avg_xgc_per_90` = 1.4
- `cs_rate_multiplier` = 0.5
- An average team (xgc_90 = 1.4) gets cs_prob ≈ 0.0

### 3.5 Component: Expected Bonus

**Lines 184-189**:
```
bps_per_90 = bps_raw / games_played   (or ev_bps_per_90 if present)
expected_bonus = clip(bps_per_90 / bps_per_bonus_point, 0, max_bonus_points)
```
- `bps_per_bonus_point` = 160.0
- `max_bonus_points` = 3.0

**Empirical model** (lines 369-377): When `empirical.bonus[position]` has `slope`:
```
expected_bonus = clip(intercept + slope × bps_per_90, 0, max_bonus_points)
```

### 3.6 Component: Expected Saves (GKP only)

**Lines 191-192, 385-393**:
```
expected_saves = clip(saves_per_90 / saves_per_bonus_point, 0, max_saves_per_90)
```
- Only applies when `position == "GKP"`, else 0.0
- `saves_per_bonus_point` = 2.0
- `max_saves_per_90` = 6.0

### 3.7 Component: Expected Cards

**Lines 194-200, 396-404**:
```
expected_cards = -(yellow_per_90 × yellow_weight × 1.0 + red_per_90 × red_weight × 3.0)
```
- `yellow_card_rate_weight` = 1.0 (1 point deduction per yellow)
- `red_card_rate_weight` = 1.0 (3 points deduction per red)

### 3.8 Component: Set Piece Bonus

**Lines 202, 407-420**:
```
set_piece_bonus = 0
if is_penalty_taker: set_piece_bonus += 0.25
if is_fk_taker:      set_piece_bonus += 0.05
if is_corner_taker:  set_piece_bonus += 0.05
```

---

## 4. Expected Minutes Engine

**File**: `engines/expected_minutes_engine.py` (478 lines)
**Entry point**: `project_expected_minutes()` (line 62)
**Config**: `config/expected_minutes/expected_minutes_v1.yaml`

### 4.1 Core Formula (Standard Mode)

**Lines 164-167**:
```
expected_minutes = start_prob × minutes_if_starting × (1 - substitution_risk)
expected_minutes = clip(expected_minutes, 0.0, 90.0)
```

### 4.2 Core Formula (Historical Mode)

**Lines 431-434** (when `historical_minutes.enabled = true`, i.e. hist configs):
```
expected_minutes = start_prob × min_if_start + (1 - start_prob) × sub_rate × min_if_sub
expected_minutes = clip(expected_minutes, 0.0, 90.0)
```

This adds the "came off the bench" branch that the standard model ignores.

### 4.3 Start Probability

**Standard mode** (`_compute_start_probability`, lines 233-264):

```
if status in ["i", "s", "u"]:  return 0.0
if status == "d":              return 0.40

prob = starts_rate × history_weight + chance_next × chance_weight

if form >= 6.0:  prob += 0.05    # high form boost
if form < 2.0:   prob -= 0.05    # low form penalty

prob = clip(prob, 0.05, 0.97)
```

- `history_weight` = 0.60
- `chance_of_playing_weight` = 0.40

**Historical mode** (`_compute_historical_expected_minutes`, lines 301-399):

Uses **Beta-binomial posterior** when `hist_starts` and `hist_appearances` are available:
```
observed = (alpha + hist_starts) / (alpha + beta + hist_appearances)
```

Falls back to fixed-weight blend toward position prior:
```
observed = 0.8 × starts_rate + 0.2 × start_rate_prior
```

Then blends with `chance_of_playing_next_round`:
```
start_prob = observed × (1 - 0.40) + chance_next × 0.40
start_prob = clip(start_prob, 0.03, 0.97)
```

### 4.4 Minutes If Starting

**Standard mode** (`_compute_minutes_if_starting`, lines 267-285):

```
if starts < 3 or minutes_per_game <= 0:
    return positional_baseline    # GKP=90, DEF=88, MID=78, FWD=75

blended = 0.6 × minutes_per_game + 0.4 × positional_baseline
return clip(blended, 0, 90)
```

**Historical mode** (lines 401-414):
- Uses `positional.min_if_start` from hist config (empirically fit per position)
- When `ev_minutes_per_start` is present (evidence mode): uses it directly if `starts >= 1`
- Otherwise blends with history: `0.6 × minutes_per_game + 0.4 × min_if_start`

### 4.5 Substitution Risk

**Lines 288-298**:
```
if minutes_if_starting >= 78:
    return max(0.10, 0.25)     # = 0.25 (full 90-min player more likely to be subbed)
else:
    return 0.10                 # baseline risk
```

### 4.6 Sub Rate (Historical Mode Only)

**Lines 416-422**:
```
sub_rate = 0.7 × player_sub_rate + 0.3 × positional_sub_rate_prior
sub_rate = clip(sub_rate, 0, 1)
```

Positional priors from hist config:
| Position | sub_rate_given_not_start | min_if_sub |
|----------|--------------------------|------------|
| GKP | 0.0436 | 83.0 min |
| DEF | 0.1614 | 42.0 min |
| MID | 0.2501 | 30.6 min |
| FWD | 0.2570 | 26.5 min |

### 4.7 Rotation Risk Classification

**Lines 438-449**:
```
start_prob < 0.30  → "High"
start_prob < 0.60  → "Medium"
start_prob >= 0.60 → "Low"
```

---

## 5. Expected Projection Engine (Compositor)

**File**: `engines/expected_projection_engine.py` (320 lines)
**Entry point**: `run_expected_projection()` (line 84)
**Output**: `list[ExpectedPlayerProjection]`

### 5.1 Composition

**Lines 142-157**:
```
minutes_factor = expected_minutes / 90.0
projected_points = xpts_per_90 × minutes_factor

goals_proj       = xg_90 × minutes_factor × fixture_multiplier
assists_proj     = xa_90 × minutes_factor × fixture_multiplier
clean_sheet_proj = clean_sheet_prob × position.clean_sheet × minutes_factor
bonus_proj       = expected_bonus × minutes_factor
other_proj       = (expected_saves + expected_cards + set_piece_bonus) × minutes_factor
```

### 5.2 CI Construction

**Lines 170-190**:
```
std_dev = sqrt(max(variance, 0.0))

ci_80_low  = max(0, projected_points - 1.28 × std_dev)
ci_80_high = projected_points + 1.28 × std_dev
ci_95_low  = max(0, projected_points - 1.96 × std_dev)
ci_95_high = projected_points + 1.96 × std_dev
```

Low bounds are floored at 0 (a player cannot score negative FPL points).

### 5.3 Overall Confidence

**Lines 295-306**:
```
blended = 0.5 × rate_confidence + 0.5 × minutes_confidence
if projected_points >= 5:  blended += 5
if projected_points <= 2:  blended -= 5
confidence = clip(blended, 10, 95)
```

### 5.4 Data Quality Merge

**Lines 309-312**: Takes the more conservative (lower) of the two engines' quality tiers:
```
rank = {"none": 0, "limited": 1, "moderate": 2, "good": 3}
merged = min(rate_quality, minutes_quality) by rank
```

---

## 6. Feature Store (Inputs)

**File**: `features/store.py` (500 lines)
**Entry point**: `build_feature_store()` (line 413)

The FeatureStore is built once per snapshot cycle. It normalizes all raw FPL data and provides typed accessors. No engine computes features directly.

### 6.1 Feature Categories

| Category | Accessor | Key Columns | NaN Default |
|----------|----------|-------------|-------------|
| Minutes | `minutes_features()` | `minutes_season`, `minutes_per_game`, `starts_rate`, `starts` | 0, 0, 0.0, 0 |
| xGI | `xgi_features()` | `xg_raw`, `xa_raw`, `xgi_raw`, `xgc_raw`, `xgi_per_90` | 0, 0, 0, 0, 0 |
| Fixture | `fixture_features()` | `fixture_avg_1gw/3gw/6gw`, `home_count_next_3`, `fixture_swing` | 3.0, 3.0, 3.0, 1, 0.0 |
| Value | `value_features()` | `price`, `points_per_million`, `cost_change_start/event` | 0, 0, 0, 0 |
| Market | `market_features()` | `selected_by_percent`, `net_transfers`, `ownership_tier` | 0, 0, "differential" |
| Availability | `availability_features()` | `status`, `is_fit`, `chance_next`, `chance_this` | "a", 1.0, 1.0, 1.0 |
| Set Piece | `set_piece_features()` | `is_penalty_taker`, `is_fk_taker`, `is_corner_taker` | 0, 0, 0 |
| Trend | `trend_features()` | `form`, `influence`, `creativity`, `threat`, `ict_index` | 0, 0, 0, 0, 0 |

### 6.2 Derived Columns (scoring.py)

`add_derived_columns()` at `services/scoring.py:28-79`:

| Column | Formula | NaN Behavior |
|--------|---------|-------------|
| `xgi_per_90` | `xgi / minutes × 90` (0 if minutes=0) | NaN minutes → 0 |
| `points_per_million` | `total_points / price` (0 if price=0) | NaN price → 0 |
| `minutes_fraction` | `minutes / MAX_SEASON_MINUTES × 100` | **No fillna** — NaN propagates |
| `team_strength_raw` | `(home.fillna(100) + away.fillna(100)) / 2` | 100.0 |
| `fixture_score_raw` | Weighted fixture difficulty (50.0 if no fixture_map) | 50.0 |
| `set_piece_raw` | Composite FK/penalty/corner score | 50.0 |

---

## 7. Configuration Files

### 7.1 Active Configs (`config/active.yaml`)

```yaml
active_versions:
  expected_points: expected_points_v1
  expected_minutes: expected_minutes_v1
```

### 7.2 Production Config (`config/production/production_v1.yaml`)

```yaml
primary_model: expected_points_v1
shadow_models:
  - projection_v2
  - v3_hist_d_team
```

### 7.3 Points Config Values (`expected_points_v1.yaml`)

| Section | Key | Value | Purpose |
|---------|-----|-------|---------|
| `position_values.MID.goal` | | 5 | FPL goal points for midfielders |
| `position_values.DEF.clean_sheet` | | 4 | FPL CS points for defenders |
| `clean_sheet.league_avg_xgc_per_90` | | 1.4 | Average team xGC/90 |
| `clean_sheet.cs_rate_multiplier` | | 0.5 | CS prob scaling factor |
| `clean_sheet.team_strength_anchor` | | 1000 | Anchor for strength regression |
| `bonus.bps_per_bonus_point` | | 160.0 | BPS threshold per bonus point |
| `bonus.max_bonus_points` | | 3.0 | Maximum bonus per match |
| `saves.saves_per_bonus_point` | | 2.0 | Saves per save point |
| `set_pieces.penalty_taker_bonus` | | 0.25 | xPts/90 bonus for PK taker |
| `set_pieces.fk_taker_bonus` | | 0.05 | xPts/90 bonus for FK taker |
| `set_pieces.corner_taker_bonus` | | 0.05 | xPts/90 bonus for corner taker |
| `fixture.base_difficulty` | | 3 | Default fixture difficulty |
| `fixture.floor_multiplier` | | 0.5 | Minimum fixture multiplier |
| `confidence_intervals.ci_80_z` | | 1.28 | Z-score for 80% CI |
| `confidence_intervals.ci_95_z` | | 1.96 | Z-score for 95% CI |
| `variance_sources.rate` | | 0.40 | Weight: rate uncertainty |
| `variance_sources.minutes` | | 0.35 | Weight: minutes uncertainty |
| `variance_sources.base` | | 0.25 | Weight: inherent randomness |
| `confidence.none` | | 20 | Confidence score: no data |
| `confidence.limited` | | 40 | Confidence score: limited data |
| `confidence.moderate` | | 60 | Confidence score: moderate data |
| `confidence.good` | | 75 | Confidence score: good data |

### 7.4 Minutes Config Values (`expected_minutes_v1.yaml`)

| Section | Key | Value |
|---------|-----|-------|
| `minutes_if_starting.GKP` | | 90 |
| `minutes_if_starting.DEF` | | 88 |
| `minutes_if_starting.MID` | | 78 |
| `minutes_if_starting.FWD` | | 75 |
| `start_probability.history_weight` | | 0.60 |
| `start_probability.chance_of_playing_weight` | | 0.40 |
| `start_probability.doubtful_prob` | | 0.40 |
| `start_probability.high_form_boost` | | 0.05 |
| `start_probability.low_form_penalty` | | 0.05 |
| `start_probability.max_start_prob` | | 0.97 |
| `start_probability.min_start_prob` | | 0.05 |
| `substitution.baseline_risk` | | 0.10 |
| `substitution.high_minutes_threshold` | | 78 |
| `substitution.risk_if_expected_full` | | 0.25 |
| `history.min_starts_for_history` | | 3 |
| `history.history_blend` | | 0.6 |
| `history.base_blend` | | 0.4 |
| `confidence.none` | | 25 |
| `confidence.limited` | | 45 |
| `confidence.moderate` | | 65 |
| `confidence.good` | | 80 |
| `rotation_risk.high_threshold` | | 0.30 |
| `rotation_risk.medium_threshold` | | 0.60 |

---

## 8. Data Flow Pipeline

```
FPL Bootstrap API
    │
    ▼
get_players_dataframe()
    │
    ▼
add_derived_columns()          ← scoring.py:28 (xgi/90, team_strength, fixture_score, set_piece_raw)
    │
    ▼
build_feature_store()          ← features/store.py:413 (normalizes, fills NaN, builds 8 feature categories)
    │
    ├──────────────────────────────────────────────────────────┐
    ▼                                                          ▼
project_expected_points()     project_expected_minutes()
  ← expected_points_engine.py:69    ← expected_minutes_engine.py:62
    │                                                          │
    ▼                                                          ▼
list[ExpectedPointsProjection]  list[ExpectedMinutesProjection]
    │                                                          │
    └──────────────────────┬───────────────────────────────────┘
                           ▼
               compose_expected_projections()
                 ← expected_projection_engine.py:113
                           │
                           ▼
               list[ExpectedPlayerProjection]
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
        persist_expected_version()   Decision engines
          ← expected_pipeline.py:145   (assistant manager,
                                       league intelligence,
                                       chat assistant)
```

---

## 9. Persistence Layer

**File**: `services/expected_pipeline.py` (231 lines)

### 9.1 Persistence Flow

`persist_expected_version()` (line 145):
1. Compute `config_hash = SHA-256 of expected_points config`
2. Compute `version_tag = f"xpts-gw{gameweek_id}-{config_hash[:8]}"` (expected_points_engine.py:270)
3. Check idempotency: if `version_tag` exists in DB, return existing `version_id`
4. Call `persist_predictions_only()` → writes `PredictionVersion` + `Prediction` rows
5. Return `version_id`

### 9.2 Ledger Schema

Each run creates:
- **PredictionVersion** row: `model_name`, `version_tag`, `gameweek_id`, `config_hash`, `created_at`
- **Prediction** rows: one per player: `player_id`, `projected_points`, `ci_80_low`, `ci_80_high`, etc.

**Append-only**: Nothing is ever updated or deleted.

### 9.3 Known Bug (O1 from GW1 Audit)

`compute_expected_points_version_tag()` at `expected_points_engine.py:270` does NOT include `model_name` in the tag:
```python
return f"xpts-gw{gameweek_id}-{config_hash[:8]}"
```
This means if primary and shadow use configs with the same `config_hash`, they generate the same `version_tag`, causing the shadow's persistence to be skipped by the idempotency guard. In practice, primary uses `expected_points_v1.yaml` and shadow uses `expected_points_v1_hist.yaml` which have different hashes — so this bug is currently masked.

---

## 10. Primary/Shadow Dispatch

**File**: `services/production_predictor.py` (323 lines)

### 10.1 Dispatch Logic

`run_production_predictions()` (line 112):
1. Load `primary_model_id` from `get_primary_model_id()` → `"expected_points_v1"`
2. Run primary via `run_model()`
3. Load `shadow_model_ids` from `get_shadow_model_ids()` → `["projection_v2", "v3_hist_d_team"]`
4. Run each shadow via `run_model()`

`run_model()` (line 189) dispatches by model_id:
- `"expected_points_v1"` → `_run_expected_points()` (line 236) — calls `run_expected_projection()`
- `"projection_v2"` → `_run_projection_v2()` (line 263) — calls V2 pipeline
- `"v3_hist_d_team"` → `_run_v3_hist_d_team()` (line 293) — calls `run_expected_projection()` with hist config versions

### 10.2 Model D (Shadow) Specifics

`_run_v3_hist_d_team()` (lines 293-323):
```python
projections = run_expected_projection(
    store, gameweek_id,
    points_version="expected_points_v1_hist",
    minutes_version="expected_minutes_v1_hist",
)
```
Persists with `model_name="v3_hist_d_team"`.

---

## 11. Confidence & Variance

### 11.1 Per-Engine Confidence

**xPts engine** (lines 220-221, 423-452):
Counts data sources: minutes > 0, xgi > 0, bps > 0, form > 0, status == "a"
```
≥ 4 sources → "good" (75)
≥ 3 sources → "moderate" (60)
≥ 1 sources → "limited" (40)
0 sources   → "none" (20)
```

**Minutes engine** (lines 452-474):
Counts: minutes > 0, starts > 0, chance_next > 0, status == "a"
```
≥ 3 sources → "good" (80)
2 sources   → "moderate" (65)
1 source    → "limited" (45)
0 sources   → "none" (25)
```

### 11.2 Variance Model

`_compute_variance()` at `expected_projection_engine.py:264-292`:

```
rate_uncertainty = 1 - (rate_confidence / 100)
minutes_uncertainty = 1 - (minutes_confidence / 100)
base_randomness = 0.4

raw_variance = 0.40 × rate_uncertainty + 0.35 × minutes_uncertainty + 0.25 × base_randomness
total_variance = raw_variance × max(projected_points, 1.0) × quality_multiplier
```

**Quality multipliers** (for CI width):
| Quality | Multiplier |
|---------|-----------|
| none | 1.5 |
| limited | 1.2 |
| moderate | 1.0 |
| good | 0.8 |

Variance scales with expected points (heteroscedastic) — high-xPts players have wider CIs in absolute terms.

---

## 12. Position-Specific Scoring

FPL scoring values from `expected_points_v1.yaml:7-37`:

| Position | Goal | Assist | Clean Sheet | Yellow | Red |
|----------|------|--------|-------------|--------|-----|
| GKP | 10 | 3 | 1 | -1 | -3 |
| DEF | 6 | 3 | 4 | -1 | -3 |
| MID | 5 | 3 | 1 | -1 | -3 |
| FWD | 4 | 3 | 0 | -1 | -3 |

These are standard FPL values — not model parameters. They are defined locally in the xPts config to keep it self-contained.

---

## 13. Fixture Multiplier

`_fixture_multiplier()` at `expected_points_engine.py:296-307`:

```
multiplier = (5 - difficulty) / 4.0
multiplier = max(multiplier, floor_multiplier)
```

| Difficulty | Multiplier |
|------------|-----------|
| 1 (easiest) | 1.00 |
| 2 | 0.75 |
| 3 (average) | 0.50 (hits floor) |
| 4 | 0.50 (floor) |
| 5 (hardest) | 0.50 (floor) |

**Note**: The formula produces values in [0.5, 1.0]. All teams have multiplier ≤ 1.0, which systematically suppresses xPts for harder fixtures. Difficulty 3 is the breakpoint where the floor activates.

---

## 14. Team Strength Adjustment

`_team_strength_adjust()` at `expected_points_engine.py:310-324`:

```
xgc_90_adjusted = xgc_90 × (1000 / team_strength_raw)
```

- Only applied when evidence layer is inactive
- Only affects `xgc_90` (goals conceded rate), not xG/xA
- Teams stronger than 1000 (anchor) have their xGC reduced
- Teams weaker than 1000 have their xGC increased
- If `team_strength_raw ≤ 0`: no adjustment, raw xGC used

---

## 15. Empirical Calibration (Hist Configs)

The `_hist` config variants add empirically-fitted parameters trained on 2022-23 through 2024-25 seasons.

### 15.1 Points Hist Additions (`expected_points_v1_hist.yaml`)

**Finishing multipliers** (scale xG by position):
| Position | Multiplier |
|----------|-----------|
| GKP | 1.000 |
| DEF | 0.932 |
| MID | 1.131 |
| FWD | 1.094 |

**Creative multipliers** (scale xA by position):
| Position | Multiplier |
|----------|-----------|
| GKP | 1.600 |
| DEF | 1.302 |
| MID | 1.508 |
| FWD | 1.600 |

**Bonus models** (linear: `intercept + slope × bps_per_90`):
| Position | Intercept | Slope |
|----------|-----------|-------|
| GKP | -0.116 | 0.02298 |
| DEF | 0.1566 | 0.00094 |
| MID | 0.1203 | 0.00416 |
| FWD | 0.0051 | 0.02059 |

**Clean sheet models** (same for all positions):
```
cs_prob = clip(0.6103 + (-0.1564) × xgc_90, 0.0, 0.6)
```

**Previous-season shrinkage**: `prev_weight = 0.35` when `games_played < 3`
**Historical team**: `attack_weight = 0.5`, `defense_weight = 0.5`

### 15.2 Minutes Hist Additions (`expected_minutes_v1_hist.yaml`)

**Positional parameters** (Beta-binomial priors):
| Position | start_rate_prior | alpha | beta | min_if_start | min_if_sub | sub_rate |
|----------|-----------------|-------|------|-------------|-----------|----------|
| GKP | 0.2213 | 0.142 | 0.518 | 89.5 | 83.0 | 0.044 |
| DEF | 0.2943 | 0.355 | 0.896 | 85.4 | 42.0 | 0.161 |
| MID | 0.2647 | 0.317 | 0.916 | 80.0 | 30.6 | 0.250 |
| FWD | 0.2193 | 0.279 | 1.051 | 79.1 | 26.5 | 0.257 |

**Start prior blend weight**: 0.8 (fallback when no hist data)
**Sub blend weight**: 0.7
**Previous-season**: `prev_weight = 0.3` when `current_starts < 3`

---

## 16. Evidence Layer Integration

**File**: `research/evidence.py`

The evidence layer (`config/evidence/evidence_v1.yaml`) is **NOT** in the active config (`config/active.yaml`). It is only used during ablation studies (Model G) and is injected via research backtest columns (`ev_*`), never via production FeatureStore.

When `ev_*` columns are present:
- `ev_xg_per_90`, `ev_xa_per_90` override raw xG/xA rates
- `ev_team_attack_mult`, `ev_team_defense_mult` override team adjustments
- `ev_minutes_per_start` overrides minutes-if-starting calculation
- `ev_w_starting`, `ev_prior_starts_rate` override start probability blend

When `ev_*` columns are absent (production): all evidence paths are skipped. The engine falls through to the standard/historical path.

**Ablation verdict**: Model G (D + evidence) did NOT beat Model D. Evidence layer is documented as a negative result. Not registered as shadow candidate.

---

## 17. NaN / Missing Data Behavior

### 17.1 FeatureStore Defaults

All NaN values are handled at the FeatureStore layer with `fillna()`. Engines should never see NaN.

| Input | Default | Optimistic? |
|-------|---------|------------|
| `minutes` | 0 | Neutral |
| `expected_goals` | 0 | Conservative |
| `expected_assists` | 0 | Conservative |
| `expected_goals_conceded` | 0 | Optimistic (concedes 0) |
| `status` | "a" (available) | **Optimistic** |
| `chance_of_playing_next_round` | 100 → 1.0 | **Optimistic** |
| `form` | 0 | Conservative |
| `bps` | 0 | Conservative |
| `saves` | 0 | Conservative |
| `yellow_cards` | 0 | Conservative |
| `penalties_order` | 99 (not a taker) | Neutral |

**Critical**: Missing `status` or `chance_of_playing_next_round` treats the player as **fully available**. This is an optimistic default — a brand new player with no FPL history gets a start probability driven entirely by the positional prior and chance_next = 1.0.

### 17.2 Engine-Level Behavior

| Scenario | xPts Engine | Minutes Engine |
|----------|------------|----------------|
| `xg_raw` is NaN | → 0 via FeatureStore fillna | N/A |
| `bps` is NaN | → 0, expected_bonus = 0 | N/A |
| `saves` is NaN | → 0, expected_saves = 0 | N/A |
| `yellow_cards` is NaN | → 0, no card penalty | N/A |
| `form` is NaN | → 0, no effect on xpts (affects data_quality tier) | Affects start_prob via form thresholds |
| `team_id` not in fixture_map | difficulty = 3, multiplier = 0.5 (floor) | N/A |
| `team_strength_raw` = 0 | No xGC adjustment, raw xGC used | N/A |
| `starts` = 0 | N/A | start_prob driven by chance_next; minutes_if_starting = positional baseline |
| `minutes` = 0 | games_played = 1, rates = raw values | minutes_per_game = 0, falls back to baseline |
| `chance_of_playing_next_round` = NaN | N/A | → 1.0 (FeatureStore default) |

---

## 18. Failure Modes

### 18.1 Engine Failure Isolation

Each model run is wrapped in try/except in `production_predictor.py`:
```python
except Exception as exc:
    logger.warning("V3 expected-points projection failed: %s", exc)
    return ModelRun(model_id="expected_points_v1", error=str(exc))
```
A failed primary does NOT crash the app. The `ModelRun.error` field captures the exception. The assistant manager degrades gracefully.

### 18.2 Persistence Failure

If `session.commit()` fails after writing predictions, the predictions are lost for that run. There is **no rollback protection** — a commit failure means the append-only write is silently lost. The next run will re-generate and re-persist (the version_tag idempotency guard only prevents *duplicate* writes, not missing ones).

### 18.3 Empty Fixture Map

If `fixture_map` is empty (no fixtures loaded):
- `_fixture_multiplier()` returns 0.5 (the floor) for all players
- `_build_fixture_features()` returns defaults: avg_1gw=3.0, avg_3gw=3.0, etc.
- All players get the same (minimum) fixture boost

### 18.4 Zero Minutes Season

If a player has 0 season minutes:
- `games_played = max(1, 0) = 1`
- All per-90 rates are just the raw totals (not divided by actual games)
- Minutes engine: `minutes_per_game = 0`, falls to positional baseline

---

## 19. Model Assumptions

### 19.1 Explicit Assumptions

1. **Rate stationarity**: Per-90 rates (xG/90, xA/90) from the season so far are representative of future performance
2. **Independence**: xPts/90 and expected_minutes are estimated independently
3. **Linear fixture effect**: Fixture difficulty affects goal/assist rates linearly via `(5-diff)/4`
4. **League-average anchor**: Team strength is regressed toward a league anchor of 1000
5. **Normal CIs**: Confidence intervals assume normally distributed errors (z=1.28 for 80%, z=1.96 for 95%)
6. **Additive components**: xPts/90 is a sum of independent point sources (goals, assists, CS, bonus, saves, cards, set pieces)

### 19.2 Implicit Assumptions

1. **No opponent modeling**: Fixture difficulty is a single integer (1-5), not a full opponent profile
2. **No tactical context**: The model doesn't know formation, role, or tactical instructions
3. **No weather/venue effects**: Beyond home/away (captured in fixture difficulty)
4. **No injury cascade**: If a key teammate is injured, the model doesn't adjust other players' rates
5. **No price change timing**: Model predicts points, not value — price changes are not modeled
6. **No blank/double GW handling**: Each GW is treated independently; DGW/BGW aren't special-cased
7. **Positional baseline substitution risk**: Substitution risk is position-agnostic (same formula for all positions in standard mode; position-specific only in hist mode)
8. **Beta-binomial prior for starts**: Historical mode assumes start decisions follow a Beta-binomial process
9. **Clean sheet is binary**: Either 0 or 1 CS point — no partial clean sheet

### 19.3 Independence Assumptions

- **Within-player**: Goal and assist rates are treated as independent (no correlation between xG and xA for the same player)
- **Between-players**: No correlation between teammates' projections (no team-level xG allocation)
- **Between-gameweeks**: Each GW projection is independent (no momentum or fatigue modeling)
- **Minutes and rates**: xPts/90 is computed without considering the player's expected minutes (true independence)

---

## 20. Decision Intelligence Boundary

The architecture enforces a strict separation between prediction and decision:

### 20.1 Prediction Layer (read-only outputs)
- `engines/expected_points_engine.py` → xPts/90
- `engines/expected_minutes_engine.py` → expected_minutes
- `engines/expected_projection_engine.py` → xPts, CIs, component breakdown

### 20.2 Decision Layer (consumes projections read-only)
- **Assistant Manager** (`services/assistant_manager/engine.py`): squad evaluation, transfer recommendations, hit analysis, chip strategy
- **League Intelligence** (`services/league_intelligence/`): differentials, exposures, mini-league analysis
- **Chat Assistant** (`services/assistant_chat/`): natural language Q&A, cites V3 numbers with origin labels
- **Captain Recommendations**: ranked by `projected_points` from V3
- **Transfer Engine**: computes expected points gained from each potential transfer

### 20.3 The Boundary

- Decision engines **never modify** prediction engines
- Config changes require human approval via the Decision Log
- No feedback loop: model tuning is manual, not automated from decision outcomes
- The chatbot prompt (`services/assistant_chat/engine.py`) instructs: "Treat V3 numbers as authoritative. Use shadow model numbers for comparison."

---

## 21. Validation Framework

### 21.1 Metrics

`validate_version()` at `engines/validation_engine.py:72-181` computes per (version_id, gameweek):
- MAE, RMSE, bias (actual - predicted)
- Median absolute error
- CI 80% and CI 95% coverage
- CI average width
- Per-position MAE/RMSE
- Best/worst predicted player

### 21.2 Walk-Forward Ablation

`research/validation.py` defines 7 models (A-G) across 2 folds:
- **fold1**: train 2022-23 → validate 2023-24
- **fold2**: train 2022-23+23-24 → validate 2024-25

### 21.3 Evidence Maturity Levels

`services/learning_service.py:41-47`:
- `weak` (1 GW), `needs_more_data` (2 GW), `moderate` (3-4 GW), `strong` (5-9 GW), `statistically_significant` (10+ GW)
- These are **sample-size heuristics**, not formal statistical tests

### 21.4 Shadow Monitoring

V2 and Model D run as permanent shadows. Validation compares their MAE/RMSE/bias against V3 over time. From `comparison_reports.py`:
> "V3 is the production model; the V2 shadow (control group) must stay within tolerance over ≥5 gameweeks of validated MAE/RMSE and CI calibration. A sustained control-group divergence is a drift signal — investigate before trusting V3. No change is ever automatic."

---

## 22. Known Issues & Limitations

### 22.1 Bugs (from GW1 Production Readiness Audit)

| ID | Severity | Description | Status |
|----|----------|-------------|--------|
| O1 | Medium | `version_tag` doesn't include `model_name` — shadow persistence silently skipped when hashes collide | Open |
| O2 | Low | `minutes_fraction` in `scoring.py:60` doesn't fillna before division — NaN propagates to `minutes_reliable` | Open |
| O3 | Low | No `PRAGMA busy_timeout` on SQLite — concurrent writes risk `OperationalError` | Open |
| O4 | Low | No DB indexes on frequently queried columns (player_id, gameweek_id in Prediction) | Open |
| O5 | Low | No rollback on `session.commit()` failures | Open |
| O6 | Low | No spinner on My Team page during projection run | Open |

### 22.2 Design Limitations

1. **No opponent-specific modeling**: Fixture difficulty is a single integer
2. **No tactical awareness**: Doesn't account for formation, role changes, or tactical shifts
3. **No fatigue/cumulative load**: Each GW is independent
4. **No blank/double GW special handling**: DGWs aren't modeled as 2× points
5. **Substitution risk is crude**: Fixed thresholds, not player-specific sub patterns (standard mode)
6. **Clean sheet model is simple**: Anchored closed-form or linear — doesn't capture team defensive form trends
7. **Bonus model is a proxy**: BPS/90 → bonus is noisy; actual BPS depends on in-match events
8. **Positional baselines are static**: GKP=90, DEF=88, MID=78, FWD=75 — don't adapt to team-specific patterns
9. **Historical team adjustment uses global weights**: `attack_weight=0.5` applied uniformly across all teams

### 22.3 Model D (Shadow) Limitations

- Projects Woodman (LIV, £4.0m) as highest xPts GKP but only 86% start prob — may be reading inflated rate stats from previous club
- Hist configs carry 3-season priors that may not reflect current-season form changes
- `sub_rate_given_not_start` and `min_if_sub` are positional averages, not player-specific

---

## Appendix A: File Reference Map

| File | Lines | Role |
|------|-------|------|
| `engines/expected_points_engine.py` | 485 | xPts/90 engine |
| `engines/expected_minutes_engine.py` | 478 | Expected minutes engine |
| `engines/expected_projection_engine.py` | 320 | Compositor |
| `features/store.py` | 500 | FeatureStore |
| `services/scoring.py` | 191 | Derived columns |
| `services/production_predictor.py` | 323 | Primary/shadow dispatch |
| `services/expected_pipeline.py` | 231 | Persistence layer |
| `config/expected_points/expected_points_v1.yaml` | 99 | Points config |
| `config/expected_points/expected_points_v1_hist.yaml` | 117 | Points hist config |
| `config/expected_minutes/expected_minutes_v1.yaml` | 50 | Minutes config |
| `config/expected_minutes/expected_minutes_v1_hist.yaml` | 84 | Minutes hist config |
| `config/production/production_v1.yaml` | 28 | Production model selection |
| `config/active.yaml` | 15 | Active config versions |
| `database/models.py` | — | Ledger schema (append-only) |
| `engines/validation_engine.py` | — | Validation metrics |
| `research/validation.py` | — | Walk-forward ablation |
| `services/assistant_chat/engine.py` | — | Chatbot integration |
| `services/assistant_manager/engine.py` | — | Decision engine |
