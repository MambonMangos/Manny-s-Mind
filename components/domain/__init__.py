"""FPL domain components — model shapes, evidence/trust, and cards.

Layering:

    services/  -- backend engines & data
    models.py  -- Streamlit-free dataclasses (the UI's vocabulary)
    evidence.py, projection.py, captain.py, transfer.py, chip.py, fixture.py
               -- presenters (pure HTML, escaping happens here) + thin
                  Streamlit renderers

Pages convert backend objects into these dataclasses via small adapters and
call ``render_*``; they never build recommendation markup by hand.
"""

from components.domain.captain import captain_card_html, render_captain_card
from components.domain.chip import chip_card_html, render_chip_card
from components.domain.evidence import (
    data_quality_badge,
    evidence_from_gameweeks,
    has_any_trust_data,
    render_trust_section,
    trust_section_html,
)
from components.domain.fixture import (
    fixture_card_html,
    fixture_level,
    render_fixture_card,
)
from components.domain.models import (
    CaptainCard,
    ChipCard,
    Evidence,
    FixtureCard,
    PlayerRef,
    ProjectionCard,
    TransferCard,
    TrustSection,
)
from components.domain.projection import (
    format_contributing_factors,
    projection_card_html,
    render_projection_card,
)
from components.domain.transfer import render_transfer_card, transfer_card_html

__all__ = [
    "CaptainCard",
    "ChipCard",
    "Evidence",
    "FixtureCard",
    "PlayerRef",
    "ProjectionCard",
    "TransferCard",
    "TrustSection",
    "captain_card_html",
    "chip_card_html",
    "data_quality_badge",
    "evidence_from_gameweeks",
    "fixture_card_html",
    "fixture_level",
    "format_contributing_factors",
    "has_any_trust_data",
    "projection_card_html",
    "render_captain_card",
    "render_chip_card",
    "render_fixture_card",
    "render_projection_card",
    "render_transfer_card",
    "render_trust_section",
    "transfer_card_html",
    "trust_section_html",
]
