# V3 Historical Backtest — Deliverable C

**Date:** 2026-08-14 · **Data:** vaastav pinned `8c97b2adb123863c3dd581e730f1360e89815ac2` · **Model:** `expected_points_v1` × `expected_minutes_v1` (production V3, run read-only)

Prediction rows (with actuals, players only): **141228** across 6 seasons (faithful: 3, proxy: 3).

## Overall (V3 as-is, aggregated across seasons)
| season_mode | n | actual_mean | predicted_mean | bias_points | mae_points | rmse_points | corr_points | mae_minutes | corr_minutes | actual_starts_mean | expected_minutes_mean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| faithful | 76417 | 1.168 | 0.326 | -0.842 | 1.178 | 2.488 | 0.246 | 31.774 | 0.496 | 0.277 | 38.825 |
| proxy | 64811 | 1.370 | 0.220 | -1.150 | 1.418 | 2.849 | 0.049 | 36.281 | 0.399 | — | 23.125 |

## By season
| season | season_mode | n | actual_mean | predicted_mean | bias_points | mae_points | rmse_points | corr_points | mae_minutes | corr_minutes | actual_starts_mean | expected_minutes_mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2019-20 | proxy | 21121 | 1.388 | 0.219 | -1.168 | 1.426 | 2.784 | 0.038 | 35.725 | 0.403 | — | 23.135 |
| 2020-21 | proxy | 21751 | 1.374 | 0.224 | -1.150 | 1.425 | 2.866 | 0.058 | 36.513 | 0.401 | — | 23.159 |
| 2021-22 | proxy | 21939 | 1.350 | 0.217 | -1.133 | 1.404 | 2.894 | 0.052 | 36.587 | 0.393 | — | 23.083 |
| 2022-23 | faithful | 23606 | 1.271 | 0.266 | -1.005 | 1.305 | 2.667 | 0.134 | 33.168 | 0.397 | 0.227 | 30.114 |
| 2023-24 | faithful | 27292 | 1.087 | 0.350 | -0.738 | 1.091 | 2.399 | 0.305 | 31.226 | 0.600 | 0.291 | 42.025 |
| 2024-25 | faithful | 25519 | 1.159 | 0.355 | -0.804 | 1.154 | 2.408 | 0.280 | 31.071 | 0.592 | 0.310 | 43.459 |

## By position (faithful seasons only)
| position | n | actual_mean | predicted_mean | bias_points | mae_points | rmse_points | corr_points | mae_minutes | corr_minutes | actual_starts_mean | expected_minutes_mean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEF | 25561 | 1.052 | 0.416 | -0.636 | 1.214 | 2.357 | 0.067 | 34.564 | 0.460 | 0.309 | 41.756 |
| FWD | 9144 | 1.352 | 0.316 | -1.035 | 1.236 | 2.827 | 0.350 | 29.938 | 0.515 | 0.230 | 37.362 |
| GKP | 8291 | 0.887 | 0.517 | -0.370 | 0.910 | 1.987 | 0.421 | 31.892 | 0.592 | 0.232 | 36.648 |
| MID | 33421 | 1.276 | 0.212 | -1.064 | 1.202 | 2.596 | 0.317 | 30.113 | 0.492 | 0.277 | 37.522 |

## By position (proxy seasons only)
| position | n | actual_mean | predicted_mean | bias_points | mae_points | rmse_points | corr_points | mae_minutes | corr_minutes | actual_starts_mean | expected_minutes_mean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEF | 22316 | 1.327 | 0.514 | -0.813 | 1.461 | 2.731 | 0.182 | 39.424 | 0.508 | — | 24.082 |
| FWD | 8572 | 1.512 | 0.016 | -1.496 | 1.513 | 3.175 | 0.203 | 32.895 | 0.575 | — | 24.733 |
| GKP | 7381 | 1.078 | 0.327 | -0.751 | 1.085 | 2.367 | 0.491 | 35.923 | 0.771 | — | 24.481 |
| MID | 26542 | 1.442 | 0.010 | -1.432 | 1.444 | 2.956 | 0.165 | 34.832 | 0.512 | — | 21.425 |

