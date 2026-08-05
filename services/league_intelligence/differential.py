"""Differential Scoring engine — config-driven strategic scores.

Combines projection, minutes, fixture, ownership, transfer-velocity and price
signals into a single 0..1 differential score. All weights come from
config/league_intelligence/league_intelligence_v1.yaml — changing behaviour is
a config change, never a code change.

Design contract:
  - ``xpts`` is carried through from the prediction layer UNCHANGED. The score
    is a league-strategy signal layered on top, not a re-prediction.
  - Feature normalisation is min-max across the candidate pool, so the score is
    relative to the players being compared, not an absolute.
"""

from __future__ import annotations

import logging

from utils.config import get_active_version, load_config

logger = logging.getLogger(__name__)

# Features the scorer knows how to read from the feature store row.
_WEIGHT_KEYS = (
    "projected_points",
    "expected_minutes",
    "fixture_attractiveness",
    "inverse_ownership",
    "transfer_velocity",
    "price_movement",
    "rotation_risk",
)


class DifferentialScorer:
    """Scores players by differential appeal using config-driven weights.

    Usage::

        scorer = DifferentialScorer()  # loads active league_intelligence config
        candidates = [{"player_id":.., "xpts":.., "ownership":.., ...}, ...]
        scored = scorer.score(candidates)          # list[DifferentialScore]
        top = scorer.top_differentials(candidates) # list[DifferentialScore]
    """

    def __init__(self, config: dict | None = None):
        self._config = config or load_config("league_intelligence")
        diff = self._config.get("differential", {})
        weights = diff.get("weights", {})
        total = sum(weights.get(k, 0.0) for k in _WEIGHT_KEYS)
        if total <= 0:
            raise ValueError("differential.weights must have positive total")
        self._weights = {k: weights.get(k, 0.0) / total for k in _WEIGHT_KEYS}
        self._threshold = float(diff.get("threshold", 0.60))
        self._ownership_power = float(diff.get("ownership_power", 1.0))
        self.version = get_active_version("league_intelligence")

    # ------------------------------------------------------------------
    # Feature extraction (feature-store row → raw inputs)
    # ------------------------------------------------------------------
    @staticmethod
    def _row_features(row: dict) -> dict:
        """Extract raw strategy features from an enriched store row.

        The orchestrator overlays ``projected_points`` / ``expected_minutes``
        onto a copy of each store row, so this reader can stay flat and pure.
        """
        pid = int(row.get("player_id", 0) or 0)
        xpts = float(row.get("projected_points", row.get("xpts", 0.0)) or 0.0)
        minutes = float(row.get("expected_minutes", 0.0) or 0.0)
        ownership = float(row.get("selected_by_percent", 0.0) or 0.0)
        vel_in = float(row.get("transfers_in_event", 0.0) or 0.0)
        vel_out = float(row.get("transfers_out_event", 0.0) or 0.0)
        price_move = float(row.get("cost_change_event", 0.0) or 0.0)

        strength_home = float(row.get("strength_overall_home", 0.0) or 0.0)
        strength_away = float(row.get("strength_overall_away", 0.0) or 0.0)
        fixture_attractiveness = (strength_home + strength_away) / 2.0

        rotation_risk = float(row.get("rotation_risk", 0.0) or 0.0)
        if "rotation_risk" not in row and minutes > 0:
            rotation_risk = max(0.0, 1.0 - min(minutes / 90.0, 1.0))

        return {
            "player_id": pid,
            "web_name": str(row.get("web_name", f"P{pid}")),
            "position": str(row.get("position", "UNK")),
            "xpts": xpts,
            "expected_minutes": minutes,
            "fixture_attractiveness": fixture_attractiveness,
            "ownership": ownership,
            "transfer_velocity": vel_in - vel_out,
            "price_movement": price_move,
            "rotation_risk": rotation_risk,
        }

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def score(self, candidates: list[dict]) -> list:
        """Return a scored ``DifferentialScore`` for each candidate.

        ``candidates`` are raw feature rows (store rows or dicts with
        player_id / web_name / position / xpts / ownership / ...). Scoring is
        min-max normalised per feature across the whole pool.
        """
        from services.league_intelligence.models import DifferentialScore

        if not candidates:
            return []

        rows = [self._row_features(c) for c in candidates]
        scores = self._normalise_and_weight(rows)
        return [
            DifferentialScore(
                player_id=r["player_id"],
                web_name=r["web_name"],
                position=r["position"],
                xpts=round(r["xpts"], 2),
                expected_minutes=round(r["expected_minutes"], 2),
                global_ownership=round(r["ownership"], 2),
                transfer_velocity=round(r["transfer_velocity"], 2),
                price_movement=round(r["price_movement"], 2),
                fixture_attractiveness=round(r["fixture_attractiveness"], 2),
                score=round(s["score"], 4),
                is_differential=s["score"] >= self._threshold,
                components=s["components"],
                config_version=self.version,
            )
            for r, s in zip(rows, scores)
        ]

    def top_differentials(
        self,
        candidates: list[dict],
        squad_ids: list[int] | None = None,
        top_n: int | None = None,
    ) -> list:
        """Return the highest-scoring differentials, optionally excluding squad.

        Without a squad, returns the global top-N differentials across the
        candidate pool. With a squad, returns top-N differentials the user
        does NOT already own (pure suggestions — nothing is applied).
        """
        if top_n is None:
            top_n = int(self._config.get("differential", {}).get("top_n", 10))
        scored = self.score(candidates)
        squad_set = set(squad_ids or [])
        eligible = [d for d in scored if d.player_id not in squad_set]
        eligible.sort(key=lambda d: d.score, reverse=True)
        return eligible[:top_n]

    # ------------------------------------------------------------------
    # Internal: min-max normalise + weighted sum
    # ------------------------------------------------------------------
    def _normalise_and_weight(self, rows: list[dict]) -> list[dict]:
        min_max: dict[str, tuple[float, float]] = {}
        for key in (
            "xpts",
            "expected_minutes",
            "fixture_attractiveness",
            "transfer_velocity",
            "price_movement",
            "rotation_risk",
        ):
            vals = [r[key] for r in rows]
            lo, hi = min(vals), max(vals)
            min_max[key] = (lo, hi) if hi > lo else (0.0, 1.0)
        # Ownership is inverted and non-linear (power curve) before normalising.
        own_vals = [r["ownership"] ** self._ownership_power for r in rows]
        lo, hi = min(own_vals), max(own_vals)
        own_range = (lo, hi) if hi > lo else (0.0, 1.0)

        def _norm(v: float, rng: tuple[float, float]) -> float:
            lo, hi = rng
            return 0.0 if hi == lo else (v - lo) / (hi - lo)

        out = []
        for r in rows:
            components = {
                "projected_points": round(_norm(r["xpts"], min_max["xpts"]), 4),
                "expected_minutes": round(_norm(r["expected_minutes"], min_max["expected_minutes"]), 4),
                "fixture_attractiveness": round(_norm(r["fixture_attractiveness"], min_max["fixture_attractiveness"]), 4),
                "inverse_ownership": round(1.0 - _norm(r["ownership"] ** self._ownership_power, own_range), 4),
                "transfer_velocity": round(_norm(r["transfer_velocity"], min_max["transfer_velocity"]), 4),
                "price_movement": round(_norm(r["price_movement"], min_max["price_movement"]), 4),
                "rotation_risk": round(_norm(r["rotation_risk"], min_max["rotation_risk"]), 4),
            }
            score = sum(self._weights[k] * components[k] for k in _WEIGHT_KEYS)
            out.append({"score": score, "components": components, **r})
        return out
