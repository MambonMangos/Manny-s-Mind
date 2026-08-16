# Model Audit — Substitute Selection & Minimum-Cost Reliable Minutes

**Scope:** 12-phase read-only audit of the V3 production model's ability to (a) distinguish starters, sub appearances and unused players, and (b) support a "minimum-cost reliable minutes" bench strategy.

**Guardrails (Phase 1):** audit only. No production code, weights, features, configs or pipelines were modified. Obvious defects are documented here and are not silently fixed.

**Date:** 2026-08-13 · **Auditor:** opencode · **Status:** Complete (no code changes)

---

## 1. Executive Finding

**The V3 expected-minutes model cannot tell a reliable starter from a bench/sub player.** For any player with any minutes, `start_probability` saturates at ~0.95–0.97 and `expected_minutes` collapses to a per-position constant (GKP 64.1, DEF 63.6, MID 60.7, FWD 59.9). Consequently the "minimum-cost reliable minutes" philosophy is unattainable with the current model and data.

**Root cause (single chain):**
1. `services/data_loader.py:23-44` (`_PLAYER_FIELDS`) omits the real `starts` field, so it never reaches the DB.
2. `features/store.py:448-449` fabricates `starts = round(minutes/90)`.
3. `features/store.py:180-182` computes `starts_rate = starts / max(minutes_season/90, 1)` → **always 1.0** (or 0) for everyone.
4. `start_probability = 0.6 × starts_rate + 0.4 × chance_of_playing_next_round` therefore reduces to `0.6 + 0.4 × chance`, i.e. a pure function of the news feed, clamped to `[0.05, 0.97]` (`config/expected_minutes/expected_minutes_v1.yaml`).
5. Because `minutes_if_starting` is also inflated (fabricated `minutes_per_game = 90`), it always exceeds the 78-min threshold, so `substitution_risk = 0.25` for everyone.

The documented formula in `docs/expected_points.md` (§3.1–3.3, lines 145–191) describes the intended behaviour; the fabricated `starts` feature makes the actual behaviour diverge from that intent. **This is a silent modeling defect, not a crash.**

| Player | Pos | Price | Real starts (2025/26) | Model start_prob | Model exp_min |
|---|---|---|---|---|---|
| Dubravka | GKP | £4.0m | 35 | 0.95 | 64.1 |
| Petrović | GKP | £4.5m | 38 | 0.95 | 64.1 |
| Valdimarsson | GKP | £4.5m | 1 | 0.95 | 64.1 |
| Kusi-Asare | FWD | £4.5m | 0 (49 min) | 0.95 | 59.9 |

A £4.0m 35-start regular and a £4.5m near-non-player are treated as identical.

---

## 2. Current Architecture (Phase 2 — decision-layer trace)

```
FPL API ──data_loader (drops starts)──> SQLite moneyball.db ──> FeatureStore
   └── build_feature_store fabricates starts ───────────────> minutes_features()
                                                                   │
V3:  expected_minutes = start_prob × minutes_if_starting × (1 − sub_risk)   [expected_minutes_engine.py]
     xPts = xPts_per_90 × (expected_minutes / 90)                           [expected_projection_engine.py]
                                                                   │
Consumers (all inherit the blind spot):
 ├─ squad_optimizer.py:412   bench = leftovers (gkp[1:], def[4:], mid[4:], fwd[2:])
 ├─ value_engine.py          value & rating use minutes_fraction, not starts
 ├─ assistant_manager/       transfer_engine, squad_evaluator, chip_strategist (bench only for Bench Boost)
 ├─ opportunity_engine.py    xPts-driven picks
 └─ captain_engine.py        xPts-driven armband
```

- `engines/expected_points_engine.py` produces a per-90 points rate only — no minutes statement.
- `engines/expected_projection_engine.py` is the compositor: `xPts = xPts_per_90 × (expected_minutes / 90)`.
- The V2 shadow (`engines/minutes_engine.py`, `prediction_engine.py:15-29`) buckets minutes (0/30/55/70/85) from season minutes — also minutes-only, no starts.

**Finding:** every consumer treats a player as a points-per-90 machine scaled by a near-constant minutes factor. No layer distinguishes XI player vs sub vs unused.

## 3. Data Assessment (Phase 3)

