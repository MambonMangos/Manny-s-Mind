"""Single source of truth for all application-wide constants.

Every module that needs a shared value should import from here.
No other file should define its own copy of these values.

Scoring weights are loaded from config/weights/ YAML files.
To change weights, edit the YAML files — never edit this file.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ── FPL Team ────────────────────────────────────────────────────────────────

TEAM_ID: int = 472930

# ── FPL API ─────────────────────────────────────────────────────────────────

FPL_API_BASE_URL: str = "https://fantasy.premierleague.com/api"
FPL_USER_AGENT: str = "MoneyballFPL/1.0"

# ── FPL Rules ───────────────────────────────────────────────────────────────

FPL_BUDGET: float = 100.0
MAX_SEASON_MINUTES: int = 38 * 90  # 3420

# ── Positions ───────────────────────────────────────────────────────────────
# Maps FPL element_type (int) → position abbreviation (str).

POSITION_MAP: dict[int, str] = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
POSITIONS: list[str] = list(POSITION_MAP.values())  # ["GKP", "DEF", "MID", "FWD"]

# ── Scoring weights ─────────────────────────────────────────────────────────
# Loaded from config/weights/ YAML. Fallback to hardcoded defaults if config
# is unavailable (e.g. during tests or before config files exist).

_DEFAULT_WEIGHTS: dict[str, float] = {
    "minutes": 0.30,
    "xgi_per_90": 0.25,
    "value": 0.15,
    "team_strength": 0.10,
    "fixture": 0.10,
    "ownership": 0.05,
    "set_pieces": 0.05,
}


def _load_weights() -> dict[str, float]:
    """Load weights from config YAML. Falls back to defaults on error."""
    try:
        from utils.config import load_config
        config = load_config("weights")
        vs = config.get("value_score", {})
        weights = {k: float(vs.get(k, v)) for k, v in _DEFAULT_WEIGHTS.items()}
        if abs(sum(weights.values()) - 1.0) < 1e-6:
            return weights
        logger.warning("Loaded weights sum to %.4f, using defaults", sum(weights.values()))
    except Exception as e:
        logger.warning("Failed to load weights from config: %s", e)
    return _DEFAULT_WEIGHTS


WEIGHTS: dict[str, float] = _load_weights()

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-6, "WEIGHTS must sum to 1.0"
