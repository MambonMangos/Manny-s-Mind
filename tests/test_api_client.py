"""Tests for services.api_client (SSL, retry, redaction).

SEC-01  fpl_get refuses non-HTTPS requests (fail closed).
SEC-02  URL redaction hides /entry/<id> segments from logs.
SEC-03  Retries on 429/5xx with backoff; raises RetryError when exhausted.
SEC-04  SSL verification failure raises loudly when insecure mode is disabled.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

import pytest
import requests

from services import api_client


def test_refuses_non_https():
    """SEC-01: non-HTTPS endpoint refused when insecure mode is off."""
    with (
        mock.patch.object(api_client, "FPL_API_BASE_URL", "http://localhost:9999"),
        mock.patch.object(api_client, "FPL_API_ALLOW_INSECURE_SSL", False),
        pytest.raises(requests.exceptions.InvalidURL),
    ):
        api_client.fpl_get("bootstrap-static")
    print("PASS: non-HTTPS refused (fail closed)")


def test_redact_url_hides_entry_ids():
    """SEC-02: /entry/<id> path segments are redacted."""
    redacted = api_client._redact_url(
        "https://fantasy.premierleague.com/api/entry/472930/transfers"
    )
    assert "472930" not in redacted
    assert redacted == "https://fantasy.premierleague.com/api/entry/{team_id}/transfers"
    print("PASS: entry ids redacted from URLs")


def test_retry_on_429_then_success():
    """SEC-03: 429 triggers retry; a later success is returned."""
    from requests import Response

    def make_resp(status):
        r = Response()
        r.status_code = status
        r._content = b"{}"
        return r

    with (
        mock.patch("services.api_client.time.sleep") as sleep_mock,
        mock.patch.object(
            api_client.requests, "get",
            side_effect=[make_resp(429), make_resp(200)],
        ) as get_mock,
        mock.patch.object(api_client, "FPL_API_ALLOW_INSECURE_SSL", False),
    ):
        result = api_client.fpl_get("entry/1", timeout=1, max_retries=2)

    assert get_mock.call_count == 2
    assert result is not None
    sleep_mock.assert_called_once()
    print("PASS: retried once after 429 and succeeded")


def test_retry_exhaustion_raises():
    """SEC-03: persistent 503 raises RetryError after attempts are exhausted."""
    from requests import Response

    def make_resp(status):
        r = Response()
        r.status_code = status
        r._content = b"{}"
        return r

    with (
        mock.patch("services.api_client.time.sleep"),
        mock.patch.object(
            api_client.requests, "get",
            side_effect=[make_resp(503), make_resp(503), make_resp(503)],
        ),
        mock.patch.object(api_client, "FPL_API_ALLOW_INSECURE_SSL", False),
        pytest.raises(Exception) as exc_info,
    ):
        api_client.fpl_get("entry/472930", timeout=1, max_retries=2)

    assert "503 error for" in str(exc_info.value)
    assert "472930" not in str(exc_info.value), (
        "HTTPError message must be redacted (no raw entry id)"
    )
    print("PASS: retries exhausted and raised with redacted URL")


def test_ssl_failure_is_loud_without_insecure_mode():
    """SEC-04: SSL error raises (never retries insecurely) unless enabled."""
    from requests.exceptions import SSLError

    with (
        mock.patch.object(api_client.requests, "get", side_effect=SSLError("boom")),
        mock.patch.object(api_client, "FPL_API_ALLOW_INSECURE_SSL", False),
        pytest.raises(SSLError),
    ):
        api_client.fpl_get("entry/1", timeout=1, max_retries=3)
    print("PASS: SSL failure is loud (no insecure retry by default)")


if __name__ == "__main__":
    passed = 0
    failed = 0

    tests = [
        ("SEC-01  refuse non-HTTPS", test_refuses_non_https),
        ("SEC-02  redact entry ids", test_redact_url_hides_entry_ids),
        ("SEC-03  retry on 429", test_retry_on_429_then_success),
        ("SEC-03  exhaustion raises", test_retry_exhaustion_raises),
        ("SEC-04  SSL fail-closed", test_ssl_failure_is_loud_without_insecure_mode),
    ]

    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
            print("RESULT: PASS")
            passed += 1
        except Exception as e:  # noqa: BLE001 - test harness must record the failure
            print(f"RESULT: FAIL — {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"TOTAL: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}")

    if failed > 0:
        sys.exit(1)
