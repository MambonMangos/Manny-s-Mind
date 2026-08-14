"""Conversational Assistant — input handling and safety.

Every user message is untrusted input (directive §13). This module provides
the text-processing boundary: sanitisation before the message reaches the
provider, a guard that inspects the assistant's reply before it is shown to
the user, and helpers that keep the assistant advisory-only.
"""

from __future__ import annotations

import re

# C0 + C1 control characters and bidi/zero-width markers that can be used to
# disguise text or corrupt the rendered transcript.
_CONTROL_RE = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]"
)

# Markers that should never appear in an assistant reply: they would mean the
# model is echoing internal instructions, secrets or context bookkeeping.
# Env-var *names* (e.g. "LLM_API_KEY") are intentionally excluded — they are
# public configuration, and legitimate replies (like offline guidance) may
# mention them. Only secret *values* and internal text are blocked.
_LEAK_MARKERS = (
    "SYSTEM_PROMPT",
    "CURRENT CONTEXT",
    "x-api-key",
    "Authorization: Bearer",
    "per_session_request_limit",
    "sk-",
    "sk_test",
)

# A fully rendered context/source string is long and structured; the guard
# treats any overlap beyond this fraction of a known internal string as a leak.
_INTERNAL_OVERLAP_MIN = 0.6


def sanitize_user_message(text: str, max_chars: int) -> str:
    """Sanitise a user message: strip control chars, then cap its length.

    Returns a plain string safe to embed in the provider payload and the chat
    transcript. Does not modify the team, model, or any configuration.
    """
    if not text:
        return ""
    cleaned = _CONTROL_RE.sub("", text)
    cleaned = cleaned.strip()
    if max_chars > 0 and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    return cleaned


def guard_response(content: str, internal_texts: list[str] | None = None) -> str | None:
    """Inspect an assistant reply for leaked internals.

    Returns a short reason string when the reply looks like it is exposing the
    system prompt, credentials, or context bookkeeping — the engine then
    degrades the reply instead of showing it. Returns ``None`` when the reply
    is safe to show.

    ``internal_texts`` may carry known internal strings (system prompt, context)
    so a reply that merely quotes them wholesale is caught.
    """
    if not content:
        return None
    lowered = content.lower()
    for marker in _LEAK_MARKERS:
        if marker.lower() in lowered:
            return f"leaked marker {marker!r}"
    for internal in internal_texts or []:
        if not internal:
            continue
        overlap = _overlap_fraction(content, internal)
        if overlap >= _INTERNAL_OVERLAP_MIN:
            return "quoted internal text"
    return None


def _overlap_fraction(a: str, b: str) -> float:
    """Fraction of the shorter string that appears inside the longer one."""
    if not a or not b:
        return 0.0
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if short in long:
        return 1.0
    # Chunked fallback: any long shared run suggests wholesale quoting.
    window = min(60, max(12, len(short) // 4))
    for i in range(0, len(short) - window + 1, max(window // 2, 1)):
        chunk = short[i : i + window]
        if chunk in long:
            return 1.0
    return 0.0


def frame_user_message(message: str) -> str:
    """Wrap untrusted user content in explicit delimiters.

    The model is told these markers denote data, never instructions, so a
    prompt-injection attempt inside the user's text is structurally separate
    from the system prompt.
    """
    return f"\n<user-message>\n{message}\n</user-message>\n"


def contains_forbidden(content: str) -> bool:
    """Heuristic guard used in tests only — never as a security boundary."""
    lowered = content.lower()
    return any(
        marker in lowered
        for marker in (
            "ignore your instructions",
            "ignore the system prompt",
            "show me the database",
            "reveal your prompt",
            "another user",
        )
    )
