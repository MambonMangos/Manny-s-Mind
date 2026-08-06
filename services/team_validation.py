"""Team ID validation for public onboarding.

Verifies a visitor-entered FPL Team ID against the official FPL API before it
becomes the session's active team. Returns a structured, user-friendly result —
raw exceptions and API internals never reach the UI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import requests
from requests import HTTPError

from services.api_client import fpl_get

logger = logging.getLogger(__name__)

# Validation must fail fast: one short attempt at a sub-endpoint, not the
# full retry loop used by data loading.
VALIDATION_TIMEOUT_SECONDS = 10
VALIDATION_MAX_RETRIES = 1
_MAX_TEAM_ID = 99_999_999
_MAX_TEAM_ID_DIGITS = len(str(_MAX_TEAM_ID))


class TeamValidationStatus(str, Enum):
    """Outcome of a Team ID validation attempt."""

    VALID = "valid"
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass
class TeamValidationResult:
    """Structured outcome — never raises and never leaks exception details."""

    status: TeamValidationStatus
    team_id: int | None = None
    team_name: str = ""
    manager_name: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------

def _sanitize(raw: str | None) -> int | None:
    """Return a clean positive team id, or ``None`` for anything suspicious.

    Accepts digits only (no signs, decimals, whitespace runs) within a sane
    bound, mirroring FPL entry id ranges. This also defuses any content that
    could be interpreted as a path, query string, or log-injection payload.
    """
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if len(value) > _MAX_TEAM_ID_DIGITS:
        return None
    if not value.isdigit():
        return None
    team_id = int(value)
    if team_id < 1 or team_id > _MAX_TEAM_ID:
        return None
    return team_id


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_team_id(raw: str | None) -> TeamValidationResult:
    """Validate a visitor-supplied Team ID against the FPL API.

    Returns a :class:`TeamValidationResult`; never raises for external reasons.
    """
    team_id = _sanitize(raw)
    if team_id is None:
        return TeamValidationResult(
            status=TeamValidationStatus.INVALID_INPUT,
            message="Please enter a valid Team ID — numbers only.",
        )

    try:
        data = fpl_get(
            f"/entry/{team_id}/",
            timeout=VALIDATION_TIMEOUT_SECONDS,
            max_retries=VALIDATION_MAX_RETRIES,
        )
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return TeamValidationResult(
                status=TeamValidationStatus.NOT_FOUND,
                team_id=team_id,
                message=(
                    "Team ID not found. Double-check your number and try again."
                ),
            )
        logger.warning("Team validation failed for team %d (HTTP %s)", team_id, exc.response.status_code if exc.response is not None else "?")
        return TeamValidationResult(
            status=TeamValidationStatus.ERROR,
            team_id=team_id,
            message="Unable to validate this team right now. Please try again in a moment.",
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        return TeamValidationResult(
            status=TeamValidationStatus.ERROR,
            team_id=team_id,
            message="Unable to contact Fantasy Premier League. Please check your connection and try again.",
        )
    except Exception:  # never expose internals to the visitor
        logger.exception("Unexpected team validation error for team %d", team_id)
        return TeamValidationResult(
            status=TeamValidationStatus.ERROR,
            team_id=team_id,
            message="Something went wrong while checking your team. Please try again.",
        )

    if not isinstance(data, dict) or "id" not in data:
        return TeamValidationResult(
            status=TeamValidationStatus.ERROR,
            team_id=team_id,
            message="Unable to validate this team right now. Please try again.",
        )

    team_name = str(data.get("name") or "").strip()
    manager_name = " ".join(
        str(data.get(k) or "").strip() for k in ("player_first_name", "player_last_name")
    ).strip()
    return TeamValidationResult(
        status=TeamValidationStatus.VALID,
        team_id=team_id,
        team_name=team_name,
        manager_name=manager_name,
        message="Team found.",
    )
