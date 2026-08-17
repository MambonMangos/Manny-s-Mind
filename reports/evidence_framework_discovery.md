# Historical Evidence → Current-Season Evidence Framework — Discovery & Implementation Plan

**Role:** Senior ML/Analytics Engineer · **Date:** 2026-08-16 · **Phase 1 of the evidence-framework program**
**Guardrail:** V3/xPts remains the primary production model. Nothing in this plan rewrites V3, V2 or V1, and nothing is auto-promoted. The evidence layer is an *additive, config-gated* transform applied by research/shadow paths only — production `expected_points_v1` × `expected_minutes_v1` behaviour is byte-for-byte unchanged.

---

## 1. Objective (restated)

FPL's evidence arrives at two different timescales. Before a season, we only have **historical evidence** (prior seasons, preseason signals). During the season, **current-season evidence** accumulates at a *player-specific* rate: 360 reliable minutes is a real sample; 38 minutes is not. The framework must:

1. Treat historical data as a **prior**, never as a permanent override.
2. Let current-season evidence **earn influence as it accumulates** — not by gameweek, but by evidence volume.
3. Apply **feature-specific** transition speeds (starting role moves fast; finishing/xGI profiles move slowly).
4. Expose an **evidence-strength** measure and per-feature historical/current weights.
5. Keep V3 as the prediction engine; the evidence layer only decides *how much to trust historical vs current per feature*.
6. Validate everything on historical walk-forward folds **before** any promotion consideration, and never leak future information.

## 2. Repo / architecture audit (done this phase)

| Component | Location | State |
|---|---|---|
| V3 xPts engine | `engines/expected_points_engine.py` | production; `config_version` plumbing exists (None = active, unchanged) |
| V3 minutes engine | `engines/expected_minutes_engine.py` | production; same plumbing; `historical_minutes` section is experiment-only |
| Projection engine | `engines/expected_projection_engine.py` | combines xPts/90 × minutes/90; `points_version`/`minutes_version` passthrough |
| Feature Store | `features/store.py` | minutes/xgi/fixture/value/market/availability/set-piece/trend frames; provides `starts_rate`, `minutes_per_game`, `starts`, `xg_raw/xa_raw/xgc_raw/xgi_raw` |
| Config system | `utils/config.py` `load_config(category, version)` | versioned YAML; explicit version never requires `active.yaml` entry → evidence config stays out of production selection |
| Research harness | `research/` (loader, state, identity, historical_features, calibration, preseason, validation, candidates, backtest) | historical program Phases 1–8 complete; walk-forward folds + A–F ablation + shadow registry working |
| Validation platform | `engines/validation_engine.py`, `services/learning_service.py` | DB-backed live validation; research harness is separate and offline |
| League Intelligence | `services/league_intelligence/` | strategy/analysis layer; unaffected |
| Assistant Manager | chat assistant + decision intelligence | will consume evidence explainability later (out of scope to build now) |
| DB schema | `players` has `starts` (migrated `c4d3e2f1a5b6`); research data lives under `data_research/` | OK |

**Key conclusion:** the prior historical program already built the data foundation (identity, ingestion, hist features, calibration, walk-forward validation). The genuinely new component is the **Evidence Layer** — a feature-level, evidence-strength-driven weighting between historical priors and current-season observations, plus its configuration, validation, and explainability metadata.

## 3. Data source audit (Phase 1 of the original program, re-confirmed)

| Source | Seasons | GW-level | Fields | ID mapping | Verdict |
|---|---|---|---|---|---|
| **vaastav/Fantasy-Premier-League** (pinned `8c97b2adb123863c3dd581e730f1360e89815ac2`, MIT) | 2016-17 → 2026-27 | yes (`gws/`) | minutes, starts (2022-23+), points, xG/xA/xGC (2022-23+), BPS, bonus, saves, cards, price, ownership, ICT, fixture difficulty | FPL `code` stable across seasons; `element` is not | **Primary source** — already ingested |
| Stat-Peekers/Fantasy-Premier-League-Data | ~2016-17 → 2023-24 | yes | subset of vaastav | same as vaastav | Stale fork → **rejected** |
| FPL-Core-Insights | 2024-25 → 2026-27 | yes (+lineups, match stats, Elo) | richer, incl. lineup certainty | FPL ids | **No license** → supplementary only, not ingested as backbone |
| understat (within vaastav) | 2019-20+ | no (season player tables) | shot-based xG | player names | xG proxy only; **not** used for the faithful V3 pipeline |

