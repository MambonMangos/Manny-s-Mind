"""Tests for write-action access control (``utils/access.py``)."""

from __future__ import annotations

from utils import access


def _set_token(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ADMIN_TOKEN", token)


def test_no_token_means_unrestricted(monkeypatch):
    _set_token(monkeypatch, None)
    assert access.is_admin_enforced() is False
    assert access.is_admin_token_valid("anything") is True
    assert access.is_admin_token_valid(None) is True


def test_token_enforced(monkeypatch):
    _set_token(monkeypatch, "s3cret")
    assert access.is_admin_enforced() is True
    assert access.is_admin_token_valid("s3cret") is True
    assert access.is_admin_token_valid("wrong") is False
    assert access.is_admin_token_valid("") is False
    assert access.is_admin_token_valid(None) is False


def test_require_admin_unrestricted(monkeypatch):
    _set_token(monkeypatch, None)
    assert access.require_admin() is True


def test_admin_authorized_false_by_default(monkeypatch):
    _set_token(monkeypatch, "s3cret")
    import streamlit as st

    monkeypatch.setattr(st, "session_state", {})
    assert access.admin_authorized() is False
    assert access.require_admin() is False


def test_admin_authorized_from_session_state(monkeypatch):
    _set_token(monkeypatch, "s3cret")
    import streamlit as st

    monkeypatch.setattr(st, "session_state", {"admin_authorized": True})
    assert access.admin_authorized() is True
    assert access.require_admin() is True