## By gameweek (faithful seasons, aggregated across seasons)
| round | n | actual_mean | predicted_mean | bias_points | mae_points | corr_points |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1876 | 1.255 | 0.329 | -0.926 | 1.211 | 0.285 |
| 4 | 1925 | 1.285 | 0.321 | -0.964 | 1.252 | 0.287 |
| 5 | 1963 | 1.206 | 0.313 | -0.892 | 1.181 | 0.237 |
| 6 | 1986 | 1.207 | 0.321 | -0.886 | 1.210 | 0.230 |
| 7 | 1382 | 1.260 | 0.362 | -0.898 | 1.233 | 0.297 |
| 8 | 1821 | 1.192 | 0.322 | -0.870 | 1.186 | 0.214 |
| 9 | 2023 | 1.210 | 0.318 | -0.893 | 1.210 | 0.267 |
| 10 | 2038 | 1.178 | 0.308 | -0.870 | 1.174 | 0.219 |
| 11 | 2046 | 1.215 | 0.308 | -0.907 | 1.217 | 0.210 |
| 12 | 1994 | 1.225 | 0.315 | -0.910 | 1.236 | 0.257 |
| 13 | 2072 | 1.182 | 0.306 | -0.876 | 1.192 | 0.220 |
| 14 | 2085 | 1.221 | 0.312 | -0.909 | 1.228 | 0.227 |
| 15 | 2039 | 1.171 | 0.310 | -0.861 | 1.173 | 0.162 |
| 16 | 2111 | 1.165 | 0.313 | -0.852 | 1.173 | 0.216 |
| 17 | 2047 | 1.243 | 0.311 | -0.932 | 1.262 | 0.198 |
| 18 | 2072 | 1.147 | 0.317 | -0.830 | 1.147 | 0.212 |
| 19 | 2152 | 1.191 | 0.321 | -0.870 | 1.192 | 0.246 |
| 20 | 2169 | 1.190 | 0.323 | -0.867 | 1.193 | 0.261 |
| 21 | 2183 | 1.171 | 0.324 | -0.848 | 1.165 | 0.303 |
| 22 | 2218 | 1.151 | 0.326 | -0.825 | 1.160 | 0.257 |
| 23 | 2268 | 1.078 | 0.332 | -0.746 | 1.105 | 0.243 |
| 24 | 2290 | 1.141 | 0.328 | -0.813 | 1.165 | 0.241 |
| 25 | 2158 | 1.267 | 0.331 | -0.936 | 1.277 | 0.294 |
| 26 | 2149 | 1.129 | 0.331 | -0.797 | 1.180 | 0.224 |
| 27 | 2338 | 1.172 | 0.332 | -0.840 | 1.189 | 0.277 |
| 28 | 2134 | 1.037 | 0.330 | -0.707 | 1.065 | 0.234 |
| 29 | 1718 | 1.318 | 0.318 | -1.000 | 1.333 | 0.203 |
| 30 | 2361 | 1.019 | 0.339 | -0.680 | 1.043 | 0.271 |
| 31 | 2367 | 1.050 | 0.336 | -0.714 | 1.078 | 0.243 |
| 32 | 2226 | 1.080 | 0.335 | -0.745 | 1.105 | 0.286 |
| 33 | 2384 | 1.114 | 0.335 | -0.779 | 1.146 | 0.237 |
| 34 | 2199 | 1.323 | 0.338 | -0.985 | 1.348 | 0.291 |
| 35 | 2398 | 1.048 | 0.336 | -0.712 | 1.075 | 0.216 |
| 36 | 2403 | 1.141 | 0.336 | -0.805 | 1.159 | 0.299 |
| 37 | 2405 | 1.200 | 0.337 | -0.863 | 1.209 | 0.259 |
| 38 | 2417 | 1.038 | 0.342 | -0.697 | 1.074 | 0.233 |

## Calibration (predicted vs actual, faithful seasons)
| bucket | n | mean_predicted | mean_actual | mae |
|---:|---:|---:|---:|---:|
| (-0.001, 0.0971] | 30567 | 0.011 | 0.690 | 0.701 |
| (0.0971, 0.348] | 15284 | 0.186 | 1.128 | 1.163 |
| (0.348, 0.529] | 15282 | 0.482 | 0.862 | 1.104 |
| (0.529, 5.03] | 15284 | 0.938 | 2.470 | 2.222 |

## Minutes accuracy (faithful seasons)
| position | n | mae_minutes | corr_minutes | actual_starts_mean | expected_minutes_mean |
|---:|---:|---:|---:|---:|---:|
| DEF | 25561 | 34.564 | 0.460 | 0.309 | 41.756 |
| FWD | 9144 | 29.938 | 0.515 | 0.230 | 37.362 |
| GKP | 8291 | 31.892 | 0.592 | 0.232 | 36.648 |
| MID | 33421 | 30.113 | 0.492 | 0.277 | 37.522 |

## Interpretation notes

- **Under-prediction:** V3's predicted points run well below actual mean in every season/mode (bias < 0). This is expected: xPts/90 scales from a short cumulative window and `expected_minutes` is capped by start probability × minutes_if_starting.
- **Proxy seasons (2019-20..2021-22):** `starts` and xG do not exist in the source data, so the minutes engine runs on starts=0 and the points engine on xG=0 (see historical_data_audit.md §3). Their numbers are NOT comparable to the faithful seasons.
- **Sample size:** 3 faithful seasons is enough to establish *direction* of biases but not statistical significance. Treat cross-season stability claims as indicative.

*Generated by `research/report.py`. Predictions CSV: `data_research/results/v3_baseline_predictions.csv`.*