Every dataset used is treated as **untrusted input** (validated, provenance-pinned, never allowed to write production data — research writes only to `data_research/`).

## 4. Identity resolution strategy

- **Canonical key:** FPL `code` (stable; verified Salah=118748, Saka=223340 across 2022-23..2024-25). `element` is season-scoped. `(first,last,web)` names are unreliable (e.g. "Salah"/"M.Salah").
- Flow: `historical (season, element) → code → canonical → code → current element`. Team ids are season-scoped in vaastav; mapped via `master_team_list.csv` / `teams.csv`; the research state carries its own team map.
- **Unresolved players are flagged, never guessed:** a missing code → no prior (column left NaN) → falls back to position/team-level priors, and the evidence layer records `has_historical_prior=False`. No name-similarity matching.

## 5. Which historical features integrate reliably (now)

From the faithful seasons (2022-23..2024-25) and the previous completed season, leakage-safe per-player priors exist for:

| Feature group | Historical prior (source) | Current-season value (source) | Transition |
|---|---|---|---|
| `rate_attack` | prev xGI/90, xG/90, xA/90 (identity prior) | season-to-date xGI/90 (Feature Store) | **slow** |
| `starting` | prev starts_rate, prev starts | beta-binomial posterior on season-to-date starts (minutes engine) | **fast** |
| `minutes` | prev minutes_per_start | season-to-date minutes_per_game (Feature Store) | **fast** |
| `bonus` | prev bps/90 (identity prior; add field) | season-to-date bps/90 (Feature Store) | **slowest** |
| `team_strength` | prev-season team attack/defense adjustment (compute from prev gw data) | season-to-date team adjustment (hist_team_*) | **fast** |
| `finishing`/`creative` | 3-season shrunk multipliers (calibration) | — (not blended; inherently low-sample) | keep as historical constants, documented |
| `set_piece` | prev orders | current orders | slow; current-order fallback when no prior |

**Not integrated yet (documented, deferred):** statistical stability / role-consistency measures; comparable-player priors for new players (see §11).

## 6. Current-season evidence strength — design

`effective_minutes = w_min·minutes + w_start·starts + w_app·appearances`
`strength = floor + (1 − floor)·(1 − exp(−effective_minutes / saturation))`, capped at `max_strength`.

Sanity check against the task's own examples (config `saturation=300`, `w_start=1.5`, `w_app=0.5`, `floor=0.10`, `max=0.97`):

| Player | Evidence | strength |
|---|---|---|
| A (GW4: 4 starts, 360 min, 4 apps) | 360 + 6 + 2 = 368 | ≈ **0.74** (≈ the 0.72 example) |
| B (GW4: 0 starts, 38 min, 1 app) | 38.5 | ≈ **0.21** (weak current → prior dominant) |

Per-group **current weight** = `strength ^ group_exponent`:

| Group | exponent | w_current at strength 0.74 | w_current at strength 0.5 |
|---|---|---|---|
| starting | 0.6 | 0.84 | 0.66 |
| minutes | 0.8 | 0.79 | 0.57 |
| team_strength | 0.7 | 0.81 | 0.61 |
| rate_attack | 2.0 | 0.55 | 0.25 |
| bonus | 2.5 | 0.46 | 0.18 |

This is the philosophical core: a 4-start player has an ~84% current weight on *starting role* but only ~55% on *attacking rate*, because role changes fast and xGI profiles move slowly. **All parameters live in `config/evidence/evidence_v1.yaml` and are subject to validation (never claimed optimal a priori).**

## 7. Blending formula

`value_used(group) = w_current(group) · value_current(group) + (1 − w_current(group)) · value_historical(group)`

Applied per player per feature group. Blended results are exposed as `ev_*` columns injected by the research path before the Feature Store builds; the engines read them **only when an evidence config version is explicitly requested**. The evidence layer is **not a second prediction engine** — it produces trust weights and blended inputs, then V3 does all prediction.

## 8. Sparse-player protection & new-player handling

