"""Tests for FPL Team ID validation (services.team_validation).

Covers the QA checklist: valid, invalid, empty, non-numeric, API timeout,
API failure, and that internal exceptions never leak to the visitor.
"""

from __future__ import annotations

import requests
from requests import HTTPError

from services.team_validation import TeamValidationStatus, validate_team_id

VALID = TeamValidationStatus.VALID
INVALID_INPUT = TeamValidationStatus.INVALID_INPUT
NOT_FOUND = TeamValidationStatus.NOT_FOUND
ERROR = TeamValidationStatus.ERROR


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _patch_fpl(monkeypatch, fn):
    monkeypatch.setattr("services.team_validation.fpl_get", fn)


def _no_call(*args, **kwargs):
    raise AssertionError("fpl_get must not be called")


# ---------------------------------------------------------------------------
# Valid team
# ---------------------------------------------------------------------------


def test_valid_team_id(monkeypatch):
    seen = {}

    def fake(endpoint, **kwargs):
        seen["endpoint"] = endpoint
        assert kwargs["timeout"] == 10
        return {
            "id": 12345,
            "name": "The Gunners",
            "player_first_name": "Jane",
            "player_last_name": "Doe",
        }

    _patch_fpl(monkeypatch, fake)
    result = validate_team_id(" 12345 ")
    assert result.status is VALID
    assert result.team_id == 12345
    assert result.team_name == "The Gunners"
    assert result.manager_name == "Jane Doe"
    assert seen["endpoint"] == "/entry/12345/"


def test_valid_team_without_optional_fields(monkeypatch):
    def fake(endpoint, **kwargs):
        return {"id": 99}

    _patch_fpl(monkeypatch, fake)
    result = validate_team_id("99")
    assert result.status is VALID
    assert result.team_id == 99
    assert result.team_name == ""
    assert result.manager_name == ""


# ---------------------------------------------------------------------------
# Invalid / not found / failure
# ---------------------------------------------------------------------------


def test_team_not_found(monkeypatch):
    def fake(endpoint, **kwargs):
        raise HTTPError("404", response=_FakeResponse(404))

    _patch_fpl(monkeypatch, fake)
    result = validate_team_id("12345")
    assert result.status is NOT_FOUND
    assert result.team_id == 12345
    assert "not found" in result.message.lower()


def test_http_5xx_is_friendly_error(monkeypatch):
    def fake(endpoint, **kwargs):
        raise HTTPError("500", response=_FakeResponse(500))

    _patch_fpl(monkeypatch, fake)
    result = validate_team_id("12345")
    assert result.status is ERROR
    assert "not found" not in result.message.lower()


def test_api_timeout(monkeypatch):
    def fake(endpoint, **kwargs):
        raise requests.exceptions.Timeout()

    _patch_fpl(monkeypatch, fake)
    result = validate_team_id("12345")
    assert result.status is ERROR
    assert "contact Fantasy Premier League" in result.message


def test_api_connection_error(monkeypatch):
    def fake(endpoint, **kwargs):
        raise requests.exceptions.ConnectionError()

    _patch_fpl(monkeypatch, fake)
    result = validate_team_id("12345")
    assert result.status is ERROR
    assert "contact Fantasy Premier League" in result.message


def test_unexpected_exception_is_hidden(monkeypatch):
    def fake(endpoint, **kwargs):
        raise RuntimeError("internal failure: secret_detail")

    _patch_fpl(monkeypatch, fake)
    result = validate_team_id("12345")
    assert result.status is ERROR
    assert "internal failure" not in result.message
    assert "secret_detail" not in result.message
    assert "Traceback" not in result.message


# ---------------------------------------------------------------------------
# Input sanitisation
# ---------------------------------------------------------------------------


def test_empty_input(monkeypatch):
    _patch_fpl(monkeypatch, _no_call)
    assert validate_team_id("").status is INVALID_INPUT


def test_whitespace_input(monkeypatch):
    _patch_fpl(monkeypatch, _no_call)
    assert validate_team_id("   ").status is INVALID_INPUT


def test_none_input(monkeypatch):
    _patch_fpl(monkeypatch, _no_call)
    assert validate_team_id(None).status is INVALID_INPUT


def test_non_numeric_input(monkeypatch):
    _patch_fpl(monkeypatch, _no_call)
    assert validate_team_id("12a45").status is INVALID_INPUT
    assert validate_team_id("abc").status is INVALID_INPUT
    assert validate_team_id("12.5").status is INVALID_INPUT
    assert validate_team_id("-12").status is INVALID_INPUT
    assert validate_team_id("1_000").status is INVALID_INPUT


def test_zero_and_negative_input(monkeypatch):
    _patch_fpl(monkeypatch, _no_call)
    assert validate_team_id("0").status is INVALID_INPUT
    assert validate_team_id("-5").status is INVALID_INPUT


def test_out_of_range_input(monkeypatch):
    _patch_fpl(monkeypatch, _no_call)
    assert validate_team_id("100000000").status is INVALID_INPUT
    assert validate_team_id("99999999999").status is INVALID_INPUT


def test_invalid_input_message_is_friendly(monkeypatch):
    _patch_fpl(monkeypatch, _no_call)
    result = validate_team_id("")
    assert result.status is INVALID_INPUT
    assert "numbers only" in result.message
