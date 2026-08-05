"""Tests for per-viewer team selection via the ``?team_id=`` URL param and the
sidebar ``Your FPL team ID`` input."""

from __future__ import annotations

import streamlit as st

from utils.constants import TEAM_ID, get_active_team_id


class _FakeQueryParams:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        assert key == "team_id"
        return self._value


def _patch(monkeypatch, query_value=None, session_value=None):
    monkeypatch.setattr(st, "query_params", _FakeQueryParams(query_value))
    state = {} if session_value is None else dict(session_value)
    monkeypatch.setattr(st, "session_state", state)
    return state


def test_defaults_to_env_team_id(monkeypatch):
    _patch(monkeypatch)
    assert get_active_team_id() == TEAM_ID


def test_url_param_overrides_env(monkeypatch):
    _patch(monkeypatch, query_value="12345")
    assert get_active_team_id() == 12345


def test_url_param_takes_first_of_list(monkeypatch):
    _patch(monkeypatch, query_value=["111", "222"])
    assert get_active_team_id() == 111


def test_invalid_url_param_falls_back(monkeypatch):
    _patch(monkeypatch, query_value="not-a-number")
    assert get_active_team_id() == TEAM_ID


def test_session_input_used_when_no_url(monkeypatch):
    _patch(monkeypatch, session_value={"team_id_input": 999})
    assert get_active_team_id() == 999


def test_url_overrides_session_input(monkeypatch):
    _patch(monkeypatch, query_value="12345", session_value={"team_id_input": 999})
    assert get_active_team_id() == 12345


def test_invalid_session_input_falls_back(monkeypatch):
    _patch(monkeypatch, session_value={"team_id_input": "abc"})
    assert get_active_team_id() == TEAM_ID


def test_missing_streamlit_falls_back(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "streamlit", None)
    assert get_active_team_id() == TEAM_ID