- Sparse current data: automatically de-weighted by the strength function (Player B above). The **floor** ensures the historical prior is never fully discarded; the **max cap** ensures noisy small samples never fully override it either.
- New FPL players / promoted / transfers with no FPL history: `has_historical_prior=False` → rate_attack blend uses **position-average prev xGI/90** (league-normalized) instead of a personal prior; starting uses the **positional start_rate_prior** already fit in calibration; team strength still applies (it is team-level, not player-level). Documented, implemented safely; comparable-player clustering is deferred.

## 9. Configuration (new, versioned, out of production selection)

`config/evidence/evidence_v1.yaml` — `accumulation` (strength inputs), `feature_groups` (per-group `hist_source`, `transition_exponent`, `floor`/`cap`), `new_player` fallbacks, `explainability` (labels for the Assistant Manager). Never referenced by `config/active.yaml`; loaded only by explicit `evidence_version`.

## 10. Validation plan (Phase 4)

Extend the existing walk-forward harness with an **evidence model (G = V3 + evidence layer)** alongside the current candidates:
- Folds unchanged: train 2022-23 → validate 2023-24; train 22-23+23-24 → validate 2024-25.
- Primary comparison: **production V3 (A) vs evidence (G)** on MAE, RMSE, bias, correlation, start accuracy, minutes MAE, and per-GW **top-10 identification** (the decision-relevant metric — captains/transfers).
- **Parameter validation:** small grid over `saturation_minutes` and a couple of group exponents on fold1; the fold1-optimal setting is then evaluated honestly on fold2 (walk-forward discipline preserved).
- **Temporal-integrity audit:** the research harness already restricts every feature to rounds `< gw_n` and completed seasons; a dedicated test re-checks that `ev_*` columns carry no future information.
- **Decision rule:** promote to *shadow* only if the evidence model is not materially worse than V3 on fold-mean metrics and is better on at least one decision-relevant metric (top-10, bias, start accuracy). If a feature group fails to help, it is documented and left out (engineering rule: use more data only when it demonstrably improves prediction).

## 11. Phased implementation

| Phase | Scope | Status |
|---|---|---|
| 1 Discovery + plan | this report | **done** |
| 2 Historical data foundation | identity, ingestion, provenance, storage, tests | done (prior program; extended with prev bps + prev team strength) |
| 3 Evidence layer | `research/evidence.py`, `config/evidence/evidence_v1.yaml`, strength + per-group weights + blend + explainability metadata, engine config-gated reads, tests | **done** |
| 4 Evidence backtesting | Model G in the ablation, parameter grid, leakage audit | **done — negative result; G does not beat D (see `reports/evidence_framework_validation.md`)** |
| 5 Shadow monitoring | register evidence candidate alongside production V3 during the live season | **not promoted — G failed the decision rule; D remains the candidate** |
| 6 Promotion decision | only after live shadow evidence + explicit decision | deferred (never auto) |

## 12. Security & safety (with Security Manager)

- All datasets: untrusted, validated schema, provenance-pinned (SOURCE_PIN), read-only.
- No secrets: configs/docs contain no keys; nothing new is fetched live (all local/pinned).
- Research writes only under `data_research/` (gitignored) and versioned configs; **historical data can never overwrite production current-season data** (separate paths, DB untouched by research).
- Evidence candidates are versioned configs, never wired into `active.yaml` / `production_v1.yaml`.

## 13. Explainability design (for future Assistant Manager)

`research/evidence.py` will emit per-player evidence metadata: `evidence_strength`, per-group `{hist_value, current_value, blended_value, current_weight}`, `has_historical_prior`, and short reason strings ("5 starts in 5 matches", "412 minutes", "current xGI/90 improving"). This is what the Assistant Manager will consume later — the LLM never computes predictions; it only reads the evidence metadata produced by the pipeline.

## 14. Deliverables of this work (in addition to this report)

Engineering: `research/evidence.py`, `config/evidence/evidence_v1.yaml`, engine config-gated reads, Model G in the ablation, tests (data/identity/evidence/sparse/new-player/missing-history/temporal). Scientific: evidence walk-forward results, feature-group evidence analysis, V3-baseline comparison, leakage assessment, shadow-or-promote recommendation. Documentation: `docs/evidence.md` + this report.
