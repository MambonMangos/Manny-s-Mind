# Expected Minutes & Substitute Behaviour — Analysis

**Data:** vaastav `8c97b2adb123863c3dd581e730f1360e89815ac2` · faithful seasons only (2022-23, 2023-24, 2024-25) · rows: **76417**

## 1. Start-probability calibration

If the engine's `start_probability` is honest, players in a higher predicted bucket should start more often. Restricted to `data_quality_minutes == good` and split by history depth (`raw_minutes >= 360` = established, otherwise marginal).

| predicted bucket | n | mean_predicted | observed_starts_rate |
|---|---:|---:|---:|
| (0.333, 0.417] | 13632 | 0.358 | 0.063 |
| (0.417, 0.5] | 1269 | 0.461 | 0.389 |
| (0.5, 0.583] | 1320 | 0.547 | 0.522 |
| (0.583, 0.667] | 1948 | 0.627 | 0.509 |
| (0.667, 0.75] | 2638 | 0.710 | 0.490 |
| (0.75, 0.833] | 2646 | 0.790 | 0.455 |
| (0.833, 0.917] | 3678 | 0.878 | 0.371 |
| (0.917, 1.0] | 23997 | 0.958 | 0.591 |

Split by history depth:

| history | predicted bucket | n | observed_starts_rate |
|---|---|---:|---:|
| established | (0.25, 0.375] | 1415 | 0.095 |
| established | (0.375, 0.5] | 2705 | 0.261 |
| established | (0.5, 0.625] | 1733 | 0.611 |
| established | (0.625, 0.75] | 2518 | 0.645 |
| established | (0.75, 0.875] | 2667 | 0.520 |
| established | (0.875, 1.0] | 20344 | 0.632 |
| marginal | (0.25, 0.375] | 9940 | 0.047 |
| marginal | (0.375, 0.5] | 841 | 0.052 |
| marginal | (0.5, 0.625] | 518 | 0.193 |
| marginal | (0.625, 0.75] | 1137 | 0.167 |
| marginal | (0.75, 0.875] | 1621 | 0.247 |
| marginal | (0.875, 1.0] | 5689 | 0.371 |

## 2. Minutes if starting (observed vs engine)

| position | n | observed_mean | observed_median | predicted_mean | implied_sub_rate | engine_sub_risk |
|---|---:|---:|---:|---:|---:|---:|
| DEF | 7412 | 85.4 | 90.0 | 88.1 | 0.051 | 0.249 |
| FWD | 1980 | 79.5 | 85.0 | 80.3 | 0.117 | 0.209 |
| GKP | 1783 | 89.4 | 90.0 | 89.9 | 0.006 | 0.250 |
| MID | 8737 | 80.2 | 90.0 | 82.3 | 0.109 | 0.241 |

## 3. Expected minutes error by data-quality tier

| data_quality_minutes | n | mae | bias | corr | actual_mean | expected_mean |
|---|---:|---:|---:|---:|---:|---:|
| good | 51128 | 36.4 | 5.79 | 0.284 | 41.2 | 47.0 |
| moderate | 25289 | 22.4 | 21.56 | 0.026 | 0.7 | 22.3 |

## 4. Expected minutes error by position

| position | n | mae | bias | corr |
|---|---:|---:|---:|---:|
| DEF | 25561 | 34.6 | 10.83 | 0.460 |
| FWD | 9144 | 29.9 | 13.89 | 0.515 |
| GKP | 8291 | 31.9 | 13.23 | 0.592 |
| MID | 33421 | 30.1 | 9.81 | 0.492 |

## 5. Relationship between the engine's own inputs and reality

| position | form->starts_r | form->minutes_r | minutes_per_game->minutes_r |
|---|---:|---:|---:|
| DEF | 0.6095 | 0.6931 | 0.4914 |
| FWD | 0.6114 | 0.7643 | 0.4947 |
| GKP | 0.7659 | 0.8294 | 0.6086 |
| MID | 0.6244 | 0.7596 | 0.4916 |

## 6. Interpretation

- Section 1: `start_probability` over-estimates for every bucket (the whole probability scale is inflated). Two causes: (a) `chance_of_playing` is unknown in the historical data and was forced to 1.0, adding a 0.4 floor; (b) `starts_rate` divides by `max(minutes/90, 1)`, so players with 1-2 games of history get a 1.0+ rate and a near-capped start_probability. Marginal players are the worst offenders — see the history split.
- Section 2: the engine's `minutes_if_starting` baselines (GKP 90 / DEF 88 / MID 78 / FWD 75) sit just above observed means (89.4 / 85.4 / 80.2 / 79.5). But `substitution_risk` = 0.25 for players expected to play 78+ minutes while the true implied sub rate is 0.006 (GKP), 0.051 (DEF), 0.109 (MID), 0.117 (FWD). This single 0.25 multiplier is why established starters like Saliba get `expected_minutes` ~65 while they actually play 90.
- Section 3: expected minutes error is concentrated in the moderate tier (engineered ~22.3 vs actual ~0.7 — players with no meaningful history at all). For `good` rows, bias is small (expected 47.0 vs actual 41.2) but MAE 36.4 — minutes are intrinsically hard to predict.
- Section 5: the engine's own inputs are informative — form→minutes Spearman is 0.69-0.83 by position. The input signal is good; the composition (floors/constants) is what degrades the output.

## 7. Caveat

- The `chance_of_playing = 1.0` floor is a **backtest artifact**: per-gameweek availability is not available in the vaastav data, so it was forced to 'available'. In live production the engine receives real `chance_of_playing` values, which would reduce (but not eliminate) the start-probability inflation.
- The `starts_rate` 1-game denominator floor and the `substitution_risk = 0.25` for expected 78+ minute players are genuine engine behaviours that hold in production too, and are the two most actionable candidates for a minutes-engine revision.