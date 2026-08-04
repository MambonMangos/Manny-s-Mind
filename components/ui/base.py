"""Low-level HTML helpers shared by presenters.

Everything here returns strings; nothing touches Streamlit. The presenter
boundary is the one place where all dynamic values are escaped — a component
must never pass raw, unescaped user/FPL data into ``unsafe_allow_html=True``.
"""

from __future__ import annotations

from html import escape


def esc(value) -> str:
    """HTML-escape a value for safe interpolation into markup."""
    return escape(str(value), quote=True)


def class_attr(*parts: str | None) -> str:
    """Join non-empty class names with a single space."""
    return " ".join(p for p in parts if p)


def span(content: str, classes: str = "", style: str = "") -> str:
    """Build an inline ``<span>`` element with escaped content."""
    cls = f' class="{classes}"' if classes else ""
    stl = f' style="{style}"' if style else ""
    return f"<span{cls}{stl}>{content}</span>"


def div(content: str, classes: str = "") -> str:
    """Build a block ``<div>`` element."""
    cls = f' class="{classes}"' if classes else ""
    return f"<div{cls}>{content}</div>"


def as_label(value: str, prefix: str = "", suffix: str = "") -> str:
    """Escape a value and wrap it so it reads safely in a label slot."""
    return f"{prefix}{esc(value)}{suffix}"
