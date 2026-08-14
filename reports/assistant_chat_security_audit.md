# Assistant Chat — Security & QA Audit (Phase 4)

Date: 2026-08-14. Scope: the Conversational Assistant added in Phases 1–3
(`services/assistant_chat/`, `components/domain/chat.py`, the chat section of
`pages/6_Assistant_Manager.py`). Reviewed: prompt-injection hardening, response
guarding, PII/secret handling, logging, and cost controls.

Status: **PASS** — no blocking findings. Full suite green (299 passed),
`ruff check .` clean.

---

## 1. Prompt-injection hardening

**User input is treated as data, structurally.** `security.sanitize_user_message`
strips control/bidi/zero-width characters and caps length
(`max_user_chars`). The engine then wraps every user turn in explicit
`<user-message>…</user-message>` delimiters before it reaches the provider
(`engine._build_messages`), and the system prompt instructs the model that
everything inside those tags is untrusted data, never instructions.

**Assistant replies are guarded.** `security.guard_response` inspects every
provider reply for leaked internal markers (`sk-`, `Authorization: Bearer`,
`x-api-key`, `SYSTEM_PROMPT`, `CURRENT CONTEXT`, `per_session_request_limit`)
and for wholesale quoting of the system prompt/context. A blocked reply is
replaced with the degraded message and recorded as `guard_blocked`; the leaked
content is never shown to the user.

**Advisory-only boundary.** The engine has no write path to the team, the
database, models, or configuration. Tools in Phase 3 are pure, deterministic
computations over the in-memory context — no execution, no side effects. No
tool, SQL, or shell command is ever derived from user input.

## 2. PII and secrets

- **API key**: read only from Streamlit secrets or the environment
  (`config.get_api_key`), sent only in the provider authorization header,
  never logged, never embedded in YAML or git.
- **Context content**: the prompt carries only the current team's own data
  (squad, bank, fixtures, V3 projections) plus league intelligence — no other
  user's data and no internal configuration. The context block is never
  persisted.
- **Logging**: audited every `logger.*` site in the package. All are metadata
  only — team id, status codes, redacted URLs, generic `LLMError` messages,
  and guard marker *labels*. Conversation content is never logged
  (`usage.record` emits `team/provider/model/tokens/latency/error` only).
- **Rendering**: `components/domain/chat.py` uses `st.chat_message` +
  `st.markdown` (no `unsafe_allow_html`) and escapes source lines with
  `esc()`.

## 3. Cost controls

- **Per-session request limit** (`per_session_request_limit`, default 60):
  enforced in the engine before any paid call.
- **Session token budget** (`max_session_tokens`, default 100,000): cumulative
  prompt+completion tokens tracked by `UsageState.over_token_budget`, enforced
  before each paid call.
- **Tools are free**: matched Phase 3 tools short-circuit to a deterministic
  answer (`provider="tool"`) and never consume the request/token budget.
- **Graceful degradation**: provider errors, timeouts, limit exhaustion and
  guard blocks all return friendly degraded messages without surfacing stack
  traces, credentials, or internal architecture.

## 4. Regression evidence

- `tests/test_assistant_chat.py` — 47 tests covering config, providers,
  context, memory, engine, tools, response guard, framing, and usage limits.
- Full suite: **299 passed** (baseline 252 + 47 chat tests), `ruff check .`
  clean, no production behavior changed.
- One observed transient failure in `test_v2_pipeline.py` (untouched file,
  borderline numpy-RNG assertion) — unrelated to this work; passes
  consistently in isolation and in repeated full runs.

## 5. Remaining items before release (Phase 5)

- Manual smoke test of the live chat UI in the running app (browser check of
  the transcript, sources expander, starter prompts).
- Confirm the operator sets `LLM_API_KEY` in Streamlit secrets / env before
  enabling a live provider; the app degrades to offline mock otherwise.
- Write `docs/assistant_chat.md` (user documentation) as the Phase 5 deliverable.