| Source | Finding |
|---|---|
| Live `bootstrap-static` | `starts` present on 584/584 elements; 35 players with `starts=0 & minutes>0` (sub-only last season); 184 with `starts=0 & minutes=0` |
| `element-summary/{id}` | History **empty in preseason**; will populate per-GW minutes/starts once the season starts |
| SQLite `players` table | **No `starts` column** (verified via PRAGMA; 584 rows) |
| `services/data_loader.py:23-44` | `_PLAYER_FIELDS` omits `starts` → never fetched |
| `features/store.py:448-449` | `starts` fabricated as `round(minutes/90)` |

Example sub-only players (real starts=0) the model currently rates as 0.95-probability starters: Ünal (214m), Nwaneri (165m), Nelson (118m), Sosa (99m), Kalimuendo (89m), Soler (£4.0m, 34m).

## 4. Model Assessment (Phase 4 — empirical)

Formula (as shipped in `config/expected_minutes/expected_minutes_v1.yaml`):

```
expected_minutes = start_probability × minutes_if_starting × (1 − substitution_risk)
start_probability = clamp(0.60×starts_rate + 0.40×chance_of_playing_next_round, 0.05, 0.97)
minutes_if_starting = starts<3 ? positional_baseline : 0.60×minutes_per_game + 0.40×baseline
substitution_risk   = 0.25 if minutes_if_starting ≥ 78 else 0.10
```

Empirical behaviour (tested against the live FeatureStore, all cheap players ≤ £4.5m):

| Position | starts_rate | start_prob | minutes_if_starting | sub_risk | exp_min |
|---|---|---|---|---|---|
| GKP | 1.0 | 0.95 | 90.0 | 0.25 | **64.1** |
| DEF | 1.0 | 0.95 | 89.2 | 0.25 | **63.6** |
| MID | 1.0 | 0.95 | 85.2 | 0.25 | **60.7** |
| FWD | 1.0 | 0.95 | 84.0 | 0.25 | **59.9** |

With minutes ≥ 270 (starts ≥ 3 fabricated), `minutes_per_game = minutes/fabricated_starts = 90`, so `minutes_if_starting` is a pure function of position. With 1–2 fabricated starts, `minutes_if_starting` falls back to the positional baseline. Either way the spread between a 38-start regular and a 0-start sub is zero.

**Event-coverage assessment (the 3 questions from the brief):**
- Start probability: modeled, but degenerate (see above). No.
- Sub-appearance probability (chance of coming on): **not modeled anywhere.**
- Minutes conditional on being a sub: **not modeled.** `minutes_if_starting` only describes E[minutes | start]; `substitution_risk` is only the probability of being *subbed off* early, not of *coming on as a sub*.
- Unused-sub probability: **not modeled.**

## 5. Bench Strategy Assessment (Phase 7 — decision trace)

- `engines/squad_optimizer.py:412` — `bench = gkp[1:] + def_[4:] + mid[4:] + fwd[2:]`: the bench is simply the **leftover overflow** after filling the XI. No reliability objective, no cost/minutes optimisation, no "must-play" requirement.
- Real run: 4-5-1 formation, £78.0m spent, bench = Leno £4.5 / Tosin £4.5 / Scarlett £4.5 / N.Jackson £6.5 — cheapest/leftover, not selected for reliability.
- `services/assistant_manager/chip_strategist.py` — `bench_quality` is computed and used only for **Bench Boost** assessment.
- `services/assistant_manager/transfer_engine.py`, `squad_evaluator.py` — no bench-specific logic; every player judged identically by position.
- No existing notion of an "auto-sub chain" (who comes on when a starter misses).

**Finding:** the house's stated philosophy (minimum-cost reliable minutes) is not implemented anywhere in the squad-selection path.

## 6. Recommended Architecture (Phase 9a)

**Data (immediate, low risk):**
- Add `starts` to `_PLAYER_FIELDS` and to the `players` schema via an Alembic migration (`docs/database.md` mandates migrations for schema changes).
- Once in-season, ingest per-GW `element-summary` minutes/starts so the history is built from facts, not fabrication.
- Backfill: last-season `starts` is already available in `bootstrap-static` today (584/584 players).

**Features (after evidence):**
- `starts_rate_real` = real starts ÷ games; `minutes_per_start`; `sub_appearances`; `unused_sub_rate`; `minutes_when_sub`.

**Model — three-event minutes model (replaces the single start_prob chain):**

