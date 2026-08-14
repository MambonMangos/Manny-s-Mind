# Assistant Manager Chat — Architecture Plan (Phase 1 Report)

Status: approved. Target: Gameweek 3 (2026-27). Phase 1 of the GW3 coding directive.

## Objective

A conversational interface to the Assistant Manager ("Manny's Mind") that lets the
user explore and challenge the platform's V3-based recommendations: transfer advice,
captaincy, budget/price questions, and "what-if" proposals. The chat is strictly
**advisory**. It never writes to the team, never changes the squad model, and never
modifies configuration. V3 remains the single source of truth for projections.

## Key findings from investigation

1. **No LLM/AI infrastructure exists** anywhere in the codebase. Providers, context
   assembly, memory, usage tracking, and UI must all be built new. The cleanest
   pattern to reuse is `services/league_intelligence/providers.py`, which uses a
   `Protocol`-based provider abstraction with injected implementations and graceful
   degradation; `services/api_client.py` supplies the retry/backoff/redaction
   conventions. API calls will use `requests` directly (bundled with `certifi`
   CA bundle); no new SDK dependencies are needed.

2. **Reuse the Assistant Manager engine as the context source, never re-derive
   projections.** `services/assistant_manager/engine.py` runs the full production
   pipeline (`engines/expected_projection_engine.py`, Feature Store, fixtures,
   team, budget) and returns an `AssistantReport` whose
   `production_pipeline_result` already contains the recommendations a user would
   want to ask about. The chat consumes that result for its context window instead
   of re-running engines or reading the DB directly.

3. **V3 is the prediction authority.** The chat prompt will instruct the model to
   treat V3's expected points as ground truth and to prefer "defer to V3" over
   inventing numbers. The full V3 detail behind the headline numbers
   (`xpts_per_90`, `expected_minutes`, `start_probability` in
   `ExpectedPlayerProjection.contributing_factors`) is only ever kept in-memory for
   context; it is not persisted to the DB.

4. **Security model — the biggest risk.** The app has no authentication; Streamlit
   session state is the only isolation boundary. Therefore:
   - `team_id` is resolved only through `utils/team_context.py`
     (`get_current_team_id()` / `require_team()`); the chat must never accept a
     team id from the user or the model.
   - Phase 2 performs **no** tool calls: no DB access, no SQL, no shell execution,
     and no direct league fetches from the LLM.
   - Nothing user-specific is ever written into the prompt that the model did not
     receive through `build_chat_context` (team squad, budget, fixtures, V3 report).
   - Secrets come from environment / `.streamlit/secrets.toml` via the
     `utils/access.py` pattern; never in YAML or git.
   - Conversation content is never logged. Usage logs are metadata only, e.g.
     `assistant_chat request team=... provider=... model=... tokens=...`.

5. **`team_id` semantics are ambiguous in this codebase.** In the team context it is
   the FPL entry id; the `teams` table stores club ids. The chat context builder
   must be explicit about which is which and never mix them.

## Architecture (Phase 2 onward)

```
pages/6_Assistant_Manager.py
        │  st.chat_input + ChatBubble (components/domain/chat.py)
        ▼
services/assistant_chat/engine.py  ── ChatEngine.respond(text)
        │  (SYSTEM_PROMPT, degrade/limit handling)
        ▼
        ├── context.py   build_chat_context(report) → ChatContext  (from run_assistant)
        ├── providers.py LLMProvider Protocol → OpenAI/Anthropic/Mock (+ graceful degradation)
        ├── memory.py    last_window()/add_turn() (session-scoped)
        ├── usage.py     UsageState (per-team, per-session request limit)
        ├── security.py  prompt hardening (moderation, sandbox escape checks)
        └── config.py    LLMSettings (config/llm/llm_v1.yaml + env overrides)
```

New/changed configuration is additive: `config/llm/llm_v1.yaml` and the `llm:`
category in `config/active.yaml`. No existing engine, feature-store, or DB behavior
changes, so all existing tests must keep passing (regression gate).

## Phases

- **Phase 1 — Investigation** (this report). Approved.
- **Phase 2 — Minimal chat** (implemented): providers (OpenAI/Anthropic/Mock),
  context builder, session memory, usage limits, engine, chat UI in the Assistant
  Manager page, tests, no tools, no persistence.
- **Phase 3 — Analytical tools** (implemented): deterministic tools in
  `services/assistant_chat/tools.py` — `compare_players`, `evaluate_user_proposal`
  (transfer xPts/price/hit math), `captaincy` (owned squad ranked by V3 xPts),
  and `budget_math` — computed from V3 report data only, dispatched by
  `run_tools` with zero provider calls.
- **Phase 4 — Security and QA**: prompt-injection hardening, PII audit, usage/cost
  review, full-suite regression, manual review in the live app.
- **Phase 5 — Release**: GW3 cutoff, `docs/assistant_chat.md` user doc, security
  review sign-off before release.

## Deliverables

- `services/assistant_chat/` package (config, providers, context, memory, usage,
  security, engine).
- `components/domain/chat.py` chat UI component.
- Chat section wired into `pages/6_Assistant_Manager.py`.
- `config/llm/llm_v1.yaml` + `config/active.yaml` registration.
- `tests/test_assistant_chat.py`.
- This plan (`docs/assistant_chat_plan.md`) and, at release,
  `docs/assistant_chat.md` user documentation.
