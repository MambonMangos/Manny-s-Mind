# Historical FPL Data Audit — V3 Backtesting Feasibility

**Role:** ML/Analytics + Data Engineering + QA · **Phase 0 of the Historical Research Program** · **Date:** 2026-08-13
**Guardrail:** This is an audit only. **No production V3 code, config, Feature Store, or DB schema was modified.** `expected_points_v1.yaml`, `expected_minutes_v1.yaml`, `production_v1.yaml`, engines, and the live Feature Store are untouched.

**Sources checked (live, against the actual repos on 2026-08-13):**
1. `vaastav/Fantasy-Premier-League`
2. `Stat-Peekers/Fantasy-Premier-League-Data`
3. `olbauday/FPL-Core-Insights`
4. Supporting: vaastav `understat/`, FPL API (already in our stack), `master_team_list.csv`, `DATA_DICTIONARY.md`

---

## 1. Executive Summary

Historical FPL data is **real and rich**, and it can answer most of the Director's research questions — **but the exact V3 input set is only reconstructable from the 2022-23 season onward.** This is the single most important constraint and it changes the proposed train/test design.

Key facts established by inspecting the actual CSV schemas per season:

- **Per-gameweek `starts` exists only from 2022-23 onward** (vaastav `gws/gw*.csv` and `players_raw.csv`). For 2016-17 → 2021-22 it is **absent** in both the gameweek files and the season files.
- **FPL API xG/xA/xGC exists only from 2022-23 onward.** No xG columns in any vaastav gameweek file before 2022-23; `expected_goals` appears in `players_raw.csv` from 2022-23. An xG proxy exists via `understat/` for 2019-20+ (different measure, separate provenance — see §4).
- **Position (`GKP/DEF/MID/FWD`) and team name appear per-GW only from 2020-21** (2016-17 and 2018-19 gw files use `name` only).
- **Everything else V3 needs** — minutes, points, goals, assists, BPS, bonus, saves, cards, price (`value`), ownership (`selected`), transfers, fixture difficulty, clean sheets, ICT, was_home/opponent — is present **for all 11 seasons (2016-17 → 2026-27)**.
- **`Stat-Peekers/Fantasy-Premier-League-Data` is a stale fork of vaastav** (older README, no `xP` lookahead caveat, no data dictionary) → **rejected as a primary source.**
- **`FPL-Core-Insights` is excellent for 2024-25 → 2026-27** (per-gameweek snapshots, `lineups.csv`, match stats, Elo) but **covers only 3 seasons** and has **no formal license** → usable as a supplementary/enrichment source, not the backbone.

