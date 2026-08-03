"""Shared HTTP client for the FPL API.

Single source of truth for SSL handling, headers, timeouts, and retry logic.
All service modules should use ``fpl_get()`` instead of implementing their own.
"""

from __future__ import annotations

import logging
import time
import warnings
from typing import Any

import certifi
import requests
from urllib3.exceptions import InsecureRequestWarning

from utils.constants import (
    FPL_API_ALLOW_INSECURE_SSL,
    FPL_API_BACKOFF_BASE,
    FPL_API_BASE_URL,
    FPL_API_MAX_RETRIES,
    FPL_API_TIMEOUT,
    FPL_USER_AGENT,
)

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

logger = logging.getLogger(__name__)

_HEADERS: dict[str, str] = {"User-Agent": FPL_USER_AGENT}
_TIMEOUT: int = FPL_API_TIMEOUT
_MAX_RETRIES: int = FPL_API_MAX_RETRIES
_BACKOFF_BASE: float = FPL_API_BACKOFF_BASE

_RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


def fpl_get(endpoint: str) -> Any:
    """Make a GET request to the FPL API and return parsed JSON.

    Retries on transient failures with exponential backoff:
      - SSL errors (known macOS certifi issue)
      - Connection errors / timeouts
      - HTTP 429 (rate limit), 5xx (server errors)
    Raises on non-retryable HTTP errors (4xx except 429) and after
    exhausting all retries.
    """
    url = f"{FPL_API_BASE_URL}{endpoint}"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers=_HEADERS,
                timeout=_TIMEOUT,
                verify=certifi.where(),
            )
        except requests.exceptions.SSLError:
            if not FPL_API_ALLOW_INSECURE_SSL:
                logger.error(
                    "SSL verification failed for %s. Refusing to retry insecurely. "
                    "Set FPL_API_ALLOW_INSECURE_SSL=true to permit (NOT recommended).",
                    url,
                )
                raise
            logger.warning(
                "SSL verification failed (%s); retrying without verification "
                "(FPL_API_ALLOW_INSECURE_SSL=true)",
                f"attempt {attempt + 1}/{_MAX_RETRIES + 1}",
            )
            try:
                resp = requests.get(
                    url,
                    headers=_HEADERS,
                    timeout=_TIMEOUT,
                    verify=False,
                )
            except _RETRYABLE_EXCEPTIONS:
                if attempt < _MAX_RETRIES:
                    _wait_and_log(attempt)
                    continue
                raise
        except _RETRYABLE_EXCEPTIONS:
            if attempt < _MAX_RETRIES:
                _wait_and_log(attempt)
                continue
            raise

        if resp.status_code == 429 and attempt < _MAX_RETRIES:
            retry_after = int(resp.headers.get("Retry-After", _BACKOFF_BASE * (2**attempt)))
            logger.warning(
                "Rate limited (attempt %d/%d), retrying in %ds",
                attempt + 1,
                _MAX_RETRIES + 1,
                retry_after,
            )
            time.sleep(retry_after)
            continue

        if resp.status_code in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES:
            _wait_and_log(attempt)
            continue

        resp.raise_for_status()
        return resp.json()

    raise requests.exceptions.RetryError(
        f"Failed to fetch {url} after {_MAX_RETRIES + 1} attempts"
    )


def _wait_and_log(attempt: int) -> None:
    """Sleep with exponential backoff and log a warning."""
    wait = _BACKOFF_BASE * (2**attempt)
    logger.warning(
        "Transient failure (attempt %d/%d), retrying in %.1fs",
        attempt + 1,
        _MAX_RETRIES + 1,
        wait,
    )
    time.sleep(wait)
