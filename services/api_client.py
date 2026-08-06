"""Shared HTTP client for the FPL API.

Single source of truth for SSL handling, headers, timeouts, and retry logic.
All service modules should use ``fpl_get()`` instead of implementing their own.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import certifi
import requests

from utils.constants import (
    FPL_API_ALLOW_INSECURE_SSL,
    FPL_API_BACKOFF_BASE,
    FPL_API_BASE_URL,
    FPL_API_MAX_RETRIES,
    FPL_API_TIMEOUT,
    FPL_USER_AGENT,
)

logger = logging.getLogger(__name__)

# Maximum number of seconds to sleep on a 429 response, even if the API
# requests longer. Prevents an abusive/misconfigured Retry-After value from
# hanging a worker indefinitely.
_MAX_RETRY_AFTER_SECONDS = 60

_HEADERS: dict[str, str] = {"User-Agent": FPL_USER_AGENT}
_TIMEOUT: int = FPL_API_TIMEOUT
_MAX_RETRIES: int = FPL_API_MAX_RETRIES
_BACKOFF_BASE: float = FPL_API_BACKOFF_BASE

_RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503, 504}
_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


def _redact_url(url: str) -> str:
    """Redact per-team path segments so FPL entry ids never reach the logs."""
    return re.sub(r"/entry/\d+", "/entry/{team_id}", url)


def fpl_get(endpoint: str, timeout: int | None = None, max_retries: int | None = None) -> Any:
    """Make a GET request to the FPL API and return parsed JSON.

    Retries on transient failures with exponential backoff:
      - SSL errors (known macOS certifi issue)
      - Connection errors / timeouts
      - HTTP 429 (rate limit), 5xx (server errors)
    Raises on non-retryable HTTP errors (4xx except 429) and after
    exhausting all retries.

    *timeout* and *max_retries* override the module defaults (used by the
    onboarding validator to fail fast).
    """
    url = f"{FPL_API_BASE_URL}{endpoint}"
    request_timeout = _TIMEOUT if timeout is None else timeout
    attempts = _MAX_RETRIES if max_retries is None else max_retries

    if urlparse(url).scheme != "https" and not FPL_API_ALLOW_INSECURE_SSL:
        raise requests.exceptions.InvalidURL(
            f"Refusing non-HTTPS request to {FPL_API_BASE_URL}. "
            "Set FPL_API_ALLOW_INSECURE_SSL=true to permit (NOT recommended)."
        )

    for attempt in range(attempts + 1):
        try:
            resp = requests.get(
                url,
                headers=_HEADERS,
                timeout=request_timeout,
                verify=certifi.where(),
            )
        except requests.exceptions.SSLError:
            if not FPL_API_ALLOW_INSECURE_SSL:
                logger.error(
                    "SSL verification failed for %s. Refusing to retry insecurely. "
                    "Set FPL_API_ALLOW_INSECURE_SSL=true to permit (NOT recommended).",
                    _redact_url(url),
                )
                raise
            logger.warning(
                "SSL verification failed (%s); retrying without verification "
                "(FPL_API_ALLOW_INSECURE_SSL=true)",
                f"attempt {attempt + 1}/{attempts + 1}",
            )
            try:
                resp = requests.get(
                    url,
                    headers=_HEADERS,
                    timeout=request_timeout,
                    verify=False,
                )
            except _RETRYABLE_EXCEPTIONS:
                if attempt < attempts:
                    _wait_and_log(attempt)
                    continue
                raise
        except _RETRYABLE_EXCEPTIONS:
            if attempt < attempts:
                _wait_and_log(attempt)
                continue
            raise

        if resp.status_code == 429 and attempt < attempts:
            retry_after = _parse_retry_after(resp.headers, attempt)
            logger.warning(
                "Rate limited (attempt %d/%d), retrying in %ds",
                attempt + 1,
                attempts + 1,
                retry_after,
            )
            time.sleep(retry_after)
            continue

        if resp.status_code in _RETRYABLE_STATUSES and attempt < attempts:
            _wait_and_log(attempt)
            continue

        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            # requests embeds the full URL (including /entry/<id>) in the
            # message; re-raise with the same type but a redacted message so
            # the FPL team id never leaks into logs or the UI.
            raise requests.exceptions.HTTPError(
                f"{resp.status_code} error for {_redact_url(resp.url or '<unknown>')}",
                response=resp,
            ) from exc
        return resp.json()

    raise requests.exceptions.RetryError(
        f"Failed to fetch {_redact_url(url)} after {attempts + 1} attempts"
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


def _parse_retry_after(headers: Any, attempt: int) -> int:
    """Parse the Retry-After header safely, clamped to _MAX_RETRY_AFTER_SECONDS.

    Falls back to exponential backoff when the header is missing or malformed.
    """
    default = int(_BACKOFF_BASE * (2**attempt))
    raw = headers.get("Retry-After")
    if raw is None:
        return min(default, _MAX_RETRY_AFTER_SECONDS)
    try:
        return min(int(raw), _MAX_RETRY_AFTER_SECONDS)
    except (TypeError, ValueError):
        logger.warning("Malformed Retry-After header %r; using backoff", raw)
        return min(default, _MAX_RETRY_AFTER_SECONDS)
