# Suggested No-Transfers Squad — Full Season 2026-27

Built 2026-08-14 · GW1 deadline **2026-08-21 18:30 BST** · scenario: **one fixed 15-man squad picked once, zero transfers for all 38 gameweeks**.

## The squad (100.0m / 100.0m)

| position | player | club | price | GW1-5 | GW6-10 | GW11-15 | GW16-20 | GW21-25 | GW26-30 | GW31-35 | GW36-38 | season |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DEF | De Cuyper | Brighton | 4.5m | 27 | 26 | 28 | 27 | 27 | 29 | 27 | 15 | 207 |
| DEF | Calafiori | Arsenal | 5.5m | 26 | 27 | 26 | 27 | 27 | 27 | 27 | 16 | 203 |
| DEF | Patterson | Everton | 4.5m | 26 | 25 | 25 | 26 | 26 | 24 | 26 | 15 | 194 |
| DEF | Acheampong | Chelsea | 4.5m | 24 | 23 | 23 | 25 | 24 | 24 | 23 | 14 | 181 |
| DEF | Davies | Spurs | 4.0m | 23 | 22 | 23 | 22 | 23 | 22 | 22 | 13 | 171 |
| FWD | Ekitiké | Liverpool | 7.5m | 31 | 30 | 30 | 31 | 29 | 31 | 29 | 18 | 229 |
| FWD | Osula | Newcastle | 6.0m | 30 | 30 | 30 | 28 | 29 | 29 | 30 | 18 | 225 |
| FWD | Marmoush | Man City | 7.0m | 30 | 29 | 29 | 30 | 29 | 30 | 29 | 18 | 224 |
| GKP | Ellborg | Sunderland | 4.5m | 22 | 23 | 21 | 22 | 22 | 21 | 23 | 13 | 167 |
| GKP | Raya | Arsenal | 6.0m | 22 | 22 | 22 | 22 | 22 | 22 | 22 | 13 | 167 |
| MID | B.Fernandes | Man Utd | 12.0m | 36 | 35 | 35 | 35 | 34 | 34 | 37 | 22 | 268 |
| MID | Cherki | Man City | 7.5m | 32 | 32 | 32 | 32 | 32 | 33 | 31 | 20 | 244 |
| MID | Saka | Arsenal | 9.5m | 31 | 32 | 31 | 32 | 32 | 32 | 32 | 20 | 242 |
| MID | Kroupi.Jr | Bournemouth | 7.5m | 29 | 31 | 30 | 31 | 31 | 31 | 30 | 17 | 231 |
| MID | Palmer | Chelsea | 9.5m | 30 | 29 | 29 | 31 | 30 | 30 | 29 | 18 | 225 |

## Expected points actually scored (best legal XI + auto-subs)

| block | GW1-5 | GW6-10 | GW11-15 | GW16-20 | GW21-25 | GW26-30 | GW31-35 | GW36-38 | season |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| expected | 338.2 | 337.5 | 337.1 | 337.5 | 337.9 | 338.0 | 340.9 | 204.0 | **2571.2** |

~67.7 pts/GW fielded, remarkably flat across blocks — expected, because over a full season every team's fixtures normalise (each squad member faces the full league twice). The all-15 "squad value" is 3175.4, but only the 11 fielded (+ auto-subs) count.

**Default captain:** B.Fernandes (268 season projection). The armband should realistically rotate week-to-week around your best fixture (his GW1-3 and GW31-35 are the strongest).
**Bench (lowest 4 season projections):** Davies, Acheampong, Ellborg, Raya.

## Season fixture summary (avg difficulty · easy/38 · home/38)
- De Cuyper (Brighton): 3.1 · 10 · 19 — Acheampong (Chelsea): 3.0 · 11 · 19
- Calafiori (Arsenal): 3.0 · 11 · 19 — Davies (Spurs): 3.1 · 11 · 19
- Patterson (Everton): 3.1 · 11 · 19 — Ekitiké (Liverpool): 3.0 · 11 · 19
- Osula (Newcastle): 3.1 · 10 · 19 — Marmoush (Man City): 3.0 · 11 · 19
- Ellborg (Sunderland): 3.1 · 10 · 19 — Raya (Arsenal): 3.0 · 11 · 19
- B.Fernandes (Man Utd): 3.0 · 11 · 19 — Cherki (Man City): 3.0 · 11 · 19
- Saka (Arsenal): 3.0 · 11 · 19 — Kroupi.Jr (Bournemouth): 3.1 · 11 · 19
- Palmer (Chelsea): 3.0 · 11 · 19

## Constraints satisfied
- 2 GKP / 5 DEF / 5 MID / 3 FWD ✓
- Max 3 per club: Arsenal 3, Chelsea 2, Man City 2, rest ≤ 1 ✓
- Budget exactly 100.0m ✓

## Methodology & caveats
Same research-informed scoring as the GW1-5 picker: shrunk per-90 rates × starts reliability, per-position blend of points and regression-calibrated xGI (`points_per_90 = α + β·xGI`: DEF 3.24/6.41, MID 3.25/4.05, FWD 2.45/5.42), per-GW fixture factor (0.85-1.15), set-piece bonus per GW. Selection maximises the sum across all 38 GWs under the standard constraints.
- **Fixture factors wash out over a full season** — every team plays all 38 games, so this is effectively a value selection on base signal per price, which is what you want with no transfers.
- **High uncertainty caveat:** a no-transfer season assumes everyone stays fit/in form/at their current club and keeps last season's role all year. In reality you'd burn that on transfers. Treat the 2571 as a long-run EV, not a forecast — variance over 38 GWs is enormous.
- Preseason projection: per-90 rates are last season's; no current-season data exists. Cheap 4.5m picks (Patterson, Acheampong, Davies) project near the positional average because of the low-history shrinkage — they're value plays, not "stars".
- Auto-subs modelled as GK replaced by bench GK with prob (1 − starts reliability); outfield misses ~ Poisson(λ), each bench sub contributing when k+ starters are out.

Reproduce: `python -c "from research.gw1_picker import build_squad_season, format_squad_season; sq = build_squad_season(); print(format_squad_season(sq))"`
