# ML Workstream Report (Phase 1) — ML / Analytics Engineer

## Executive Summary

Phase 1 was **review-only** for ML. The prediction architecture was documented end-to-end (engine ownership map, technical debt, post-GW1 roadmap). **No prediction, weight, or validation behaviour was changed** — per the engineering directive.

## Completed Work

1. **Engine ownership map** — 16 engines categorised V2 / V1(legacy) / merged (`docs/prediction.md`).
2. **Technical debt register** — 9 items (TD-1..TD-9) with severity, location, and impact:
   - **HIGH**: V1 engines parallel to V2 (TD-1); feature logic duplicated between Feature Store and engines (TD-2); CI/variance weights duplicated across engines (TD-3); hardcoded player-rating split instead of config-driven (TD-4, `engines/value_engine.py`).
   - **MEDIUM**: `iterrows()` hot loops (TD-5); validation engine coupled to DB/CRUD (TD-6); missing FK indexes (TD-7).
   - **LOW**: in-process staleness (TD-8); silent fixture fallback (TD-9).
3. **Post-GW1 improvement roadmap** — 7 prioritised items, each a behaviour-preserving refactor validated by evidence before the next step.
4. **Validation platform documented** — metrics, CI calibration, version comparison, persistence, gaps (`docs/validation.md`).
5. **No code changes** to `engines/`, `features/`, or weights.

## Risks

| Risk | Severity | Notes |
|---|---|---|
| V1 and V2 engines produce divergent results simultaneously | HIGH | Retirement (TD-1) intentionally deferred until GW1 evidence |
| Feature duplication can silently diverge | HIGH | TD-2 — single source should be the Feature Store |
| Dual uncertainty implementations | MEDIUM | TD-3 — consolidate after validation data exists |
| Hardcoded rating split in `value_engine.py` ignores `player_rating` config | MEDIUM | TD-4 — quick fix once config-drive approach is approved |

## Recommendations

1. **Do not touch engines until GW1 validation data exists.** Prioritise roadmap item 6 (validation evidence loop).
2. Fix TD-4 (config-driven rating) first when changes are permitted — smallest, highest-clarity win.
3. Route all feature computation through the Feature Store to prevent TD-2 divergence.

## Handoff

Owner: ML. `docs/prediction.md` is the authoritative reference. Next meaningful ML work is after GW1 actuals land: baseline the V2 pipeline vs V1, then execute the roadmap in order.
