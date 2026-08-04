"""UI primitives — badges, cards, metrics, states, layout.

Public surface of :mod:`components.ui`. Pages and domain components import
from here; the submodules are implementation detail.
"""

from components.ui.badges import (
    badge_confidence,
    badge_delta,
    badge_evidence,
    badge_fixture,
    badge_model_agreement,
    badge_position,
    badge_risk,
    render_badges,
    render_confidence_badge,
    render_evidence_badge,
    render_fixture_badge,
    render_html,
    render_position_badge,
    render_risk_badge,
)
from components.ui.cards import (
    card_header_html,
    card_html,
    metric_card_html,
    render_card,
    render_metric_card,
)
from components.ui.layout import (
    divider_html,
    page_header_html,
    render_divider,
    render_hero_title,
    render_page_header,
    render_section_label,
    render_section_title,
    section_label_html,
    section_title_html,
)
from components.ui.metrics import (
    grid_class,
    metric_grid_html,
    render_metric_grid,
    render_metric_row,
)
from components.ui.states import (
    empty_state_html,
    render_alert,
    render_empty_state,
    render_error,
    render_info,
    render_success,
    render_warning,
)

__all__ = [
    "badge_confidence",
    "badge_delta",
    "badge_evidence",
    "badge_fixture",
    "badge_model_agreement",
    "badge_position",
    "badge_risk",
    "card_header_html",
    "card_html",
    "divider_html",
    "empty_state_html",
    "grid_class",
    "metric_card_html",
    "metric_grid_html",
    "page_header_html",
    "render_alert",
    "render_badges",
    "render_card",
    "render_confidence_badge",
    "render_divider",
    "render_empty_state",
    "render_error",
    "render_evidence_badge",
    "render_fixture_badge",
    "render_hero_title",
    "render_html",
    "render_info",
    "render_metric_card",
    "render_metric_grid",
    "render_metric_row",
    "render_page_header",
    "render_position_badge",
    "render_risk_badge",
    "render_section_label",
    "render_section_title",
    "render_success",
    "render_warning",
    "section_label_html",
    "section_title_html",
]
