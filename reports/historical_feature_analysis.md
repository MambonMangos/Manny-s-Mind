# Historical Feature Analysis — which features predict next-GW points

**Data:** vaastav `8c97b2adb123863c3dd581e730f1360e89815ac2` · faithful seasons only (2022-23, 2023-24, 2024-25) · rows: **76417**

Features are computed from state before the target gameweek (leakage-safe). Metric: **Spearman rank correlation with the player's actual points in the next gameweek**, computed per season and reported as median/min/max across seasons (sign_consistent = same sign in every season).

## Overall (all players)
| feature | category | n_seasons | median_r | min_r | max_r | sign_consistent |
|---|---:|---:|---:|---:|---:|---:|
| raw_form | raw | 3 | 0.6889 | 0.6879 | 0.6970 | 1 |
| trend_form | trend | 3 | 0.6889 | 0.6879 | 0.6970 | 1 |
| value_value_form | value | 3 | 0.6809 | 0.6793 | 0.6894 | 1 |
| raw_event_points | raw | 3 | 0.6531 | 0.6463 | 0.6603 | 1 |
| trend_event_points | trend | 3 | 0.6531 | 0.6463 | 0.6603 | 1 |
| raw_ict_index | raw | 3 | 0.6072 | 0.6051 | 0.6150 | 1 |
| trend_ict_index | trend | 3 | 0.6072 | 0.6051 | 0.6150 | 1 |
| start_probability | engine | 3 | 0.6053 | 0.4846 | 0.6064 | 1 |
| raw_total_points | raw | 3 | 0.6034 | 0.5976 | 0.6108 | 1 |
| trend_influence | trend | 3 | 0.5991 | 0.5972 | 0.5994 | 1 |
| raw_influence | raw | 3 | 0.5991 | 0.5972 | 0.5994 | 1 |
| value_points_per_million | value | 3 | 0.5938 | 0.5848 | 0.5996 | 1 |
| value_value_season | value | 3 | 0.5938 | 0.5848 | 0.5996 | 1 |
| minutes_minutes_season | minutes | 3 | 0.5917 | 0.5908 | 0.5966 | 1 |
| raw_minutes | raw | 3 | 0.5917 | 0.5908 | 0.5966 | 1 |
| minutes_minutes_fraction | minutes | 3 | 0.5917 | 0.5908 | 0.5966 | 1 |
| raw_bps | raw | 3 | 0.5909 | 0.5900 | 0.6100 | 1 |
| minutes_starts | minutes | 3 | 0.5793 | 0.3936 | 0.5827 | 1 |
| raw_starts | raw | 3 | 0.5793 | 0.3936 | 0.5827 | 1 |
| xgi_xgc_raw | xgi | 3 | 0.5755 | 0.3718 | 0.5763 | 1 |
| market_transfers_in_event | market | 3 | 0.5750 | 0.5642 | 0.5828 | 1 |
| xgi_xgi_raw | xgi | 3 | 0.5661 | 0.3708 | 0.5830 | 1 |
| raw_creativity | raw | 3 | 0.5652 | 0.5578 | 0.5770 | 1 |
| trend_creativity | trend | 3 | 0.5652 | 0.5578 | 0.5770 | 1 |
| xgi_xa_raw | xgi | 3 | 0.5613 | 0.3724 | 0.5753 | 1 |

## Top features by position
| group | feature | n_seasons | median_r | min_r | max_r | sign_consistent |
|---|---:|---:|---:|---:|---:|---:|
| GKP | trend_form | 3 | 0.7903 | 0.7593 | 0.8032 | 1 |
| GKP | raw_form | 3 | 0.7903 | 0.7593 | 0.8032 | 1 |
| GKP | value_value_form | 3 | 0.7888 | 0.7570 | 0.8008 | 1 |
| GKP | raw_event_points | 3 | 0.7809 | 0.7765 | 0.7936 | 1 |
| GKP | trend_event_points | 3 | 0.7809 | 0.7765 | 0.7936 | 1 |
| FWD | trend_form | 3 | 0.7401 | 0.6855 | 0.7456 | 1 |
| FWD | raw_form | 3 | 0.7401 | 0.6855 | 0.7456 | 1 |
| FWD | value_value_form | 3 | 0.7340 | 0.6741 | 0.7398 | 1 |
| MID | raw_form | 3 | 0.7285 | 0.7213 | 0.7305 | 1 |
| MID | trend_form | 3 | 0.7285 | 0.7213 | 0.7305 | 1 |
| FWD | trend_event_points | 3 | 0.7263 | 0.6617 | 0.7492 | 1 |
| FWD | raw_event_points | 3 | 0.7263 | 0.6617 | 0.7492 | 1 |
| MID | value_value_form | 3 | 0.7223 | 0.7161 | 0.7234 | 1 |
| GKP | raw_saves | 3 | 0.7059 | 0.6551 | 0.7218 | 1 |
| GKP | trend_ict_index | 3 | 0.7007 | 0.6591 | 0.7191 | 1 |
| GKP | raw_ict_index | 3 | 0.7007 | 0.6591 | 0.7191 | 1 |
| GKP | trend_influence | 3 | 0.7004 | 0.6588 | 0.7187 | 1 |
| GKP | raw_influence | 3 | 0.7004 | 0.6588 | 0.7187 | 1 |
| GKP | minutes_minutes_fraction | 3 | 0.7003 | 0.6640 | 0.7183 | 1 |
| GKP | minutes_minutes_season | 3 | 0.7003 | 0.6640 | 0.7183 | 1 |

