# Conversational Assistant — User Documentation

**Release target:** Gameweek 3, 2026-27.
**Status:** released. Advisory only — never modifies your team.

The **Conversational Assistant** ("Assistant Chat") is a decision-support
chatbot inside the Assistant Manager page. It reasons with your team and the
platform's V3 expected points (xPts) projections, so you can explore and
challenge the numbers before you act.

## 1. What it does

- Answers questions about **your team**: squad, bank, free transfers, fixtures.
- Explains V3 **xPts projections** with provenance — every number is traceable.
- Runs **deterministic tools** for well-scoped questions (no AI guesswork):
  - **Compare players** — side-by-side table on any available field
    (xPts, xPts/90, expected minutes, start probability, price, form, fixtures).
  - **Evaluate a transfer** — exact xPts change, hit cost (-4 per extra
    transfer), net expected gain and whether it is affordable against your bank.
  - **Captaincy** — your top owned picks ranked by V3 xPts, with start risk.
  - **Budget math** — what a player costs and the most expensive player you
    could buy outright.
- Uses the LLM for open-ended conversation (transfers, chips, what-ifs,
  reasoning about the model).

Example prompts:

| You ask | What you get |
|---------|--------------|
| "Who should I captain this week?" | Top owned captain picks by V3 xPts |
| "Compare Saka and Palmer" | Head-to-head table |
| "Sell Palmer for Saka, takes a -4" | Net expected gain after the hit |
| "Can I afford Haaland?" | Cost, bank, and max affordable buy |
| "Why is my team weak?" | LLM reasoning grounded in V3 numbers |

## 2. What it never does

- **Never makes changes** — it cannot transfer, change your captain or chips,
  or modify any configuration.
- **Never re-derives predictions** — it consumes the V3 projections the
  platform already produced.
- **Never touches other users' data** — it only sees your team and league
  context.
- **Never runs code or SQL** from your messages, and has no direct database
  access.
- **Never logs your conversation** — usage is tracked as metadata only
  (requests, tokens, latency).

## 3. Data sources and provenance

Every assistant reply can be expanded via **"Data sources (V3 / FPL / League)"**
showing the exact values used. Provenance labels:

- **V3 projects** — model output (xPts, expected minutes, start probability).
- **FPL data shows** — raw FPL data (prices, fixtures, ownership, news).
- **Based on your assumption** — information you provided.
- **That suggests** — the assistant's own inference, never presented as V3.

## 4. Security and limits

- Per-session **request limit** and a cumulative **token budget** are enforced;
  when exhausted the chat explains that limits were reached rather than
  changing anything.
- The assistant degrades gracefully to offline mode (deterministic tool
  answers still work) when no LLM provider is configured or reachable.
- Input is sanitised and every user message is treated as untrusted data;
  assistant replies are screened before display.

## 5. Running live vs offline

- **Live answers** require `LLM_API_KEY` (and optionally `LLM_PROVIDER` /
  `LLM_MODEL`) in Streamlit secrets or the environment. Default provider is
  OpenAI (`gpt-4o-mini`); Anthropic is supported.
- **Offline/demo mode** is the default when no key is set: free-form answers
  become a clearly-labelled placeholder, but the analytical tools still answer
  exactly.
- Configuration lives in `config/llm/llm_v1.yaml` (versioned, additive) with
  deployment overrides via environment variables. The API key is never stored
  in YAML or git.

## 6. Where the code lives

- `services/assistant_chat/` — engine, providers, context, memory, tools,
  usage, security, config.
- `components/domain/chat.py` — transcript / starter-prompt rendering.
- `pages/6_Assistant_Manager.py` — the chat section.
- `tests/test_assistant_chat.py` — unit tests.
- `docs/assistant_chat_plan.md` — architecture plan (Phase 1 report).
- `reports/assistant_chat_security_audit.md` — Phase 4 security & QA audit.
