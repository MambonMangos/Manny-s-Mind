"""Tests for the design-system layer (tokens, ui primitives, domain cards).

Covers:
- CSS-variable regression: token-generated ``:root`` block must match the
  pre-refactor hardcoded values (a visual no-op guarantee).
- Legacy colour constants re-exported by theme.py must match the original
  values.
- HTML escaping at the presenter boundary (XSS-safe recommendations).
- Evidence/confidence mappings and the trust-section "render nothing when
  there is no data" rule.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from components import design_tokens as t
from components.domain import (
    CaptainCard,
    ChipCard,
    FixtureCard,
    PlayerRef,
    ProjectionCard,
    TransferCard,
    TrustSection,
)
from components.domain import evidence as domain_evidence
from components.domain.projection import (
    format_contributing_factors,
    projection_card_html,
)
from components.ui import badges

# Legacy hardcoded :root block from components/theme.py BEFORE the token
# refactor. Keep byte-identical (modulo whitespace) to the generated block.
LEGACY_ROOT_VARIABLES = {
    "--bg-primary": "#09090b",
    "--bg-secondary": "#18181b",
    "--bg-tertiary": "#27272a",
    "--bg-elevated": "#1c1c24",
    "--border": "#3f3f46",
    "--border-subtle": "#27272a",
    "--text-primary": "#fafafa",
    "--text-secondary": "#a1a1aa",
    "--text-muted": "#71717a",
    "--color-market-buy": "#818cf8",
    "--color-market-sell": "#a78bfa",
    "--color-market-riser": "#34d399",
    "--color-market-faller": "#fb7185",
    "--color-risk-low": "#34d399",
    "--color-risk-med": "#fbbf24",
    "--color-risk-high": "#f87171",
    "--color-quality-good": "#34d399",
    "--color-quality-fair": "#fbbf24",
    "--color-quality-poor": "#f87171",
    "--color-accent-indigo": "#6366f1",
    "--color-accent-cyan": "#06b6d4",
    "--color-accent-amber": "#f59e0b",
    "--radius": "12px",
    "--radius-sm": "8px",
}

LEGACY_COLOUR_CONSTANTS = {
    "COLOR_MARKET_BUY": "#818cf8",
    "COLOR_MARKET_SELL": "#a78bfa",
    "COLOR_MARKET_RISER": "#34d399",
    "COLOR_MARKET_FALLER": "#fb7185",
    "COLOR_RISK_LOW": "#34d399",
    "COLOR_RISK_MED": "#fbbf24",
    "COLOR_RISK_HIGH": "#f87171",
    "COLOR_QUALITY_GOOD": "#34d399",
    "COLOR_QUALITY_FAIR": "#fbbf24",
    "COLOR_QUALITY_POOR": "#f87171",
    "COLOR_ACCENT_INDIGO": "#6366f1",
    "COLOR_ACCENT_CYAN": "#06b6d4",
    "COLOR_ACCENT_AMBER": "#f59e0b",
}


def _parse_root_variables(css: str) -> dict[str, str]:
    """Extract ``--name: value`` pairs from a ``:root { ... }`` block."""
    match = re.search(r":root\s*\{(.*?)\}", css, re.DOTALL)
    assert match, "no :root block found"
    pairs: dict[str, str] = {}
    for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", match.group(1)):
        pairs[name] = value.strip()
    return pairs


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------


def test_css_variable_regression_matches_legacy_values():
    """Generated :root variables must equal the pre-refactor hardcoded CSS."""
    generated = _parse_root_variables(t.build_css_variables())
    assert generated == LEGACY_ROOT_VARIABLES


def test_css_variable_map_matches_legacy_values():
    assert t.css_variable_map() == LEGACY_ROOT_VARIABLES


def test_all_css_variables_are_valid_hex_or_length():
    for name, value in t.css_variable_map().items():
        assert value.startswith("#") or value.endswith("px"), (name, value)


def test_legacy_theme_constants_match_original():
    from components import theme

    for name, expected in LEGACY_COLOUR_CONSTANTS.items():
        assert getattr(theme, name) == expected, name


def test_color_resolves_palette_and_semantic():
    assert t.color("trust_primary") == "#6366f1"
    assert t.color("ink") == "#09090b"
    try:
        t.color("does_not_exist")
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unknown token must raise KeyError")


def test_rgba_helper_returns_comma_separated_rgb():
    assert t.rgba("trust_primary", 0.15) == "99,102,241"
    try:
        t.rgba("does_not_exist", 0.5)
    except KeyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unknown token must raise KeyError")


def test_confidence_level_mapping():
    assert t.confidence_level_for(80) == "high"
    assert t.confidence_level_for(50) == "medium"
    assert t.confidence_level_for(30) == "low"
    assert t.confidence_level_for(0) == "low"
    assert t.confidence_level_for(100) == "high"


# ---------------------------------------------------------------------------
# Escaping (presenter boundary)
# ---------------------------------------------------------------------------


def test_presenters_escape_player_names():
    evil = PlayerRef(1, "<script>alert(1)</script>", "BRE", "MID", 7.5)
    html = projection_card_html(
        ProjectionCard(
            player=evil, gameweek_id=8, projected_points=6.4,
            ci_80_low=2.0, ci_80_high=10.0, ci_95_low=1.0, ci_95_high=12.0,
            confidence_pct=78, data_quality="high",
        )
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_badges_escape_position():
    html = badges.badge_position("<FWD>")
    assert "&lt;FWD&gt;" in html
    assert "<FWD>" not in html


def test_badges_escape_arbitrary_level():
    html = badges.badge_evidence("<strong>")
    assert "&lt;strong&gt;" in html


def test_ui_layout_escapes_section_titles():
    from components.ui import section_label_html, section_title_html

    assert "&lt;title&gt;" in section_title_html("<title>hi</title>")
    assert "&lt;label&gt;" in section_label_html("<label>hi</label>")


# ---------------------------------------------------------------------------
# Evidence / confidence state groups
# ---------------------------------------------------------------------------


def test_evidence_levels_cover_learning_service_keys():
    from services.learning_service import EVIDENCE_THRESHOLDS

    assert set(EVIDENCE_THRESHOLDS) == set(t.EVIDENCE_LEVELS)


def test_evidence_from_gameweeks_respects_thresholds():
    assert domain_evidence.evidence_from_gameweeks(1).level == "weak"
    assert domain_evidence.evidence_from_gameweeks(2).level == "needs_more_data"
    assert domain_evidence.evidence_from_gameweeks(4).level == "moderate"
    assert domain_evidence.evidence_from_gameweeks(6, consistency_score=0.8).level == "strong"
    assert domain_evidence.evidence_from_gameweeks(12).level == "statistically_significant"


def test_trust_section_renders_nothing_when_empty():
    assert domain_evidence.trust_section_html(TrustSection()) == ""
    assert not domain_evidence.has_any_trust_data(TrustSection())


def test_trust_section_renders_badges_and_reasons():
    ts = TrustSection(
        evidence=domain_evidence.evidence_from_gameweeks(6, consistency_score=0.8),
        confidence_pct=78,
        data_quality="high",
        model_agreement=0.85,
        historical_accuracy=0.72,
        reasoning=["Consistent 5+ GW pattern"],
    )
    html = domain_evidence.trust_section_html(ts)
    assert "Evidence:" in html
    assert "High 78%" in html
    assert "High 85%" in html  # model agreement
    assert "High 72%" in html  # historical accuracy
    assert "Consistent 5+ GW pattern" in html


# ---------------------------------------------------------------------------
# Domain cards
# ---------------------------------------------------------------------------


def test_projection_card_includes_confidence_interval():
    card = ProjectionCard(
        player=PlayerRef(1, "Mbeumo", "BRE", "MID", 7.5), gameweek_id=8,
        projected_points=6.4, ci_80_low=2.1, ci_80_high=10.7,
        ci_95_low=0.8, ci_95_high=12.0,
        confidence_pct=78, data_quality="high",
    )
    html = projection_card_html(card)
    assert "6.4" in html
    assert "2.1–10.7" in html
    assert "0.8–12.0" in html


def test_format_contributing_factors_humanises_labels():
    rows = format_contributing_factors({
        "xpts_per_90": 5.8, "expected_minutes": 82.5, "start_probability": 0.87,
        "rotation_risk": "low", "data_quality_rate": "high",
    })
    assert "xPts/90: 5.8" in rows
    assert "Expected minutes: 82.5" in rows
    assert "Start probability: 0.87" in rows


def test_transfer_card_presenter_escapes_and_shows_gain():
    out = PlayerRef(1, "<Ollie>", "BRE", "MID", 7.5)
    in_ = PlayerRef(2, "Saka", "ARS", "MID", 9.0)
    card = TransferCard(out=out, in_=in_, price_difference=1.5,
                        expected_points_gained=1.8, risk_level="low",
                        confidence_pct=81, reasoning="Fixture swing")
    html = __import__("components.domain", fromlist=["transfer_card_html"]).transfer_card_html(card)
    assert "&lt;Ollie&gt;" in html
    assert "<Ollie>" not in html
    assert "+1.8" in html


def test_fixture_level_mapping():
    from components.domain import fixture_level

    assert fixture_level(1) == "easy"
    assert fixture_level(2) == "easy"
    assert fixture_level(3) == "medium"
    assert fixture_level(4) == "hard"
    assert fixture_level(5) == "hard"


def test_chip_and_fixture_cards_render():
    chip_html = __import__("components.domain", fromlist=["chip_card_html"]).chip_card_html(
        ChipCard("wildcard", "Wildcard", True, 82, best_gameweek=9, projected_gain=12.5,
                 reasoning="Two DGWs ahead")
    )
    assert "Wildcard" in chip_html
    assert "GW9" in chip_html

    fixture_html = __import__("components.domain", fromlist=["fixture_card_html"]).fixture_card_html(
        FixtureCard(8, "Arsenal", "ARS", home=False, difficulty=4, difficulty_label="Hard")
    )
    assert "Arsenal" in fixture_html
    assert "Hard" in fixture_html


def test_captain_card_presenter_escapes():
    html = __import__("components.domain", fromlist=["captain_card_html"]).captain_card_html(
        CaptainCard(PlayerRef(1, "<script>x</script>", "BRE", "FWD", 7.5), 8, 6.4,
                    rationale="Best fixture", next_opponent="Southampton",
                    next_opponent_difficulty=1)
    )
    assert "&lt;script&gt;" in html
