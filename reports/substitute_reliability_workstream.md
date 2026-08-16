# Substitute Reliability & Minutes Intelligence — Workstream Report

**Role:** ML / Analytics Engineer · **Audit + Phase 1 implemented** · **Date:** 2026-08-13
**Scope:** Fix the data foundation (Phase 1), design the substitute/minutes intelligence (Phases 2–7, design-only), define validation (evidence-first). **V3 is NOT modified, replaced, or promoted.**
**Related report:** `reports/model_audit_substitute_selection.md` (12-phase audit that identified the defect).

---

## 1. Data Audit

### 1.1 Where `starts` originates

The FPL API supplies a real, season-cumulative `starts` value on every element in `bootstrap-static` (verified live: 584/584 players, 0 nulls). It also exposes real per-season `starts` in `element-summary/{id}/history_past`. **It never provides substitute-appearance or unused-substitute counts** — that is a documented API limitation (see §3.1).

### 1.2 Where it was being lost

| Stage | Before | After |
|---|---|---|
| `services/data_loader.py` `_PLAYER_FIELDS` | `starts` omitted — never fetched | `"starts"` added; `_parse_player` coerces to int, defaults 0 |
| DB schema | `players` table had no `starts` column | `Player.starts` (`Integer, default=0`) + Alembic migration `c4d3e2f1a5b6` (`server_default='0'`, NOT NULL) |
| `database/crud.py` `get_players_dataframe` | `starts` never selected | `"starts": player.starts or 0` |
| `features/store.py` `build_feature_store` (was line 448–449) | fabricated `starts = round(minutes/90)` | fabrication **removed**; missing → 0, real values preserved |
| `features/store.py` `_build_minutes_features` | `starts_rate = starts/(minutes/90)` computed on fabricated starts → ≡ 1.0 | computed on **real** starts; `minutes_per_game` capped at 90 (logical bound) |

The fabricated `round(minutes/90)` was also provably wrong in the other direction: 22 real players have `starts > minutes/90 + 1` (started games but subbed off early), which the approximation could never represent.

### 1.3 Verification (post-fix, live data)

- `players` = 584, `teams` = 20, `gameweeks` = 38; `alembic_version` at head.
- 365 players with `starts > 0`; **35 players with `starts = 0 AND minutes > 0`** (sub-only last season) — exactly matching the live API count.
- Migration test + data-integrity tests added: real starts preserved, no fabrication, zero stays zero, sub-only players are not converted to starters, `starts_rate` separates a sub-heavy player from an ever-present, `minutes_per_game` capped at 90.

### 1.4 Additional finding (production-safety)

`tests/test_production_predictor.py`, `tests/test_validation_platform.py`, `tests/test_comparison_reports.py`, `tests/test_expected_projection_engine.py` import the module-level engine bound to the **default** `DATABASE_URL` and call `drop_all`/`create_all` — silently destroying the real dev database on every `pytest` run. **Fixed:** root `conftest.py` now redirects `DATABASE_URL` to in-memory SQLite for the whole test session (before any test module imports `database.database`). Verified: full suite passes, real DB untouched. CI runs `pytest -q` with no `DATABASE_URL` set, so CI is now also protected.

---

## 2. Expected Minutes Audit

### 2.1 Current V3 methodology (unchanged)

`engines/expected_minutes_engine.py` + `config/expected_minutes/expected_minutes_v1.yaml`:

```
expected_minutes = start_probability × minutes_if_starting × (1 − substitution_risk)
start_probability  = clip(0.60×starts_rate + 0.40×chance_of_playing_next_round ± form adj, 0.05, 0.97)
minutes_if_starting= starts<3 ? positional baseline : 0.60×minutes_per_game + 0.40×baseline
substitution_risk  = 0.25 if minutes_if_starting ≥ 78 else 0.10
```

No engine code, config value, or weight was changed.

### 2.2 What the corrected data changes

The model now receives a **truthful** `starts_rate`. Before the fix every player with minutes had `starts_rate = 1.0`, so `start_probability` saturated at ~0.95–0.97 and `expected_minutes` collapsed to per-position constants (GKP 64.1, DEF 63.6). After the fix (live 584-player run):

| Player | Pos | Price | Real starts | start_prob | exp_min |
|---|---|---|---|---|---|
| Dubravka | GKP | £4.0m | 35 | 0.95 | 64.1 |
| Konsa | DEF | £4.5m | 34 | 0.95 | 63.2 |
| Sosa | DEF | £4.5m | 0 (99 min) | 0.35 | **23.1** |
| Kusi-Asare | FWD | £4.5m | 0 (49 min) | 0.35 | **23.6** |
| Scarlett | FWD | £4.5m | 0 (7 min) | 0.35 | **23.6** |

Cheap-but-unreliable players are no longer scored as starters. Integrity checks: 584 projections, **0 NaN**, **0 negatives**, all within [0, 90].

**Accepted consequence:** a player with 1 start and exactly 90 minutes legitimately gets `starts_rate = 1.0` (they played their one game and started it). Distinguishing "ever-present" from "one-game-wonder" requires per-GW history, which arrives once the season starts (Phase 2 evidence).

---

## 3. Substitute Intelligence Design (design-only — nothing promoted)

### 3.1 What the API can and cannot tell us

| Observation | Available now? | Source |
|---|---|---|
| Event A — Started (season-cumulative starts) | Yes | `bootstrap-static` `starts` |
| Event A — Started (per gameweek) | In-season | `element-summary/{id}/history` (empty in preseason — schema unverifiable until GW1) |
| Event B — Substitute appearance (per gameweek) | In-season, derivable | `history` minutes > 0 with no start in that GW (needs GW history) |
| Event C — Did not play (available but unused) | **Not available** | the public API does not expose "was on the bench but unused" vs "not in the squad" |
| Event D — Unused substitute (named bench, no entry) | **Not available** | same limitation |
| Substitute-appearance / unused-sub **counts** | **Not available anywhere** | FPL public API has no such field |

