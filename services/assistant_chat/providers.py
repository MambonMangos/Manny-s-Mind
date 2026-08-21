"""LLM provider abstraction for the Conversational Assistant.

Follows the same pattern as :mod:`services.league_intelligence.providers`:
a ``typing.Protocol`` interface with concrete, injected implementations and
graceful degradation. No provider is hard-coded into the chat engine.

Providers
---------
- ``OpenAIProvider`` — OpenAI-compatible ``/chat/completions`` HTTP API.
- ``AnthropicProvider`` — Anthropic Messages API.
- ``MockProvider`` — deterministic local responder (offline/demo mode, tests).

Transport mirrors :mod:`services.api_client` conventions: ``certifi`` CA
bundle, bounded timeouts, exponential-backoff retries on transient failures,
and URL/payload redaction from logs. The API key is sent only in the
authorization header, never logged.

Contract: ``chat()`` returns a ``ChatResult`` or raises :class:`LLMError`.
Providers never write to the database, never touch FPL data, and never
execute anything derived from user input.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

import certifi
import requests

logger = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_BACKOFF_BASE = 1.0
_MAX_RETRY_AFTER = 30.0

_USER_AGENT = "MoneyballFPL-Chat/1.0"


class LLMError(Exception):
    """A provider call failed. Messages are deliberately generic and safe."""


@dataclass
class ChatMessage:
    """One message in the conversation sent to the provider."""
    role: str  # system | user | assistant
    content: str


@dataclass
class ChatResult:
    """Successful (or degraded) response from a provider."""
    content: str
    provider: str
    model: str
    finish_reason: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMProvider(Protocol):
    """A chat-completion provider. Implementations must be stateless."""
    name: str

    def chat(self, messages: list[ChatMessage]) -> ChatResult:
        """Send a conversation and return the assistant reply.

        Raises :class:`LLMError` on any failure so the engine can degrade
        gracefully.
        """
        ...


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------

def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: float,
    max_retries: int,
) -> dict:
    """POST JSON with bounded retries. Returns parsed JSON or raises LLMError."""
    last_error: Exception | None = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
                verify=certifi.where(),
            )
            if response.status_code in _RETRY_STATUSES and attempt < max_retries:
                delay = _BACKOFF_BASE * (2**attempt)
                try:
                    retry_after = float(response.headers.get("Retry-After", delay))
                    delay = min(max(retry_after, 0.1), _MAX_RETRY_AFTER)
                except ValueError:
                    pass
                logger.warning("LLM endpoint %s returned %d; retrying in %.1fs",
                               _safe_url(url), response.status_code, delay)
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                # Never surface response bodies to callers or logs.
                logger.warning("LLM endpoint %s returned %d", _safe_url(url), response.status_code)
                raise LLMError(f"Provider returned HTTP {response.status_code}")
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(_BACKOFF_BASE * (2**attempt))
                continue
        except requests.exceptions.JSONDecodeError as exc:
            last_error = exc
            break
    raise LLMError("Provider request failed") from last_error


def _safe_url(url: str) -> str:
    """Redact query strings / credentials from a URL before it hits logs."""
    return url.split("?", 1)[0].split("@", 1)[-1]


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------

class OpenAIProvider:
    """OpenAI-compatible chat completions provider (raw HTTP, no SDK)."""

    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        temperature: float = 0.4,
        max_tokens: int = 900,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        reasoning_effort: str = "",
    ) -> None:
        if not model:
            raise LLMError("LLM_MODEL is not configured for provider 'openai'")
        if not api_key:
            raise LLMError("LLM_API_KEY is not configured for provider 'openai'")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds
        self._retries = max_retries
        self._reasoning_effort = reasoning_effort.strip().lower()

    def chat(self, messages: list[ChatMessage]) -> ChatResult:
        payload: dict = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        # Reasoning models (e.g. Gemini 3.x via OpenAI-compatible endpoints)
        # spend thinking tokens from the max_tokens budget; a low effort keeps
        # the visible reply from being truncated. Omitted when unset so
        # providers that reject the parameter are unaffected.
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        data = _post_json(
            f"{self._base_url}/chat/completions",
            headers,
            payload,
            self._timeout,
            self._retries,
        )
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            usage = data.get("usage", {})
            return ChatResult(
                content=content,
                provider=self.name,
                model=self._model,
                finish_reason=str(choice.get("finish_reason", "")),
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("Provider returned an unexpected response") from exc


class AnthropicProvider:
    """Anthropic Messages API provider (raw HTTP, no SDK)."""

    name = "anthropic"

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        temperature: float = 0.4,
        max_tokens: int = 900,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not model:
            raise LLMError("LLM_MODEL is not configured for provider 'anthropic'")
        if not api_key:
            raise LLMError("LLM_API_KEY is not configured for provider 'anthropic'")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds
        self._retries = max_retries

    def chat(self, messages: list[ChatMessage]) -> ChatResult:
        system = "\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        payload: dict = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": turns,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        data = _post_json(
            f"{self._base_url}/v1/messages",
            headers,
            payload,
            self._timeout,
            self._retries,
        )
        try:
            blocks = data.get("content") or []
            content = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            usage = data.get("usage", {})
            return ChatResult(
                content=content,
                provider=self.name,
                model=self._model,
                finish_reason=str(data.get("stop_reason", "")),
                prompt_tokens=int(usage.get("input_tokens", 0)),
                completion_tokens=int(usage.get("output_tokens", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMError("Provider returned an unexpected response") from exc


class MockProvider:
    """Deterministic offline responder — demo mode, tests, no-API fallback.

    Never calls the network. Produces a short, clearly-labelled advisory reply
    so the conversational interface remains usable when no LLM is configured.
    """

    name = "mock"

    def __init__(self, model: str = "mock") -> None:
        self._model = model

    def chat(self, messages: list[ChatMessage]) -> ChatResult:
        user = messages[-1].content if messages else ""
        user = re.sub(r"^\s*<user-message>\s*|\s*</user-message>\s*$", "", user)
        return ChatResult(
            content=(
                "I'm running in offline mode because no LLM provider is configured, "
                "so this is a placeholder rather than a full analysis.\n\n"
                f"You asked: *{user[:200]}*\n\n"
                "Add `LLM_API_KEY` (and optionally `LLM_PROVIDER` / `LLM_MODEL`) to your "
                "environment or `.streamlit/secrets.toml` to enable live answers."
            ),
            provider=self.name,
            model=self._model,
            finish_reason="stop",
        )


def get_provider(settings) -> tuple[LLMProvider, bool, str]:
    """Resolve an :class:`LLMProvider` from settings.

    Returns ``(provider, offline, reason)``. ``offline=True`` means the returned
    provider is the deterministic mock — either because ``mock`` was requested or
    because the configured provider cannot be used (missing key/model). Never
    raises; misconfiguration degrades to offline mode.
    """
    if settings.provider == "mock":
        return MockProvider(model=settings.model or "mock"), True, "mock provider requested"
    try:
        if settings.provider == "anthropic":
            provider: LLMProvider = AnthropicProvider(
                model=settings.model,
                api_key=settings.api_key,
                base_url=settings.base_url or "https://api.anthropic.com",
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                timeout_seconds=settings.timeout_seconds,
                max_retries=settings.max_retries,
            )
        else:
            provider = OpenAIProvider(
                model=settings.model,
                api_key=settings.api_key,
                base_url=settings.base_url or "https://api.openai.com/v1",
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                timeout_seconds=settings.timeout_seconds,
                max_retries=settings.max_retries,
                reasoning_effort=getattr(settings, "reasoning_effort", ""),
            )
    except LLMError as exc:
        logger.warning("LLM provider unavailable; falling back to offline mode: %s", exc)
        return MockProvider(model=settings.model or "mock"), True, str(exc)
    return provider, False, ""
