"""Chat UI — renders the conversational transcript.

Streamlit-native rendering (``st.chat_message`` + ``st.markdown``). The
``unsafe_allow_html`` flag is never used here, so LLM output and player names
are rendered as inert markdown. Each assistant bubble gets a collapsible
"Data sources" block that lists the exact V3/FPL values behind the reply.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from components.ui.base import esc

STARTER_PROMPTS: list[str] = [
    "Review my team",
    "Who should I captain this week?",
    "Compare Saka and Palmer",
    "Why does the model disagree with me?",
]


@dataclass
class ChatBubble:
    """One rendered turn in the transcript."""
    role: str  # user | assistant
    content: str
    sources: list[str] = field(default_factory=list)
    degraded: bool = False


def render_chat_history(bubbles: list[ChatBubble]) -> None:
    """Render the full transcript with per-bubble data sources."""
    if not bubbles:
        st.caption(
            "Ask about your team below — transfers, captaincy, fixtures, or a "
            "what-if scenario. The assistant reasons with your V3 projections."
        )
        return

    for bubble in bubbles:
        with st.chat_message(bubble.role):
            if bubble.degraded:
                st.caption("offline mode")
            st.markdown(bubble.content)
            if bubble.sources:
                with st.expander("Data sources (V3 / FPL / League)"):
                    for source in bubble.sources:
                        st.markdown(f"- {esc(source)}")


def render_starter_prompts(on_pick) -> None:
    """Render clickable starter prompts; call ``on_pick(text)`` on selection."""
    cols = st.columns(len(STARTER_PROMPTS))
    for col, prompt in zip(cols, STARTER_PROMPTS):
        with col:
            if st.button(prompt, key=f"chat_starter_{prompt[:16]}", use_container_width=True):
                on_pick(prompt)
