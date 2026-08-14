"""Conversational Assistant — usage metering and cost controls.

Tracks per-session request counts, token usage, latency and errors so runaway
usage is visible and bounded (directive §16). Counters live in session state;
each request also emits one structured log line with **no conversation
content** — only metadata (team, provider, model, tokens, latency, error).

Sensitive conversation content is deliberately never logged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_STATE_KEY = "assistant_chat_usage"


@dataclass
class UsageSnapshot:
    """Point-in-time usage for one team in the current session."""
    team_id: int
    requests: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_latency_ms: float = 0.0
    last_error: str = ""


class UsageState:
    """Per-team usage counters backed by session state."""

    def __init__(self, team_id: int) -> None:
        self.team_id = int(team_id)
        self._session_state = self._resolve_session_state()
        self._fallback: dict = {}

    @staticmethod
    def _resolve_session_state():
        """Return Streamlit session state, or None in bare (test) contexts.

        Gated on the script-run context so tests get an isolated local store
        instead of Streamlit's process-global bare-mode session state.
        """
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx

            if get_script_run_ctx() is None:
                return None
            from streamlit import session_state

            return session_state
        except Exception:  # noqa: BLE001 - non-Streamlit contexts
            return None

    def _store(self) -> dict:
        if self._session_state is not None:
            if _STATE_KEY not in self._session_state:
                self._session_state[_STATE_KEY] = {}
            return self._session_state[_STATE_KEY]
        return self._fallback

    def _bucket(self) -> dict:
        bucket = self._store().setdefault(self.team_id, {})
        bucket.setdefault("requests", 0)
        bucket.setdefault("errors", 0)
        bucket.setdefault("prompt_tokens", 0)
        bucket.setdefault("completion_tokens", 0)
        bucket.setdefault("total_latency_ms", 0.0)
        bucket.setdefault("last_error", "")
        return bucket

    def count_requests(self) -> int:
        return int(self._bucket().get("requests", 0))

    def over_limit(self, limit: int) -> bool:
        return self.count_requests() >= max(limit, 1)

    def total_tokens(self) -> int:
        b = self._bucket()
        return int(b.get("prompt_tokens", 0)) + int(b.get("completion_tokens", 0))

    def over_token_budget(self, budget: int) -> bool:
        return self.total_tokens() >= max(budget, 1)

    def snapshot(self) -> UsageSnapshot:
        b = self._bucket()
        return UsageSnapshot(
            team_id=self.team_id,
            requests=int(b.get("requests", 0)),
            errors=int(b.get("errors", 0)),
            prompt_tokens=int(b.get("prompt_tokens", 0)),
            completion_tokens=int(b.get("completion_tokens", 0)),
            total_latency_ms=float(b.get("total_latency_ms", 0.0)),
            last_error=str(b.get("last_error", "")),
        )

    def record(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
        error: str | None = None,
    ) -> UsageSnapshot:
        """Record one request and emit a content-free metrics log line."""
        b = self._bucket()
        b["requests"] = int(b.get("requests", 0)) + 1
        b["prompt_tokens"] = int(b.get("prompt_tokens", 0)) + max(int(prompt_tokens), 0)
        b["completion_tokens"] = int(b.get("completion_tokens", 0)) + max(
            int(completion_tokens), 0
        )
        b["total_latency_ms"] = float(b.get("total_latency_ms", 0.0)) + max(latency_ms, 0.0)
        if error:
            b["errors"] = int(b.get("errors", 0)) + 1
            b["last_error"] = error[:200]
        logger.info(
            "assistant_chat request team=%d provider=%s model=%s prompt_tokens=%d "
            "completion_tokens=%d latency_ms=%.0f error=%s",
            self.team_id,
            provider,
            model,
            b["prompt_tokens"],
            b["completion_tokens"],
            latency_ms,
            error or "none",
        )
        return self.snapshot()


class Timer:
    """Small monotonic stopwatch for latency metering."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self._start) * 1000.0
