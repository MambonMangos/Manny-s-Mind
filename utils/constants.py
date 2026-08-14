"""Single source of truth for all application-wide constants.

Every module that needs a shared value should import from here.
No other file should define its own copy of these values.

Scoring weights are loaded from config/weights/ YAML files.
To change weights, edit the YAML files — never edit this file.
"""

from __future__ import annotations

import logging
import os

import utils.env  # noqa: F401  (load .env before reading environment variables)

logger = logging.getLogger(__name__)


# ── Environment helpers ──────────────────────────────────────────────────────
# Values are read from environment variables with safe defaults. This is the
# "Environment Variables → config/ → Safe Defaults" hierarchy from Phase 1.

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Environment variable %s=%r is not an integer; using %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Environment variable %s=%r is not a number; using %s", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ── FPL Team ────────────────────────────────────────────────────────────────
# The viewer's FPL Team ID is RUNTIME state, not application configuration.
# It lives in the per-session Team Context (utils.team_context) and is set only
# after validation on the onboarding page. There is deliberately NO hardcoded
# default team — an unvalidated visitor has no team.

# ── FPL API ─────────────────────────────────────────────────────────────────
# Override FPL_API_BASE_URL to point at a mirror or test stub.

FPL_API_BASE_URL: str = os.getenv(
    "FPL_API_BASE_URL", "https://fantasy.premierleague.com/api"
)
FPL_USER_AGENT: str = os.getenv("FPL_USER_AGENT", "MoneyballFPL/1.0")

# HTTP client behaviour (used by services/api_client.py)
FPL_API_TIMEOUT: int = _env_int("FPL_API_TIMEOUT", 30)
FPL_API_MAX_RETRIES: int = _env_int("FPL_API_MAX_RETRIES", 3)
FPL_API_BACKOFF_BASE: float = _env_float("FPL_API_BACKOFF_BASE", 1.0)

# NEVER enable in production: permits retrying API calls with TLS verification
# disabled. Default off — API failures are loud instead of silently insecure.
FPL_API_ALLOW_INSECURE_SSL: bool = _env_bool("FPL_API_ALLOW_INSECURE_SSL", False)

# ── Data freshness ───────────────────────────────────────────────────────────
# How old FPL data must be before it is re-fetched (seconds).

DATA_STALENESS_SECONDS: int = _env_int("DATA_STALENESS_SECONDS", 3600)

# ── Conversational Assistant (LLM) ──────────────────────────────────────────
# Optional deployment overrides for the chat assistant. When empty, the
# config/llm/ YAML category supplies the defaults. The API key itself is a
# secret and is read via the secrets-aware helper in services.assistant_chat
# (never here and never in the YAML).

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "")
LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")

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
    except Exception as e:  # noqa: BLE001 - config load must never crash the app
        logger.warning("Failed to load weights from config: %s", e)
    return _DEFAULT_WEIGHTS


WEIGHTS: dict[str, float] = _load_weights()

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-6, "WEIGHTS must sum to 1.0"
