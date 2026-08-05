# League Intelligence Layer — Architecture, Modules & Roadmap

**Owner:** ML / Analytics Engineer
**Phase 1 scope:** Architecture + foundation service. **No prediction behaviour changed.**

## 1. Purpose

Manny's FPL House V3 already forecasts points (V2/V3 projections) and turns them
into recommendations. The **League Intelligence Layer** adds the missing
dimension: **league context**. It answers questions the prediction layer
intentionally does not:

- "Everyone in my mini-league owns Haaland — if he blanks, I lose nothing; if he
  hauls, I gain nothing."
- "Rival #3 is chasing me and owns my captain. Should I pick a different one?"
- "Nobody in my league owns this mid-priced midfielder with elite xPts — a
  differential."
- "Chips remaining + fixture swings — what move maximises *league position
  gain*, not raw points?"

### Core design principle (non-negotiable)

> **The prediction engine is never contaminated by league strategy.**

Projections remain objective, measurable, validated and reproducible. League
context is layered **on top of** predictions, inside the League Intelligence
Layer, and only ever shapes **recommendations**. Every recommendation carries
the untouched projection value (`xpts`) alongside a league-aware `strategy_score`.

### Where it sits

```
FPL API  ──►  Data ingestion ──►  Feature Store (features/store.py)
                                      │
                                      ▼
                              ┌──────────────────────┐
                              │  PREDICTION LAYER     │  V2 + V3 (objective)
                              │  projections + CIs    │  append-only ledger
                              └──────────────────────┘
                                      │  (read-only projections)
                                      ▼
                              ┌──────────────────────┐
                              │ DECISION INTELLIGENCE │  comparison_reports.py
                              └──────────────────────┘
                                      ▼
                              ┌──────────────────────┐
                              │  LEAGUE INTELLIGENCE  │  ★ this layer ★
                              │  services/league_intelligence/
                              └──────────────────────┘
                                      │  (typed recommendations)
                                      ▼
                              ┌──────────────────────┐
                              │ RECOMMENDATION ENGINE │  assistant_manager
                              └──────────────────────┘
                                      ▼
                              ┌──────────────────────┐
                              │   VALIDATION PLATFORM │  learning_service thresholds
                              └──────────────────────┘
```

## 2. What is built in Phase 1 (this change)

The full foundation, implemented and tested (`tests/test_league_intelligence.py`):

| Phase | Deliverable | Module | Status |
|---|---|---|---|
| 1 | League Intelligence Foundation service | `engine.py` | ✅ implemented |
| 2 | Community Intelligence provider interfaces | `providers.py` | ✅ implemented |
| 3 | Mini-League Analyzer (analysis only) | `mini_league.py` | ✅ implemented |
| 4 | Rival Tracker (analysis only) | `rivals.py` | ✅ implemented |
| 5 | Effective Ownership Engine (global/league/rival) | `effective_ownership.py` | ✅ implemented |
| 6 | Differential Scoring (config-driven weights) | `differential.py` | ✅ implemented |
| 7 | Game Theory Engine — **architecture & interfaces only** | `game_theory.py` | ✅ interfaces |

### Module responsibilities

**`models.py`** — pure dataclasses, no streamlit, no DB:
`PlayerExposure`, `DifferentialScore`, `StrategicRecommendation`,
`MiniLeagueAnalysis`, `RivalAnalysis`, `LeagueIntelligenceReport`.

**`engine.py`** — `run_league_intelligence(store, projections, team_id,
gameweek_id, ...)` orchestrator. Consumes projections (read-only), builds
exposures, scores differentials, runs league/rival analysis (when data is
provided), and emits typed `StrategicRecommendation`s. All inputs injectable;
one call → one self-contained report, no hidden state.

**`providers.py`** — the boundary to external data. Protocols
(`OwnershipProvider`, `CaptainPollProvider`, `CommunityStatsProvider`,
`MiniLeagueProvider`) so **no external source is ever hard-coded into the
layer**. Two reference implementations:
- `FeatureStoreOwnershipProvider` — offline, always available, reads
  `selected_by_percent` / `transfers_*` / `cost_change_event` from the store.
- `FPLApiMiniLeagueProvider` — league standings + rival squads via the official
  FPL API (`fpl_get`, shared retry/SSL handling). Every call degrades to empty
  on failure.

**`effective_ownership.py`** — `compute_effective_ownership(selected, captained,
tc)` = selected% + captained% + triple-captained%, matching the community
convention; plus `league_ownership()` / `rival_ownership()` helpers and an
`EffectiveOwnershipEngine` producing `PlayerExposure` rows. Pure functions →
standalone or orchestrator use.

**`differential.py`** — `DifferentialScorer`: min-max normalises 7 features
(xPts, expected minutes, fixture attractiveness, inverse ownership, transfer
velocity, price movement, rotation risk) then applies **config-driven weights**
from `config/league_intelligence/league_intelligence_v1.yaml`. `xpts` is always
carried through unchanged.

**`mini_league.py`** — `MiniLeagueAnalyzer`: common players, league
differentials, captain overlap, ownership overlap, risk profile, Jaccard squad
similarity and competitive threats. **Analysis only.**

**`rivals.py`** — `RivalTracker`: per-rival squad diff, captain comparison,
differential opportunities (players no rival owns), transfer divergence, weak
positions by xPts, aggregate xPts totals. **Analysis only.**

**`game_theory.py`** — `PositionGainInput`, `ExpectedLeaguePositionGain`,
`GameTheoryEngine` (Protocol), `get_game_theory_engine()` guard that returns an
unimplemented engine while `game_theory.enabled: false` in v1. Interface only.

## 3. Project structure changes

