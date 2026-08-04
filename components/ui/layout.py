"""Page layout primitives — headers, sections, dividers, grid wrappers.

Presenters return HTML; renderers wrap with Streamlit. Escaping happens here
so pages never escape manually.
"""

from __future__ import annotations

import streamlit as st

from components.ui.base import esc


def page_header_html(title: str, subtitle: str = "") -> str:
    """Return the HTML for a consistent page header."""
    subtitle_html = (
        f'<div class="page-subtitle fade-in fade-in-delay-1">{esc(subtitle)}</div>'
        if subtitle
        else ""
    )
    return f'<div class="page-title fade-in">{esc(title)}</div>{subtitle_html}'


def section_label_html(text: str) -> str:
    return f'<div class="section-label">{esc(text)}</div>'


def section_title_html(text: str) -> str:
    return f'<div class="section-title">{esc(text)}</div>'


def divider_html() -> str:
    return '<div class="divider"></div>'


def render_page_header(title: str, subtitle: str = "") -> None:
    st.markdown(page_header_html(title, subtitle), unsafe_allow_html=True)


def render_section_label(text: str) -> None:
    st.markdown(section_label_html(text), unsafe_allow_html=True)


def render_section_title(text: str) -> None:
    st.markdown(section_title_html(text), unsafe_allow_html=True)


def render_divider() -> None:
    st.markdown(divider_html(), unsafe_allow_html=True)


def render_hero_title(title: str) -> None:
    st.markdown(f'<div class="hero-title">{esc(title)}</div>', unsafe_allow_html=True)
