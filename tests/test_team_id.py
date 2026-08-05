"""Tests for per-viewer team selection via the ``?team_id=`` URL param."""

from __future__ import annotations

import streamlit as st

from utils.constants import TEAM_ID, get_active_team_id


class _FakeQueryParams:
    def __init__(self, value):
        self._value = value

    def get(self, key):
        assert key == "team_id"
        return self._value


def test_defaults_to_env_team_id(monkeypatch):
    monkeypatch.setattr(st, "query_params", _FakeQueryParams(None))
    assert get_active_team_id() == TEAM_ID


def test_url_param_overrides_env(monkeypatch):
    monkeypatch.setattr(st, "query_params", _FakeQueryParams("12345"))
    assert get_active_team_id() == 12345


def test_url_param_takes_first_of_list(monkeypatch):
    monkeypatch.setattr(st, "query_params", _FakeQueryParams(["111", "222"]))
    assert get_active_team_id() == 111


def test_invalid_url_param_falls_back(monkeypatch):
    monkeypatch.setattr(st, "query_params", _FakeQueryParams("not-a-number"))
    assert get_active_team_id() == TEAM_ID


def test_missing_streamlit_falls_back(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "streamlit", None)
    assert get_active_team_id() == TEAM_ID
