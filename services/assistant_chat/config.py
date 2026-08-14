"""Conversational Assistant — configuration.

Merges the versioned ``config/llm`` YAML defaults with deployment overrides
(``LLM_PROVIDER`` / ``LLM_MODEL`` / ``LLM_BASE_URL``) and the API key from
Streamlit secrets or the environment. The API key is a secret: it is never
embedded in YAML and is never logged.

Resolution order (matches ``docs/configuration.md``):

    Environment Variables (.env / secrets) -> config/llm YAML -> safe defaults
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from utils.config import load_config
from utils.constants import LLM_BASE_URL, LLM_MODEL, LLM_PROVIDER

logger = logging.getLogger(__name__)

# Per-provider default endpoints. An empty ``base_url`` in settings means "use
# the provider default" — consumers resolve it with these.
DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}


@dataclass(frozen=True)
class LLMSettings:
    """Resolved, read-only settings for one chat session."""
    provider: str
    model: str
    base_url: str
    api_key: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    max_retries: int
    max_messages: int
    max_user_chars: int
    per_session_request_limit: int
    max_session_tokens: int
    top_projections: int
    top_differentials: int
    include_sources: bool


def get_api_key() -> str:
    """Return the LLM API key (Streamlit secrets, then environment) or ''."""
    try:
        from streamlit import secrets

        key = secrets.get("LLM_API_KEY")
        if key:
            return str(key)
    except Exception:  # noqa: BLE001 - fall back to the environment
        logger.debug("Streamlit secrets unavailable; reading LLM_API_KEY from env")
    return os.getenv("LLM_API_KEY", "")


def _int_value(value, name: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning("llm config value %s=%r is not an int; using %d", name, value, default)
        return default


def _float_value(value, name: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("llm config value %s=%r is not a number; using %s", name, value, default)
        return default


def load_llm_settings() -> LLMSettings:
    """Resolve LLM settings from config/llm YAML + environment overrides."""
    raw: dict = {}
    try:
        raw = load_config("llm")
    except FileNotFoundError:  # category missing is recoverable
        logger.warning("config category 'llm' not registered; using safe defaults")

    provider_cfg = raw.get("provider", {})
    conv_cfg = raw.get("conversation", {})
    context_cfg = raw.get("context", {})
    prov_cfg = raw.get("provenance", {})

    provider = os.getenv("LLM_PROVIDER") or LLM_PROVIDER or str(provider_cfg.get("name", "mock")).lower()
    if provider not in DEFAULT_BASE_URLS and provider != "mock":
        logger.warning("Unknown LLM provider %r; defaulting to 'mock'", provider)
        provider = "mock"

    model = os.getenv("LLM_MODEL") or LLM_MODEL or str(provider_cfg.get("model", ""))
    base_url = os.getenv("LLM_BASE_URL") or LLM_BASE_URL or str(provider_cfg.get("base_url", "")).strip()
    if not base_url and provider in DEFAULT_BASE_URLS:
        base_url = DEFAULT_BASE_URLS[provider]

    return LLMSettings(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=get_api_key(),
        temperature=_float_value(provider_cfg.get("temperature", 0.4), "temperature", 0.4),
        max_tokens=_int_value(provider_cfg.get("max_tokens", 900), "max_tokens", 900),
        timeout_seconds=_float_value(
            provider_cfg.get("timeout_seconds", 30), "timeout_seconds", 30.0
        ),
        max_retries=_int_value(provider_cfg.get("max_retries", 2), "max_retries", 2),
        max_messages=_int_value(conv_cfg.get("max_messages", 12), "max_messages", 12),
        max_user_chars=_int_value(conv_cfg.get("max_user_chars", 4000), "max_user_chars", 4000),
        per_session_request_limit=_int_value(
            conv_cfg.get("per_session_request_limit", 60), "per_session_request_limit", 60
        ),
        max_session_tokens=_int_value(
            conv_cfg.get("max_session_tokens", 100000), "max_session_tokens", 100000
        ),
        top_projections=_int_value(context_cfg.get("top_projections", 15), "top_projections", 15),
        top_differentials=_int_value(
            context_cfg.get("top_differentials", 5), "top_differentials", 5
        ),
        include_sources=bool(prov_cfg.get("include_sources", True)),
    )