```
P(start)        from starts_rate_real + chance_of_playing_next_round (news)
P(sub_appear)   from sub_appearances + starts_rate_real + fixture/status signals
P(unused)       = 1 − P(start) − P(sub_appear)
expected_minutes = P(start)·E[min|start] + P(sub_appear)·E[min|sub] + P(unused)·0
```

This preserves the V3 compositor (`xPts = xPts_per_90 × expected_minutes/90`) untouched; only the minutes input improves. No `xPts_per_90` rates or weights change.

**Bench engine (future):**
- Reliability-aware bench selection: maximize expected points of the full 15 under the £100m budget, with bench players discounted by the probability the XI actually misses a game (auto-sub probability), i.e. minimise `expected_bench_deficit = Σ P(autosub triggers) × (players expected to return 0min)`.

## 7. Recommended Metrics (Phase 5-6)

- `starts_rate_real` (observed), `P(sub_appearance)`, `P(60+ minutes)`, `expected_minutes`.
- **MRM — Minimum-cost Reliable Minutes:** `reliable minutes per £1m` where "reliable" = the player's `expected_minutes` floor across their likely role (starter vs sub). Rank candidates by this; pick the cheapest that clears the reliability bar for a bench slot.
- `expected_bench_deficit` per squad (see §6) as the bench-strategy KPI.
- Bench eligibility rule (proposed threshold, needs validation): a bench slot must have `P(60+ min) ≥ 0.6` **or** price ≤ £4.0m as an explicit "never plays" £4.0 enabler — no invented thresholds used in production until validated against GW actuals (Phase 10).

## 8. Implementation Recommendation (Phase 9b)

| Horizon | Actions |
|---|---|
| **Immediate** (no model change) | 1) Add `starts` ingestion + migration; 2) fix `store.py:448-449` to use the real field (drops the fabrication); 3) surface real `starts`/`starts_rate` in the explainability panel; 4) document this defect in `ENGINEERING_HISTORY.md`. |
| **After evidence** (6–10 GWs) | Calibrate the three-event model on real per-GW starts/sub/unused data; validate before promotion (Phase 10). |
| **Future** | Reliability-aware bench optimizer + auto-sub chain simulation; injury/news blend into P(start). |

## 9. Validation Strategy (Phase 10)

Extend the existing `validation_engine` metrics (currently points-only: MAE/RMSE/bias/CI coverage) with a minutes-level battery:
1. Minutes prediction **MAE/RMSE** per position (V3 vs three-event candidate).
2. **Appearance calibration** — predicted vs realised P(start), P(sub), P(unused) in reliability buckets.
3. **P(60+) accuracy** — brier score vs realised 60+.
4. **Bench-deficit** — expected vs actual 0-min bench players per GW.
5. **Efficiency** — cost per expected point for bench slots (MRM league table).
6. Same GW-by-GW ledger discipline as V3 (append-only, version-tagged) so the candidate can run as a second shadow model.

## 10. Production Recommendation (Phase 11-12)

- **Do not modify or retire anything in V3 today.** Keep `expected_points_v1` primary and `projection_v2` shadow (`config/production/production_v1.yaml`).
- Promote the three-event minutes model to production **only after** the Phase 10 validation passes on 6–10 GWs of real data.
- The starts ingestion (Immediate) is safe to ship now — it only adds data and fixes fabrication; it does not change the model output until the minutes features are re-derived.

---

## Annex — Defects logged (no fixes applied, per audit guardrails)

| ID | Severity | Location | Description |
|---|---|---|---|
| AUD-1 | **High (silent)** | `features/store.py:448-449` | `starts` fabricated as `round(minutes/90)` → `starts_rate ≡ 1.0`, saturating start probability. Documented V3 formula is false in practice. |
| AUD-2 | High | `services/data_loader.py:23-44` | `starts` dropped at ingest; real data available in `bootstrap-static`. |
| AUD-3 | High | `engines/squad_optimizer.py:412` | Bench = leftover overflow, no reliability objective. |
| AUD-4 | Medium | V3 minutes chain | No sub-appearance / unused-sub / minutes-conditional-on-sub terms anywhere. `substitution_risk` is sub-off risk only. |
| AUD-5 | Medium | `config/expected_minutes/expected_minutes_v1.yaml` | `substitution_risk = 0.25` triggers for all players (minutes_if_starting ≥ 78 universally) — double penalises even nailed-on 90-min players. |
| AUD-6 | Info | `engines/prediction_engine.py:15-29` | V2 shadow `project_minutes` also minutes-only; add starts-based variant for comparison. |