**Limitation (documented, per brief):** events C and D cannot be observed from the public FPL API. We will not invent fields. We observe what is available (starts, minutes, points per GW) and infer B where `minutes > 0` and no start is recorded once per-GW data exists.

### 3.2 Dataset to begin preserving (in-season)

Per player/gameweek, when `element-summary` history populates:

```
player_id | gameweek | price | position | starts | minutes | points | xPts_per_90
```

plus the derived flags `started` (0/1), `sub_appearance` (0/1 = minutes>0 and not started), `did_not_play` (0/1 = minutes=0), recorded against the **predicted** values at the time of the pre-GW projection. The per-GW observation is appended to the prediction ledger pattern (append-only, version-tagged).

### 3.3 Minimum-Cost Reliable Minutes (MCRM) — concept

Bench value is **not** "cheapest". A bench candidate should be scored as insurance:

```
Cheap  +  Likely to play  +  Contributes when introduced  =  Good bench candidate
```

Candidate metrics (computed, not thresholds): price, P(start), P(sub appearance), P(60+ minutes), expected minutes, minutes volatility, xPts/90, expected points when actually playing. The MCRM objective: **minimise cost subject to a reliability requirement**, e.g. `max(price) such that expected_minutes ≥ X and P(playing) ≥ Y`. **No threshold (X/Y) is hard-coded yet** — the correct values will be estimated from observed outcomes over the first several gameweeks (§4).

### 3.4 Future three-event minutes model (shadow candidate only)

```
                  ┌── Start          → E[minutes | start]
Player ───────────┤
                  ├── Sub appearance → E[minutes | sub]
                  └── Did not play   → 0
expected_minutes = P(start)·E[min|start] + P(sub)·E[min|sub]
```

This replaces only the minutes input; the V3 compositor `xPts = xPts_per_90 × expected_minutes/90` stays identical. It is a **shadow candidate** — it will not be promoted on design merit alone.

### 3.5 Future bench optimizer (Decision Intelligence layer)

Given budget, starting XI, formation and squad constraints, select bench players that maximise **emergency minutes coverage**. Optimizer inputs: price, playing probability, substitution probability, expected minutes, xPts/90, position, squad constraints. It must distinguish **cheap-but-unreliable**, **cheap-and-reliable**, and **expensive-but-unnecessary**. Lives in the decision layer, not the prediction layer. The prediction/minutes/decision separation is preserved:

```
V3 Prediction Model → xPts/90 → Expected Minutes → Decision Intelligence (XI vs Bench → Substitute Reliability)
```

No collapse of responsibilities into a single model.

---

## 4. Validation Plan (first several gameweeks — observation period)

Per gameweek, for every projected player, record against actuals:

| Predicted | Actual |
|---|---|
| start probability | started (0/1) |
| expected minutes | minutes |
| substitute likelihood | sub appearance (0/1) |
| xPts/90, price, position | FPL points |

Metrics accumulated across GWs (become part of the validation platform):

1. **Start probability calibration** — brier score + reliability table of P(start) vs observed start rate (bucket by predicted probability).
2. **Substitute probability calibration** — same, for sub appearances (players predicted unlikely to start).
3. **Meaningful-minutes reliability** — observed rate of "≥ 60 minutes" vs prediction; the empirical basis for the MCRM reliability threshold (no invented thresholds).
4. **Expected-minutes accuracy** — MAE/RMSE/bias of predicted minutes vs actual, per position, V3-with-real-starts vs the three-event shadow candidate.
5. **Bench reliability** — for bench players, observed contribution rate when an auto-sub is needed (the "insurance" KPI).
6. **xPts → points** — existing validation ledger continues unchanged.

**Discipline:** no model changes every Monday. The next several GWs are evidence collection only.

**Future promotion criteria:** a substitute/minutes candidate is promoted only when evidence across **multiple gameweeks** demonstrates improvement in the metrics above (calibration, meaningful-minute reliability, bench reliability) and, ultimately, FPL decision outcomes. Design quality alone, a good-looking single GW, or director preference are not promotion grounds.

---

## 5. Production Safety Report

Confirmed status:

- **V3 remains the production model** (`expected_points_v1` primary, `projection_v2` shadow — `config/production/production_v1.yaml` unchanged).
- **No V3 weights changed**, **no config value changed** (`expected_minutes_v1.yaml`, `expected_points_v1.yaml` untouched).
- **No new minutes model promoted**; the three-event model is a documented shadow-candidate concept only.
- **No automatic model changes introduced**; no scheduler/pipeline wiring was added.
- **Existing validation infrastructure intact** — validation engine, prediction ledger, and versioning unchanged; per-GW minutes reliability metrics will be **added** to it as observations accrue.
- **Regression:** `pytest` 187 passed (12 new data-integrity tests), `ruff check .` clean, streamlit boots (health 200) and all sampled pages render on the corrected data.
- **Changed files** (Phase 1 only): `services/data_loader.py`, `database/models.py`, `database/crud.py`, `features/store.py`, `conftest.py`, new Alembic migration `c4d3e2f1a5b6`, new tests. No engine files modified.

**Bottom line for the Director:** the bench philosophy ("a substitute is not simply a cheap player") is now supported by truthful data. Real FPL `starts` flows from API → DB → Feature Store → Expected Minutes → V3 xPts, `round(minutes/90)` fabrication is removed from production, and the next several gameweeks will produce the evidence to size the Minimum-Cost Reliable Minutes threshold and build the substitute/minutes intelligence.