**Consequence for the program:** a *faithful* full-V3 backtest (xPts/90 × expected minutes, both computed from V3's actual inputs) is possible for **2022-23, 2023-24, 2024-25**. The Director's proposed split (train 2019-23 → validate 2023-24 → test 2024-25) is **not fully supportable** for the *full* V3; it is supportable for the *xPts/90 component* only if we accept a documented substitute for xG in 2019-20 → 2021-22 (actual-goals-based proxies or Understat). This is exactly the kind of constraint the audit is meant to surface *before* modelling.

---

## 2. Source Evaluation

### 2.1 vaastav/Fantasy-Premier-League — PRIMARY SOURCE (recommended)
| Criterion | Assessment |
|---|---|
| Provenance | Community-maintained canonical FPL dataset since 2016; directly mirrors the FPL API at scrape time. 1.8k stars / 897 forks / 528 commits. |
| License | **MIT** (verified: `LICENSE`). Explicit and permissive. |
| Seasons | 2016-17 → 2026-27 (11). Weekly updates stopped end of 2024-25; now 3 scheduled updates/season (start, Jan window, season end) — fine for research. |
| Structure | `players_raw.csv` (full API snapshot), `cleaned_players.csv`, `gws/gw1..gwN.csv`, `gws/merged_gw.csv`, `fixtures.csv` (2018-19+), `teams.csv` (2019-20+), `understat/` (2019-20+), `players/<name>_<id>/gw.csv + history.csv`, `master_team_list.csv` (cross-season team IDs). |
| Documentation | Comprehensive `DATA_DICTIONARY.md` (verified live). |
| Known issues | **`xP` lookahead caveat** (first-party, documented in README + dictionary): `xP` = FPL `ep_this` scraped *post-gameweek*; may contain post-match info. **GW35 expected points are all 0** (errata). Schema drifts across seasons (§3). |

### 2.2 Stat-Peekers/Fantasy-Premier-League-Data — REJECTED
A **fork of vaastav** (0 stars, 0 forks, 362 commits, stale README without the `xP` caveat or data dictionary). Adds nothing; introduces provenance risk. **Do not use.** If a fork is ever needed, fork vaastav directly and pin a commit.

### 2.3 olbauday/FPL-Core-Insights — SUPPLEMENT (2024-25+)
| Criterion | Assessment |
|---|---|
| Provenance | Active project powering fplcore.com; 186 stars / 47 forks / 1,657 commits; updated **twice daily** via GitHub Actions. Inspired by vaastav. |
| License | **None found** (no LICENSE file; README says "feel free to use… if possible link back"). Informal permission — **needs a written confirmation or license addition before production use.** |
| Seasons | **2024-2025, 2025-2026, 2026-2027 only** (verified via repo listing). |
| Strengths | Per-gameweek snapshot folders (`By Gameweek/GW{x}/`), `lineups.csv`, `shots.csv`, `xg_by_minute.csv`, `playermatchstats.csv` (start_min/finish_min — enables substitute research), team Elo, cup/Euro coverage, `player_gameweek_stats.csv` with **deadline-stamped** `now_cost`/`selected_by_percent`/`form`. |
| Leakage | GW{x} folder is a **post-GW snapshot** (contains GW{x} results). Correct use: pre-GW{x} state = GW{x-1} folder + `fixtures.csv`. Same discipline as vaastav. |
| Role | Enrichment for recent seasons and ground-truth `starts`/substitute events via lineups. Not the backbone (3 seasons, no license). |

### 2.4 Supporting sources
- **Understat** (bundled in vaastav `understat/`, 2019-20+): match-level xG/xA with `id_dict.csv` mapping Understat↔FPL ids. **Different xG model than FPL's API values** — usable only as a *labelled proxy* for 2019-20 → 2021-22, with its own caveats (season label = start year, per-match files include the match itself → must align by `date` before prediction cutoff).
- **FPL API** (already in our stack via `services/api_client.py`): current season. Our live DB already has real `starts` (Phase 1 workstream) and `chance_of_playing_next_round`, confirming the "today" side of the pipeline.
- **ClubElo** (via FPL-Core-Insights `elo` column): team-strength history 2024-25+. Not needed for the baseline.

---

## 3. Per-Season Schema Availability Matrix (verified from real CSV headers)

| Season | GW files | per-GW starts | per-GW xG | per-GW position/team | players_raw starts | players_raw xG | fixtures.csv | teams.csv | understat |
|---|---|---|---|---|---|---|---|---|---|
| 2016-17 | `gws/` (merged only*) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 2017-18 | `gws/` (merged only*) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 2018-19 | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| 2019-20 | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| 2020-21 | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ |
| 2021-22 | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ |
| 2022-23 | ✓ | **✓** | **✓** | ✓ | **✓** | **✓** | ✓ | ✓ | ✓ |
| 2023-24 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2024-25 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2025-26 / 2026-27 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (curated) |

\* 2016-17 and 2017-18 were contributed as `merged_gw.csv`; need a listing check before relying on per-GW files. Regardless, they lack starts/xG.

**Consistent across ALL seasons (usable for every season):** `minutes`, `total_points`, `goals_scored`, `assists`, `clean_sheets`, `goals_conceded`, `own_goals`, `penalties_saved/missed`, `yellow_cards`, `red_cards`, `saves`, `bonus`, `bps`, `ict_index`, `influence`, `creativity`, `threat`, `value` (price per-GW), `selected` (ownership count per-GW), `transfers_in/out/balance`, `was_home`, `opponent_team`, `kickoff_time`, `fixture`.

**Schema drift hazards to encode as tests:** column presence differs by season (e.g., `expected_goals` only 2022-23+; `starts` only 2022-23+; `position`/`team` only 2020-21+; `xP` only 2020-21+; 2016-17/2018-19 `name` format differs and 2018-19 appends `_<element>` to names).

---

## 4. V3 Feature → Historical Equivalent Map

Source of truth for what V3 actually consumes (from `engines/expected_points_engine.py`, `engines/expected_minutes_engine.py`, `features/store.py`, `config/expected_points/expected_points_v1.yaml`, `config/expected_minutes/expected_minutes_v1.yaml`).

| V3 Feature | Historical Equivalent (vaastav) | Seasons | Quality | Usable for faithful V3? |
|---|---|---|---|---|
| xG (→ xg_90) | `expected_goals` | 2022-23+ | Official FPL model | **Yes, 2022-23+ only** |
| xA (→ xa_90) | `expected_assists` | 2022-23+ | Official FPL model | **Yes, 2022-23+ only** |
| xGI (→ xgi) | `expected_goal_involvements` | 2022-23+ | Derived | Yes, 2022-23+ |
| xGC (→ xgc_90, CS prob) | `expected_goals_conceded` | 2022-23+ | Official FPL model | **Yes, 2022-23+ only** |
| minutes (games_played, per-90 denom) | `minutes` | 2016-17+ | Complete | **Yes, all seasons** |
| starts (→ starts_rate, minutes_per_game) | `starts` | **2022-23+ only** | Complete where present | **Yes, 2022-23+ only**; unavailable earlier — do NOT fabricate |
| BPS (→ expected_bonus) | `bps` | 2016-17+ | Complete | Yes, all seasons |
| saves (GKP) | `saves` | 2016-17+ | Complete | Yes, all seasons |
| yellow/red cards | `yellow_cards`, `red_cards` | 2016-17+ | Complete | Yes, all seasons |
| set-piece roles (penalty/FK/corner order) | `penalties_order`, `direct_freekicks_order`, `corners_and_indirect_freekicks_order` | penalties_order 2021-22+; full trio from 2022-23 (verify 2022-23+) | Present later seasons | Partial (2021-22+); fall back to "no role" pre-2021-22 |
| fixture difficulty (fixture_map) | `team_h_difficulty`/`team_a_difficulty` in `fixtures.csv` | 2018-19+ | Pre-match FDR | Yes, 2018-19+ |
| team strength | `strength*` in `teams.csv` | 2019-20+ | **Point-in-time hazard** (see §5.4) | Yes, with timing guard |
| price (value) | `value` per-GW in gw files; `now_cost` in players_raw | 2016-17+ | Complete | Yes, all seasons |
| ownership (selected_by_percent) | `selected` count per-GW; `selected_by_percent` season | 2016-17+ | Complete | Yes, all seasons |
| transfers (net/velocity) | `transfers_in`, `transfers_out`, `transfers_balance` | 2016-17+ | Complete | Yes, all seasons |
| chance_of_playing_next_round | `chance_of_playing_next_round` (players_raw) | 2016-17+ | Season-snapshot hazard (§5.5) | Yes, with timing guard |
| form / ICT / event_points | `form`, `ict_index`, `influence`, `creativity`, `threat` | 2016-17+ | Complete | Yes, all seasons |
| position (GKP/DEF/MID/FWD) | `position` in gw files; `element_type` in players_raw | gw 2020-21+; element_type all seasons | Complete | Yes (element_type from players_raw everywhere) |

**Bottom line:** the xPts/90 engine's *underlying rates* (xG/xA/xGC, starts) are only reconstructable 2022-23+; the *scoring components* (BPS, saves, cards, position values) and the *market/value components* (price, ownership, transfers) are available for all 11 seasons.

---

## 5. Data-Leakage Assessment (the critical requirement)

Each hazard below must become an enforced, tested rule in the ingestion layer.

1. **`xP` (ep_this) is a documented lookahead trap.** vaastav's own README states scraped `xP` may be post-match. FPL-Core-Insights also stores `ep_this`/`ep_next`. **Rule: never use any `xP`/`ep_this`/`ep_next` column as a feature.** (We build our own xPts/90 — we don't need theirs.) Test: assert the backtest feature set contains no `xP`/`ep_this`/`ep_next`.
2. **Per-GW results vs pre-GW state.** `gw{N}.csv` contains GW N outcomes. **Rule: a prediction for GW N may only consume `gws/gw1..gw{N-1}` for results and cumulative features.** Same for FPL-Core-Insights: use `By Gameweek/GW{N-1}/` + `fixtures.csv`.
3. **`value`/`selected`/`transfers` timing.** These columns in `gw{N}.csv` are deadline-stamped for GW N (price/ownership at the GW N deadline) but the row also carries GW N results. **Rule:** read *snapshot columns* (`value`, `selected`, `transfers_*`) from `gw{N}` only if we treat them as "as of GW N deadline" (acceptable — managers knew them before kickoff) **or** conservatively from `gw{N-1}`; never read results from `gw{N}`. Default policy: **results ≤ N-1, snapshots ≤ N (deadline-stamped), fixtures for N (pre-match difficulty).** Encode and test.
4. **`teams.csv` strength is a season-level snapshot, not per-GW.** A single `teams.csv` per season cannot represent the *mid-season* strength that managers saw before each GW. FPL's strength values drift through the season. **Rule:** treat `strength*` as "season snapshot" and either (a) exclude the drift component by using it only as a season-level prior, or (b) mark the feature as approximate for pre-GW reconstruction. Document the choice; do not silently use end-of-season strength for early-GW predictions.
5. **`players_raw.csv` is one snapshot per season** (taken at the season's final scrape). Its season-cumulative fields (`total_points`, `minutes`, `selected_by_percent`, `chance_of_playing_next_round`, `form`, `now_cost`, `starts`, `expected_*`) **must never be used as pre-GW features** — they are end-of-season values. **Rule:** pre-GW cumulative features are computed by summing/aggregating `gw1..gw{N-1}` only. `players_raw.csv` is used solely for **static identity/position/set-piece metadata** (element_type, team, order columns where present), with timing noted per column.
6. **`merged_gw.csv` is a cumulative convenience file.** Its rows are the *same* gw-file rows; no additional hazard beyond (2), but prefer raw `gw*.csv` for explicitness.
7. **Understat match files contain the match itself.** For any Understat-based xG proxy, align to the match `date` and include only matches with `date < prediction deadline`. Season labels are start-years; map correctly.
8. **Promotion/relegation and team IDs.** `master_team_list.csv` gives per-season team→id. Team IDs are not stable across seasons (relegated teams vacate IDs). **Rule:** key all joins on `(season, team_id)` and use `master_team_list.csv` + `players_raw.element_type` for cross-season identity. Player `element` (FPL id) is stable within a season but can change across seasons (returning players keep codes, not ids); use `players_raw.code`/name + `player_idlist.csv` for cross-season identity.

**Leakage test contract (QA):** for each (season, GW N, player): construct the feature vector using only files/rows with timestamps `< deadline(GW N)`. Unit test: inject a fabricated "future" value into `gw{N}` and assert the backtest for GW N is unaffected.

---

## 6. Reconstructing the Historical V3 Prediction State

Per (season, GW N), the pre-GW-N state is built as:

```
state(N) = {
  results   : aggregated from gw1..gw(N-1)      # cumulative minutes, xG/xA/xGC (2022-23+), starts (2022-23+),
                                                 # bps, saves, cards, points, ICT, form(rolling), etc.
  snapshots : value, selected, transfers_in/out from gw(N-1) (or gw(N) deadline-stamped — see §5.3)
  fixtures  : difficulty/home-away for GW N from fixtures.csv
  team      : strength* from teams.csv (season snapshot — see §5.4)
  identity  : element_type/position, set-piece orders, code for cross-season join
}
→ FeatureStore (existing builder, fed historical df + fixture_map)
→ project_expected_points + project_expected_minutes  (existing V3 engines, read-only)
→ prediction for GW N   vs   actuals from gw(N) (points, minutes, starts, sub/appearance flags)
```

This reuses the **production V3 engines unchanged** — the research program runs them against reconstructed historical states without touching production code paths. The Feature Store builder is reused as-is; we feed it historical dataframes. Any ingestion change needed lives in the research layer, not in `features/store.py` (the audit found no reason to modify the store).

---

## 7. Feasibility per Director's Research Questions

| Question | Feasible with | Constraint |
|---|---|---|
| How well would V3 perform historically? | 2022-23, 2023-24, 2024-25 | Full faithful backtest needs starts + xG (2022-23+). Older seasons need labelled proxies. |
| Which features predict future points? (correlation/importance) | 2016-17+ | Fully supported for minutes, points, price, ownership, transfers, BPS, saves, cards, ICT, fixture. |
| xPts/90 as the cornerstone? | 2022-23+ (xG-based); 2019-20+ (proxy) | Compare xPts/90 vs points/90 vs xGI/90 vs minutes vs ownership per position, per season. |
| Expected minutes / starts predictability | 2022-23+ | Per-GW starts unavailable before 2022-23 — **do not fabricate**; mark feature unavailable (per brief). |
| Substitute behaviour (start/sub/unused, min-if-start, etc.) | 2022-23+ (gw starts); 2024-25+ (FPL-Core-Insights `lineups.csv`, `playermatchstats` start/finish_min) | The richest substitute research (lineup-level) is 2024-25+; basic started-vs-sub from `starts` 2022-23+. |
| Price vs reliable minutes (MCRM evidence) | 2022-23+ (starts needed) | Same starts constraint. |
| Walk-forward model comparison | 2022-23+ for V3-faithful; otherwise on proxy-labelled data | Only 3-4 usable seasons for full V3; rolling-origin over them is thin — report stability, not significance. |
| V3 weights justified? (ablation) | 2022-23+ (faithful); partial all seasons | Ablations needing xG/starts are limited to 2022-23+. |

**Honest constraint:** with faithful V3 inputs spanning ~3-4 seasons, we can establish *which components are weak/strong* and *which features predict*, but we should **explicitly label the sample-size limit** and avoid claims of statistical significance on 3 seasons. The Director's instruction "Insufficient evidence → say so" applies to the multi-season stability claims.

---

## 8. Risks & Recommendations

1. **No fabricating starts pre-2022-23.** The brief is explicit. If the minutes research needs earlier data, the only options are: restrict to 2022-23+, or use the API's per-season `starts` from `history_past` (verified live, 5 seasons) as a *season-level* prior — not per-GW.
2. **Vend the datasets.** Pin vaastav at a commit SHA and record it; do not live-fetch from `master` into the research DB. FPL-Core-Insights needs a license decision before any tracked use.
3. **Never merge historical ingestion into the production DB.** Research data lives in a separate, clearly-labelled store (research DB / parquet) with its own versioning. Production DB untouched.
4. **Reuse V3 engines read-only**; keep research wrappers in a research module. No changes to `engines/`, `features/store.py`, or config.
5. **Enforce the leakage rules as unit tests** (§5), including the "GW N cannot see GW N+" test the brief requires — this is the highest-priority QA artifact.
6. **CI cost:** the research suite must stay green and isolated (existing conftest isolation already protects the live DB; research tests get their own fixtures).

---

## 9. Proposed Next Steps (Phase A — pending Director/engineering go-ahead)

1. Vendor pinned vaastav data + verify 2016-17/2017-18 `gws/` layout (merged-only seasons).
2. Build a research data layer (separate store): per-season ingestion, schema validation, per-season column presence assertions.
3. Implement the leakage-safe feature-state builder (state(N) per §6) + the leakage test contract (§5.9).
4. Reconstruct historical states and run the **V3 baseline backtest** (2022-23 → 2024-25 faithful; 2019-20 → 2021-22 proxy-labelled, clearly marked) → Deliverable B/C.
5. Then feature analysis → minutes/substitute analysis → candidate models — each as its own reviewed milestone. No production changes until the evidence-review gate.

**Current status: V3 untouched. Audit delivered. Awaiting go-ahead on Phase A.**

---

*Prepared during a read-only session. Schema facts verified live against the source repositories on 2026-08-13. No production code modified.*