## Conditional: regular players only (minutes_reliable == 1)
rows: 3846
| group | feature | n_seasons | median_r | min_r | max_r | sign_consistent |
|---|---:|---:|---:|---:|---:|---:|
| MID | market_transfers_in_event | 3 | 0.3326 | 0.3306 | 0.3493 | 1 |
| GKP | market_transfers_in_event | 3 | 0.3134 | 0.1379 | 0.4002 | 1 |
| MID | trend_form | 3 | 0.3043 | 0.2930 | 0.3507 | 1 |
| MID | raw_form | 3 | 0.3043 | 0.2930 | 0.3507 | 1 |
| DEF | market_transfers_in_event | 3 | 0.3027 | 0.2618 | 0.3208 | 1 |
| MID | raw_ict_index | 3 | 0.2739 | 0.2173 | 0.2876 | 1 |
| MID | trend_ict_index | 3 | 0.2739 | 0.2173 | 0.2876 | 1 |
| MID | market_selected_by_percent | 3 | 0.2669 | 0.2397 | 0.2741 | 1 |
| MID | raw_bps | 3 | 0.2647 | 0.2498 | 0.2677 | 1 |
| MID | raw_total_points | 3 | 0.2634 | 0.2273 | 0.2766 | 1 |
| MID | start_probability | 3 | 0.2550 | 0.1485 | 0.2588 | 1 |
| MID | trend_influence | 3 | 0.2531 | 0.2240 | 0.2559 | 1 |
| MID | raw_influence | 3 | 0.2531 | 0.2240 | 0.2559 | 1 |
| MID | predicted_points | 3 | 0.2512 | 0.1865 | 0.2839 | 1 |
| MID | xpts_per_90 | 3 | 0.2502 | 0.1823 | 0.2818 | 1 |
| MID | raw_assists | 3 | 0.2487 | 0.2430 | 0.3074 | 1 |
| MID | xgi_xgi_raw | 3 | 0.2485 | 0.2156 | 0.2588 | 1 |
| MID | value_value_form | 3 | 0.2474 | 0.2317 | 0.2744 | 1 |
| MID | trend_creativity | 3 | 0.2471 | 0.1761 | 0.2478 | 1 |
| MID | raw_creativity | 3 | 0.2471 | 0.1761 | 0.2478 | 1 |

## Category strength (median |r| of best feature per category, by position)
| position | category | best_feature | median_r |
|---|---|---|---:|
| DEF | raw | raw_form | 0.5873 |
| DEF | trend | trend_form | 0.5873 |
| DEF | value | value_value_form | 0.5830 |
| DEF | market | market_transfers_in_event | 0.5269 |
| DEF | engine | expected_minutes | 0.5115 |
| DEF | minutes | minutes_minutes_fraction | 0.5035 |
| DEF | xgi | xgi_xgi_raw | 0.4655 |
| DEF | set_piece | set_piece_fk_order | -0.1853 |
| DEF | fixture | fixture_team_strength | 0.0599 |
| FWD | raw | raw_form | 0.7401 |
| FWD | trend | trend_form | 0.7401 |
| FWD | value | value_value_form | 0.7340 |
| FWD | engine | start_probability | 0.6651 |
| FWD | market | market_transfers_in_event | 0.6607 |
| FWD | xgi | xgi_xgi_raw | 0.6466 |
| FWD | minutes | minutes_minutes_season | 0.6427 |
| FWD | set_piece | set_piece_set_piece_raw | 0.4308 |
| FWD | fixture | fixture_team_strength | 0.0715 |
| GKP | raw | raw_form | 0.7903 |
| GKP | trend | trend_form | 0.7903 |
| GKP | value | value_value_form | 0.7888 |
| GKP | minutes | minutes_minutes_fraction | 0.7003 |
| GKP | engine | start_probability | 0.6940 |
| GKP | xgi | xgi_xgc_raw | 0.6465 |
| GKP | market | market_transfers_in_event | 0.6148 |
| GKP | fixture | fixture_fixture_avg_1gw | -0.0219 |
| MID | raw | raw_form | 0.7285 |
| MID | trend | trend_form | 0.7285 |
| MID | value | value_value_form | 0.7223 |
| MID | market | market_transfers_in_event | 0.6310 |
| MID | minutes | minutes_minutes_season | 0.6293 |
| MID | xgi | xgi_xgi_raw | 0.6280 |
| MID | engine | start_probability | 0.6277 |
| MID | set_piece | set_piece_corners_order | -0.3695 |
| MID | fixture | fixture_team_strength | 0.0738 |

## V3 prediction vs the raw ingredients
| feature | spearman |
|---|---:|
| predicted_points (V3 output) | 0.2603 |
| xpts_per_90 (V3) | 0.1338 |
| expected_minutes (V3) | 0.4505 |
| form | 0.6922 |
| previous GW points (event_points) | 0.6543 |
| xgi_per_90 | 0.4355 |
| raw minutes | 0.5940 |

## Notes

- Spearman on single-GW points is inherently noisy (points are sparse integers 0-15); per-season medians give the *direction* of each feature.
- Only faithful seasons can rank xG features. Proxy seasons are excluded.
- 'sign_consistent' flags features whose sign is stable across all three faithful seasons — the most trustworthy candidates.