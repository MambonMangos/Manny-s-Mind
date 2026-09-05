"""Regression tests for team transfer fetching.

The FPL transfers endpoint names the swapped players ``element_in`` /
``element_out`` (with matching ``element_*_cost`` fields), while the
application's internal ``Transfer`` contract uses ``player_in`` /
``player_out``. These tests pin the API-boundary normalisation in
``services.team_service.fetch_transfers`` so that:

- current payloads parse without KeyError,
- values map onto the internal ``Transfer`` model,
- legacy ``player_*`` payloads keep working,
- a malformed record is skipped (and logged), not fatal.
"""

from __future__ import annotations

import logging

from services.team_service import Transfer, fetch_transfers

CURRENT_PAYLOAD = [
    {
        "element_in": 98,
        "element_in_cost": 50,
        "element_out": 159,
        "element_out_cost": 55,
        "entry": 129991,
        "event": 2,
        "time": "2026-08-26T20:56:45.402027Z",
    },
]

EXPECTED_TRANSFER = Transfer(
    player_in=98,
    player_out=159,
    player_in_cost=50,
    player_out_cost=55,
    event=2,
    time="2026-08-26T20:56:45.402027Z",
)


def _patch_fpl_get(monkeypatch, payload):
    monkeypatch.setattr(
        "services.team_service.fpl_get", lambda team_id: payload
    )


# ---------------------------------------------------------------------------
# Test 1 — current FPL API payload
# ---------------------------------------------------------------------------


def test_fetch_transfers_parses_current_api_payload(monkeypatch):
    _patch_fpl_get(monkeypatch, CURRENT_PAYLOAD)

    transfers = fetch_transfers(129991)

    assert len(transfers) == 1
    assert transfers[0].player_in == 98
    assert transfers[0].player_out == 159
    assert transfers[0].player_in_cost == 50
    assert transfers[0].player_out_cost == 55
    assert transfers[0].event == 2
    assert transfers[0].time == "2026-08-26T20:56:45.402027Z"


# ---------------------------------------------------------------------------
# Test 2 — application output contract
# ---------------------------------------------------------------------------


def test_fetch_transfers_matches_transfer_contract(monkeypatch):
    _patch_fpl_get(monkeypatch, CURRENT_PAYLOAD)

    transfers = fetch_transfers(129991)

    assert transfers == [EXPECTED_TRANSFER]
    assert all(isinstance(t, Transfer) for t in transfers)


# ---------------------------------------------------------------------------
# Test 3 — legacy payload (player_in / player_out)
# ---------------------------------------------------------------------------


def test_fetch_transfers_accepts_legacy_player_payload(monkeypatch):
    _patch_fpl_get(
        monkeypatch,
        [
            {
                "player_in": 98,
                "player_in_cost": 50,
                "player_out": 159,
                "player_out_cost": 55,
                "event": 2,
                "time": "2026-08-26T20:56:45.402027Z",
            }
        ],
    )

    assert fetch_transfers(129991) == [EXPECTED_TRANSFER]


# ---------------------------------------------------------------------------
# Test 4 — malformed record
# ---------------------------------------------------------------------------


def test_fetch_transfers_skips_malformed_record(monkeypatch, caplog):
    _patch_fpl_get(
        monkeypatch,
        [
            {
                "element_in_cost": 50,
                "event": 2,
                "time": "2026-08-26T20:56:45.402027Z",
            },
            {
                "element_in": 98,
                "element_in_cost": 50,
                "element_out": 159,
                "element_out_cost": 55,
                "event": 3,
                "time": "2026-08-28T20:00:00.000000Z",
            },
        ],
    )

    with caplog.at_level(logging.WARNING, logger="services.team_service"):
        transfers = fetch_transfers(129991)

    # The malformed record is dropped; the valid record still parses.
    assert len(transfers) == 1
    assert transfers[0].event == 3
    assert "Skipping malformed transfer record at index 0" in caplog.text