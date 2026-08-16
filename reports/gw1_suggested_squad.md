# Suggested GW1 Squad — 2026-27 (research-informed)

Built 2026-08-14 · GW1 deadline **2026-08-21 18:30 BST** · data: FPL 2026-27 preseason DB (last-season totals, current prices) + live GW1 fixtures.

**Corrected projections** (2026-08-14): per-position xGI→points conversion refit as `points_per_90 = α + β·xGI` (regression with intercept) instead of a points/xGI ratio that was over-crediting high-xGI players. Per-player EVs are now bounded by their own points-per-90 (previously e.g. a 4.5m defender "projected" 8+ pts and a 12m midfielder 10+).

## The squad (100.0m / 100.0m · projected 84.8 pts for the 15)

| position | player | club | price | proj_pts | GW1 opp | diff |
|---|---|---:|---:|---:|---:|---:|
| DEF | Gabriel | Arsenal | 8.0m | 6.1 | Coventry City (H) | 2/5 |
| DEF | Calafiori | Arsenal | 5.5m | 5.7 | Coventry City (H) | 2/5 |
| DEF | De Cuyper | Brighton | 4.5m | 5.5 | Aston Villa (H) | 3/5 |
| DEF | O'Reilly | Man City | 6.5m | 5.3 | Bournemouth (H) | 3/5 |
| DEF | Aït-Nouri | Man City | 5.5m | 5.2 | Bournemouth (H) | 3/5 |
| FWD | Mateta | Crystal Palace | 6.5m | 5.8 | Everton (A) | 3/5 |
| FWD | Hirst | Ipswich Town | 5.0m | 5.3 | Sunderland (H) | 2/5 |
| FWD | Obi | Man Utd | 4.5m | 4.9 | Hull City (A) | 2/5 |
| GKP | Ellborg | Sunderland | 4.5m | 4.8 | Ipswich Town (A) | 2/5 |
| GKP | Raya | Arsenal | 6.0m | 4.7 | Coventry City (H) | 2/5 |
| MID | B.Fernandes | Man Utd | 12.0m | 7.5 | Hull City (A) | 2/5 |
| MID | Cherki | Man City | 7.5m | 6.4 | Bournemouth (H) | 3/5 |
| MID | Palmer | Chelsea | 9.5m | 5.9 | Fulham (A) | 3/5 |
| MID | Mbeumo | Man Utd | 8.0m | 5.8 | Hull City (A) | 2/5 |
| MID | Estêvão | Chelsea | 6.5m | 5.8 | Fulham (A) | 3/5 |

**Captain:** B.Fernandes (7.5) — ahead of Cherki (6.4) and Gabriel (6.1).
**Bench (lowest 4 projections):** Obi, Ellborg, Raya, Hirst.

## Constraints satisfied
- 2 GKP / 5 DEF / 5 MID / 3 FWD ✓
- Max 3 per club: Arsenal 3, Man City 3, Man Utd 3, Chelsea 2, rest ≤ 1 ✓
- Budget exactly 100.0m ✓

## Methodology (what the research said we should use)
- **Feature analysis finding:** past-GW points/form and minutes reliability are the strongest pre-gameweek signals; xG is moderate; fixture strength is weak but non-zero. The picker scores on **shrunk points-per-90 + shrunk xGI-per-90** blended per position, scaled by **starts reliability**, then a mild fixture multiplier (0.85-1.15).
- **Minutes analysis finding:** low-history players get inflated start probabilities, so per-90 rates are **shrunk toward the position mean** over the first 450 minutes (a 1-game 15-pts-per-90 "star" scores near the positional average, not like a Haaland).
- **xGI→points conversion:** per-position regression `points_per_90 = α + β·xGI` (minutes-weighted, with intercept). Calibrated α/β: DEF 3.24/6.41, MID 3.25/4.05, FWD 2.45/5.42 — the intercept keeps appearance/clean-sheet/bonus baseline points from being scaled up by a player's xGI (fixes the earlier over-inflation).

## Caveats
- **Preseason projection:** no GW1 stats exist yet; per-90 rates are last season's. New signings without minutes score near the positional average — deliberately conservative about unknowns.
- Difficulty is the FPL's official 1-5 rating, not a model; the fixture multiplier is intentionally small because our research found fixture features have weak historical predictive power.
- **This is an expected-value lineup, not a prediction.** 84.8 is the 15-man single-GW sum; the 11 fielded would be ~75. Backtest MAE was ~1.2 pts per player.

Reproduce: `python -c "from research.gw1_picker import build_squad, format_squad; sq = build_squad(); print(format_squad(sq))"`
