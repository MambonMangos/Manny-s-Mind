"""Conversational Assistant — a decision-support layer over the FPL platform.

The chat consumes the existing intelligence stack (V3 projections, Assistant
Manager report, League Intelligence) as structured context and lets the user
challenge, explore and reason with the numbers. It never re-derives
projections and never writes to the team or the prediction platform.

Public surface:
    from services.assistant_chat.engine import ChatEngine, ChatResponse
    from services.assistant_chat.providers import get_provider
    from services.assistant_chat.config import load_llm_settings
    from services.assistant_chat.context import build_chat_context, ChatContext
    from services.assistant_chat.memory import add_turn, get_conversation
    from services.assistant_chat.usage import UsageState
"""

from services.assistant_chat.config import LLMSettings, load_llm_settings
from services.assistant_chat.context import (
    ChatContext,
    build_chat_context,
    render_context,
)
from services.assistant_chat.engine import ChatEngine, ChatResponse
from services.assistant_chat.memory import (
    add_turn,
    clear_conversation,
    get_conversation,
    last_window,
)
from services.assistant_chat.providers import (
    AnthropicProvider,
    ChatMessage,
    ChatResult,
    LLMError,
    MockProvider,
    OpenAIProvider,
    get_provider,
)
from services.assistant_chat.tools import (
    ToolResult,
    compare_players,
    evaluate_user_proposal,
    run_tools,
)
from services.assistant_chat.usage import UsageSnapshot, UsageState

__all__ = [
    "AnthropicProvider",
    "ChatContext",
    "ChatEngine",
    "ChatMessage",
    "ChatResponse",
    "ChatResult",
    "LLMError",
    "LLMSettings",
    "MockProvider",
    "OpenAIProvider",
    "ToolResult",
    "UsageSnapshot",
    "UsageState",
    "add_turn",
    "build_chat_context",
    "clear_conversation",
    "compare_players",
    "evaluate_user_proposal",
    "get_conversation",
    "get_provider",
    "last_window",
    "load_llm_settings",
    "render_context",
    "run_tools",
]