```
config/
  active.yaml                                  ← + league_intelligence: league_intelligence_v1
  league_intelligence/
    league_intelligence_v1.yaml                ← ★ new (weights, thresholds, tiers)
services/
  league_intelligence/
    __init__.py                                ← run_league_intelligence, LeagueIntelligenceReport
    engine.py                                  ← ★ orchestrator
    models.py                                  ← ★ dataclasses
    providers.py                               ← ★ interfaces + 2 reference impls
    effective_ownership.py                     ← ★ EO engine
    differential.py                            ← ★ config-driven scorer
    mini_league.py                             ← ★ analysis only
    rivals.py                                  ← ★ analysis only
    game_theory.py                             ← ★ architecture only
tests/
  test_league_intelligence.py                  ← ★ 16 tests (synthetic, no network)
```

## 4. External data sources (Phase 2+)

The provider interfaces are ready; concrete sources plug in without code
changes. Confirmed candidates (research, 2026):

| Data | Source | Notes |
|---|---|---|
| Effective ownership (live, post-deadline) | fantasyfootballpundit.com/fpl-effective-ownership/ | EO table from top-10k → top-100k; captain %; top 10k/1k/100 ownership. ~30 min after deadline. |
| Overall ownership / transfer stats | Official FPL bootstrap (already in FeatureStore) | `selected_by_percent`, `transfers_in/out_event` — used offline today. |
| Top-10k / elite ownership | LiveFPL, fpl.page, fpl.team | Samples (~325 teams) — label as estimates. |
| Captain polls | Community polls + FPL gameweek `most_captained` (past GWs) | For current GW, polls are predictive; treat as soft signals. |
| Mini-league standings | FPL API `/leagues-classic/{id}/standings/` | `FPLApiMiniLeagueProvider` already wired. Private leagues need auth — v1 assumes public/accessible. |
| Rival squads | FPL API `/entry/{id}/event/{gw}/picks/` | Per-rival squad (captain = multiplier 2). |

**Rule:** no source is hard-coded. A new source = a new provider class
implementing the existing Protocol, injected at the call site.

## 5. Engineering constraints honoured

- **No hidden state** — every run is `run_league_intelligence(...)` → one report.
- **Append-only validation preserved** — this layer never writes to the
  prediction ledger; it only reads projections.
- **No duplicate calculations** — ownership/transfer/price features come from
  the existing Feature Store, never re-computed.
- **Dependency injection** — providers passed in; defaults are offline.
- **Config-driven** — weights/thresholds/tiers in versioned YAML; changing
  behaviour is a config change, not a code change.
- **Independently testable** — 16 tests, synthetic data, no network.

## 6. Roadmap (remaining phases)

1. **Community Intelligence wiring (Phase 2)** — implement a
   `CommunityStatsProvider` that pulls live EO/top-10k data into the existing
   provider interface; feed captain polls into the captaincy-hedge
   recommendation. Confidence thresholds from `learning_service`.
2. **Mini-League data pipeline (Phase 3)** — persist league standings +
   per-entry squads snapshots so the analyzer runs historically, not just live.
3. **Rival tracking persistence (Phase 4)** — store per-rival transfer history
   for true `transfer_divergence` over `rivals.transfer_divergence_window`.
4. **Live EO engine calibration (Phase 5)** — validate EO vs league-standings
   outcomes; tune `exposure_tiers`.
5. **Differential weight tuning (Phase 6)** — use the validation platform to
   back-test differentials that beat league-average on actuals; tune
   `differential.weights` in a new config version.
6. **Game Theory Engine (Phase 7)** — implement `ExpectedLeaguePositionGain`
   from `game_theory.py` once (a) differential scoring is validated and
   (b) ≥1 gameweek of mini-league data exists. Flip `game_theory.enabled: true`.
7. **Integration (done in the V3-production promotion)** — `run_assistant` now
   calls `run_league_intelligence` with the V3 production projections, exposing
   exposures/differentials on the `AssistantReport.league_intelligence` field.
   A dedicated League Intelligence tab remains on the roadmap.

## 7. Risks, assumptions & dependencies

**Assumptions**
- Mini-league standings/squads are accessible without private auth (v1).
- `selected_by_percent` in the store is current enough for the target gameweek.
- Community EO/top-10k figures are treated as *estimates* until calibrated.

**Dependencies**
- Prediction layer (V2/V3) — read-only input, must remain stable.
- Feature Store — ownership/transfer/price columns.
- Config system (`utils/config.py`) — `league_intelligence` category now active.
- `learning_service` evidence thresholds — for any confidence gating.

**Risks**
- **Garbage league data** → misleading recommendations. Mitigation: providers
  degrade to empty, and `inputs` in the report records exactly what was
  available; never trust a league figure computed from an empty sample.
- **EO contamination fear** — the top reason for this design. Mitigation: the
  layer never writes to the prediction ledger and carries `xpts` unchanged;
  enforced by test.
- **Over-fitting differential weights** → config versions + validation platform.
- **API rate limits** on per-entry squad fetches → reuse
  `fpl_get` retry/backoff; cache per gameweek.

## 8. Immediate vs deferred

**Immediate (shipped now):**
- Foundation service, models, provider interfaces, EO engine, differential
  scorer, mini-league analyzer, rival tracker, game-theory interfaces.
- Versioned config + tests (111 suite green, ruff clean).

**Deferred (needs data before they mean anything):**
- Live EO / top-10k provider implementation (Phase 2 data pipeline).
- Mini-league + rival historical persistence.
- Any game-theory scoring logic.
- UI integration.

**Recommendation:** ship this foundation, run the mini-league pipeline for a
few gameweeks, then build differential calibration on real league outcomes
before enabling game theory. The interfaces are stable; everything downstream
is a provider or a config version.
