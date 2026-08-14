"""Conversational Assistant — session conversation memory.

Session-level conversational memory (directive §9): the assistant remembers
what was said during the current conversation so follow-ups like "keep him and
sell Palmer instead" resolve correctly. Conversations are keyed by ``team_id``
so switching teams in one session can never surface another team's chat.

Storage is Streamlit session state (per-session, never persisted). Tests and
non-Streamlit contexts fall back to an in-process dict.

No permanent user memory is stored — long-term preferences are a future,
separate project (directive §9).
"""

from __future__ import annotations

from typing import Any

_KEY = "assistant_chat_conversations"

_FALLBACK: dict[int, list[dict]] = {}


def _session_state() -> dict | None:
    """Return Streamlit session state, or None outside a running app.

    Streamlit's ``session_state`` is importable even in bare test mode, where it
    is a process-global stand-in. We gate on the script-run context so tests get
    a clean local store instead of leaking state across tests.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx() is None:
            return None
        from streamlit import session_state

        return session_state
    except Exception:  # noqa: BLE001 - non-Streamlit contexts use a local store
        return None


def _state() -> dict:
    """Return the store backing conversations."""
    session_state = _session_state()
    if session_state is None:
        return _FALLBACK
    if _KEY not in session_state:
        session_state[_KEY] = {}
    return session_state[_KEY]


def get_conversation(team_id: int) -> list[dict]:
    """Return the current conversation (mutable list of message dicts)."""
    convos = _state()
    return convos.setdefault(team_id, [])


def add_turn(
    team_id: int,
    role: str,
    content: str,
    *,
    sources: list[str] | None = None,
    degraded: bool = False,
) -> None:
    """Append one turn to the team's conversation."""
    if role not in {"user", "assistant"}:
        raise ValueError(f"Unsupported chat role: {role!r}")
    message: dict[str, Any] = {"role": role, "content": content}
    if sources:
        message["sources"] = list(sources)
    if degraded:
        message["degraded"] = True
    get_conversation(team_id).append(message)


def clear_conversation(team_id: int) -> None:
    """Reset the team's conversation."""
    convos = _state()
    convos[team_id] = []
    convos.pop(team_id, None)


def message_count(team_id: int) -> int:
    """Number of stored turns for the team."""
    return len(get_conversation(team_id))


def last_window(team_id: int, max_messages: int) -> list[dict]:
    """Return the last ``max_messages`` turns for the model prompt.

    The system prompt is assembled by the engine, so only user/assistant turns
    are returned here. ``sources``/``degraded`` metadata is stripped — the LLM
    must never see provenance bookkeeping as content.
    """
    messages = get_conversation(team_id)
    trimmed = messages[-max_messages:] if max_messages > 0 else []
    return [
        {"role": m["role"], "content": m["content"]}
        for m in trimmed
        if m["role"] in {"user", "assistant"}
    ]
