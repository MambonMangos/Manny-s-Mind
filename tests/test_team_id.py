"""Tests for the per-session Team Context provider.

Covers the QA checklist for onboarding/session behaviour: session persistence,
never defaulting to a personal team, the Change Team workflow (clear/reset),
multiple sequential team changes, browser-refresh persistence, sidebar reset,
and URL-based pre-filling of the onboarding input.
"""

from __future__ import annotations

import pytest
import streamlit as st

from utils.team_context import (
    clear_current_team_id,
    get_current_team_id,
    is_onboarded,
    require_team,
    seed_from_url,
    set_current_team_id,
)


class _FakeQueryParams:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        assert key == "team_id"
        return self._value


class _Stop(Exception):
    pass


def _raise_stop():
    raise _Stop()


def _patch(monkeypatch, query_value=None, session_state=None):
    state = dict(session_state) if session_state else {}
    monkeypatch.setattr(st, "query_params", _FakeQueryParams(query_value))
    monkeypatch.setattr(st, "session_state", state)
    return state


# ---------------------------------------------------------------------------
# Never default to a personal team
# ---------------------------------------------------------------------------


def test_no_default_team_when_unset(monkeypatch):
    state = _patch(monkeypatch)
    assert get_current_team_id() is None
    assert not is_onboarded()
    assert state == {}


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------


def test_session_persistence(monkeypatch):
    state = _patch(monkeypatch)
    set_current_team_id(472930)
    assert get_current_team_id() == 472930
    assert is_onboarded()
    assert state["team_id"] == 472930


def test_set_then_get_roundtrips(monkeypatch):
    _patch(monkeypatch)
    set_current_team_id(123)
    assert get_current_team_id() == 123
    set_current_team_id(456)
    assert get_current_team_id() == 456


def test_corrupt_session_value_is_cleared(monkeypatch):
    state = _patch(monkeypatch, session_state={"team_id": "not-a-number"})
    assert get_current_team_id() is None
    assert "team_id" not in state


# ---------------------------------------------------------------------------
# Change Team workflow
# ---------------------------------------------------------------------------


def test_change_team_clears(monkeypatch):
    _patch(monkeypatch)
    set_current_team_id(472930)
    clear_current_team_id()
    assert get_current_team_id() is None
    assert not is_onboarded()


def test_sidebar_reset_removes_team(monkeypatch):
    state = _patch(monkeypatch)
    set_current_team_id(12345)
    clear_current_team_id()
    assert "team_id" not in state
    assert get_current_team_id() is None


def test_multiple_sequential_team_changes(monkeypatch):
    _patch(monkeypatch)
    set_current_team_id(111)
    assert get_current_team_id() == 111
    clear_current_team_id()
    assert get_current_team_id() is None
    set_current_team_id(222)
    assert get_current_team_id() == 222
    clear_current_team_id()
    set_current_team_id(333)
    assert get_current_team_id() == 333
    assert is_onboarded()


def test_browser_refresh_keeps_team(monkeypatch):
    # A Streamlit rerun/refresh re-executes the script but session_state
    # persists — the validated team must survive.
    _patch(monkeypatch)
    set_current_team_id(999)
    assert get_current_team_id() == 999
    assert is_onboarded()


# ---------------------------------------------------------------------------
# require_team gate
# ---------------------------------------------------------------------------


def test_require_team_returns_id_when_onboarded(monkeypatch):
    _patch(monkeypatch, session_state={"team_id": 777})
    assert require_team() == 777


def test_require_team_renders_onboarding_when_unset(monkeypatch):
    _patch(monkeypatch)
    rendered = []
    monkeypatch.setattr(
        "components.onboarding.render_onboarding", lambda: rendered.append(True)
    )
    monkeypatch.setattr(st, "stop", _raise_stop)
    with pytest.raises(_Stop):
        require_team()
    assert rendered == [True]


# ---------------------------------------------------------------------------
# URL pre-fill seeding (never auto-trusted)
# ---------------------------------------------------------------------------


def test_url_param_seeds_input(monkeypatch):
    _patch(monkeypatch, query_value="12345")
    assert seed_from_url() == 12345


def test_url_param_first_of_list(monkeypatch):
    _patch(monkeypatch, query_value=["111", "222"])
    assert seed_from_url() == 111


def test_url_param_invalid_returns_none(monkeypatch):
    _patch(monkeypatch, query_value="abc")
    assert seed_from_url() is None


def test_url_param_out_of_range_returns_none(monkeypatch):
    _patch(monkeypatch, query_value="999999999999")
    assert seed_from_url() is None


def test_url_param_absent_returns_none(monkeypatch):
    _patch(monkeypatch)
    assert seed_from_url() is None
