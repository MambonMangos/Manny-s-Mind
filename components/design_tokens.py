"""Design tokens — single source of truth for the Manny's FPL House design system.

Three tiers, each with a strict dependency direction:

    Tier 1  PALETTE      raw hex values. Nobody reads these except Tier 2.
    Tier 2  COLORS       semantic token names -> palette key. Components ask
                         "what meaning?" (``color("confidence_high")``), never
                         "which hex?". PALETTE hex values are swappable here.
    Tier 3  STATES       semantic state groups (evidence, confidence, risk)
                         built on Tier-2 names plus typography / spacing /
                         radii / breakpoints.

Components import from this module only. Backend / prediction logic does not
depend on this module.

This file is intentionally free of any Streamlit import so it can be unit
tested and, later, shared with a web frontend as CSS custom properties.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Tier 1 — palette (raw hex)
# ---------------------------------------------------------------------------

PALETTE: dict[str, str] = {
    # Surfaces
    "ink": "#09090b",          # app background
    "ink_soft": "#18181b",     # cards / plotly background
    "ink_soft_2": "#27272a",   # inputs / tertiary
    "elevated": "#1c1c24",     # elevated surface
    "zinc_600": "#3f3f46",     # borders
    # Text
    "slate_300": "#fafafa",    # primary text
    "slate_400": "#a1a1aa",    # secondary text
    "slate_500": "#71717a",    # muted text
    # Brand accents
    "indigo_500": "#6366f1",
    "indigo_400": "#818cf8",
    "violet_400": "#a78bfa",
    "cyan_500": "#06b6d4",
    "amber_500": "#f59e0b",
    "amber_400": "#fbbf24",
    "emerald_400": "#34d399",
    "rose_400": "#fb7185",
    "rose_500": "#f43f5e",
    "red_400": "#f87171",
    "pink_500": "#ec4899",
    "purple_500": "#8b5cf6",   # evidence / scientific confidence
}

# ---------------------------------------------------------------------------
# Tier 2 — semantic colors (meaning, not hex)
# ---------------------------------------------------------------------------

COLORS: dict[str, str] = {
    # Surfaces
    "background": "ink",
    "surface_background": "ink",
    "surface_card": "ink_soft",
    "surface_input": "ink_soft_2",
    "surface_elevated": "elevated",
    "border": "zinc_600",
    "border_subtle": "ink_soft_2",
    # Text
    "text_primary": "slate_300",
    "text_secondary": "slate_400",
    "text_muted": "slate_500",
    # Brand / trust
    "primary": "indigo_500",
    "trust_primary": "indigo_500",
    "accent_cyan": "cyan_500",
    "accent_amber": "amber_500",
    "evidence": "purple_500",
    # Quality / outcome
    "success": "emerald_400",
    "warning": "amber_400",
    "danger": "rose_400",
    # Confidence states
    "confidence_high": "emerald_400",
    "confidence_medium": "amber_400",
    "confidence_low": "rose_400",
    # Risk states
    "risk_low": "emerald_400",
    "risk_medium": "amber_400",
    "risk_high": "red_400",
    # Fixture difficulty states
    "fixture_easy": "emerald_400",
    "fixture_medium": "amber_400",
    "fixture_hard": "rose_400",
    # Evidence states
    "evidence_weak": "rose_400",
    "evidence_needs_data": "amber_400",
    "evidence_moderate": "amber_500",
    "evidence_strong": "emerald_400",
    "evidence_significant": "emerald_400",
    # Quality states (legacy semantic)
    "quality_good": "emerald_400",
    "quality_fair": "amber_400",
    "quality_poor": "red_400",
    # Market states
    "market_buy": "indigo_400",
    "market_sell": "violet_400",
    "market_riser": "emerald_400",
    "market_faller": "rose_400",
    # Position states
    "position_gkp": "amber_500",
    "position_def": "cyan_500",
    "position_mid": "indigo_500",
    "position_fwd": "rose_500",
}

# ---------------------------------------------------------------------------
# Tier 3 — state groups + primitives
# ---------------------------------------------------------------------------

EVIDENCE_LEVELS: dict[str, dict] = {
    "weak": {"label": "Weak", "icon": "🔴", "min_gameweeks": 1, "color_key": "evidence_weak"},
    "needs_more_data": {"label": "Needs More Data", "icon": "🟡", "min_gameweeks": 2, "color_key": "evidence_needs_data"},
    "moderate": {"label": "Moderate", "icon": "🟠", "min_gameweeks": 3, "color_key": "evidence_moderate"},
    "strong": {"label": "Strong", "icon": "🟢", "min_gameweeks": 5, "color_key": "evidence_strong"},
    "statistically_significant": {"label": "Statistically Significant", "icon": "✅", "min_gameweeks": 10, "color_key": "evidence_significant"},
}

CONFIDENCE_LEVELS: dict[str, dict] = {
    "high": {"label": "High", "min_pct": 70, "color_key": "confidence_high"},
    "medium": {"label": "Medium", "min_pct": 40, "color_key": "confidence_medium"},
    "low": {"label": "Low", "min_pct": 0, "color_key": "confidence_low"},
}

RISK_LEVELS: dict[str, dict] = {
    "low": {"label": "Low Risk", "color_key": "risk_low"},
    "medium": {"label": "Medium Risk", "color_key": "risk_medium"},
    "high": {"label": "High Risk", "color_key": "risk_high"},
}

FIXTURE_LEVELS: dict[str, dict] = {
    "easy": {"label": "Easy", "icon": "🟢", "color_key": "fixture_easy"},
    "medium": {"label": "Medium", "icon": "🟡", "color_key": "fixture_medium"},
    "hard": {"label": "Hard", "icon": "🔴", "color_key": "fixture_hard"},
}

FONT_FAMILY: str = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
FONT_MONO: str = "'JetBrains Mono', 'Fira Code', monospace"

TYPOGRAPHY: dict[str, dict] = {
    "hero_title": {"font_size": "3rem", "font_weight": 800, "letter_spacing": "-0.03em", "line_height": 1.1},
    "page_title": {"font_size": "1.75rem", "font_weight": 800, "letter_spacing": "-0.025em"},
    "page_subtitle": {"font_size": "0.9rem", "font_weight": 400},
    "section_label": {"font_size": "0.7rem", "font_weight": 600, "text_transform": "uppercase", "letter_spacing": "0.08em"},
    "section_title": {"font_size": "1.15rem", "font_weight": 700, "letter_spacing": "-0.01em"},
    "card_title": {"font_size": "1rem", "font_weight": 700},
    "body_text": {"font_size": "0.875rem", "font_weight": 400, "line_height": 1.6},
    "caption_text": {"font_size": "0.75rem", "font_weight": 400},
    "metric_label": {"font_size": "0.7rem", "font_weight": 600, "text_transform": "uppercase", "letter_spacing": "0.08em"},
    "metric_value": {"font_size": "1.75rem", "font_weight": 700},
}

SPACING: dict[str, str] = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.25rem",
    "xl": "1.5rem",
}

RADII: dict[str, str] = {
    "sm": "8px",
    "md": "12px",
}

BREAKPOINTS: dict[str, int] = {
    "sm": 768,
    "md": 1024,
}

# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    """Parse a 6-digit hex colour into an (r, g, b) tuple (or None)."""
    value = value.strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None


def color(token: str) -> str:
    """Resolve a semantic token (or palette) name to its hex value."""
    if token in COLORS:
        token = COLORS[token]
    if token not in PALETTE:
        raise KeyError(f"Unknown design token {token!r}")
    return PALETTE[token]


def rgba(token: str, alpha: float) -> str:
    """Return an ``r,g,b`` triple for use inside ``rgba(r,g,b,alpha)`` CSS."""
    rgb = hex_to_rgb(color(token))
    if rgb is None:
        return "0,0,0"
    return f"{rgb[0]},{rgb[1]},{rgb[2]}"


def confidence_level_for(pct: float) -> str:
    """Map a 0-100 percentage to high/medium/low using CONFIDENCE_LEVELS."""
    for level in ("high", "medium", "low"):
        if pct >= CONFIDENCE_LEVELS[level]["min_pct"]:
            return level
    return "low"


# ---------------------------------------------------------------------------
# CSS emission — legacy variable names kept identical so existing pages are
# unaffected by the token refactor. The regression test in
# tests/test_ui_components.py asserts this mapping matches the pre-refactor
# hardcoded values.
# ---------------------------------------------------------------------------

_CSS_VARIABLE_MAP: dict[str, str] = {
    "--bg-primary": color("background"),
    "--bg-secondary": color("surface_card"),
    "--bg-tertiary": color("surface_input"),
    "--bg-elevated": color("surface_elevated"),
    "--border": color("border"),
    "--border-subtle": color("border_subtle"),
    "--text-primary": color("text_primary"),
    "--text-secondary": color("text_secondary"),
    "--text-muted": color("text_muted"),
    "--color-market-buy": color("market_buy"),
    "--color-market-sell": color("market_sell"),
    "--color-market-riser": color("market_riser"),
    "--color-market-faller": color("market_faller"),
    "--color-risk-low": color("risk_low"),
    "--color-risk-med": color("risk_medium"),
    "--color-risk-high": color("risk_high"),
    "--color-quality-good": color("quality_good"),
    "--color-quality-fair": color("quality_fair"),
    "--color-quality-poor": color("quality_poor"),
    "--color-accent-indigo": color("trust_primary"),
    "--color-accent-cyan": color("accent_cyan"),
    "--color-accent-amber": color("accent_amber"),
    "--radius": RADII["md"],
    "--radius-sm": RADII["sm"],
}


def css_variable_map() -> dict[str, str]:
    """Return the legacy ``:root`` custom-property mapping (var -> hex)."""
    return dict(_CSS_VARIABLE_MAP)


def build_css_variables() -> str:
    """Emit the ``:root { ... }`` block of custom properties from tokens.

    Matches the legacy hardcoded block byte-for-byte (see the regression test
    in tests/test_ui_components.py).
    """
    lines = [":root {"]
    for k, v in _CSS_VARIABLE_MAP.items():
        if k == "--color-market-buy":
            lines.append("")
            lines.append("    /* Semantic colors */")
        lines.append(f"    {k}: {v};")
        if k == "--color-accent-amber":
            lines.append("")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Legacy flat color constants (single source of truth; re-exported by
# components/theme.py so existing imports keep working).
# ---------------------------------------------------------------------------

COLOR_MARKET_BUY = color("market_buy")
COLOR_MARKET_SELL = color("market_sell")
COLOR_MARKET_RISER = color("market_riser")
COLOR_MARKET_FALLER = color("market_faller")
COLOR_RISK_LOW = color("risk_low")
COLOR_RISK_MED = color("risk_medium")
COLOR_RISK_HIGH = color("risk_high")
COLOR_QUALITY_GOOD = color("quality_good")
COLOR_QUALITY_FAIR = color("quality_fair")
COLOR_QUALITY_POOR = color("quality_poor")
COLOR_ACCENT_INDIGO = color("trust_primary")
COLOR_ACCENT_CYAN = color("accent_cyan")
COLOR_ACCENT_AMBER = color("accent_amber")
