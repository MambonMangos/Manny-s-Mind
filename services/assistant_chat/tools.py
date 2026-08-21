"""Conversational Assistant — deterministic analytical tools (Phase 3).

Pure computations over the in-memory :class:`ChatContext` (which only carries
V3 report data). Tools answer well-scoped questions — player comparison,
transfer proposals, captaincy, budget — with exact numbers and provenance,
without calling the LLM, the database, or any engine (directive: the chatbot
sits on top of the intelligence platform and never re-derives predictions).

Contract: :func:`run_tools` inspects one user message and returns a
:class:`ToolResult` when a tool matches, else ``None`` so the engine falls
through to the conversational provider. Every tool is deterministic, safe
(no execution, no side effects) and cheap (never counted as a paid request).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from services.assistant_chat.context import ChatContext
from services.squad_validator import Player, Squad, validate_squad
from utils.fpl_rules import SQUAD_SIZE, format_validation_errors

# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """A deterministic answer produced by one analytical tool."""

    name: str
    content: str
    sources: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Player view: merge squad / projection / differential rows by name
# ---------------------------------------------------------------------------

_OWNED_FIELDS = (
    "price",
    "form",
    "xgi_per_90",
    "xpts",
    "selected_by",
    "fixtures",
    "team",
    "status",
    "news",
    "risks",
)
_PROJ_FIELDS = (
    "position",
    "xpts",
    "xpts_per_90",
    "expected_minutes",
    "start_probability",
    "confidence",
)
_DIFF_FIELDS = ("position", "xpts", "ownership")
_SHADOW_PROJ_FIELDS = ("position", "xpts", "expected_minutes", "start_probability")


def _norm_name(name: str) -> str:
    # Decompose accents (é → e + combining accent), strip combining marks,
    # then normalize whitespace — so "Guéhi" and "Guehi" both produce "guehi".
    normalized = unicodedata.normalize("NFKD", name.lower())
    stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _build_player_index(context: ChatContext) -> dict[str, dict]:
    """Merge all context rows into one per-name player view.

    Squad rows win for ownership/price/form; projection rows add the V3 rate
    and minutes detail; differential rows add ownership. Keys are normalized
    names so "Saka" matches "SAKA" and "De Bruyne" matches "de bruyne".
    """
    index: dict[str, dict] = {}
    for row in context.squad:
        key = _norm_name(str(row.get("player", "")))
        if not key:
            continue
        view = index.setdefault(key, {"name": str(row.get("player")), "owned": True})
        for f in _OWNED_FIELDS:
            value = row.get(f)
            if value not in (None, "", []):
                view.setdefault(f, value)
        view.setdefault("position", row.get("position", ""))

    for row in context.top_projections:
        key = _norm_name(str(row.get("player", "")))
        if not key:
            continue
        view = index.setdefault(key, {"name": str(row.get("player")), "owned": False})
        for f in _PROJ_FIELDS:
            value = row.get(f)
            if value is not None:
                view[f] = value

    for row in context.top_differentials:
        key = _norm_name(str(row.get("player", "")))
        if not key:
            continue
        view = index.setdefault(key, {"name": str(row.get("player")), "owned": False})
        for f in _DIFF_FIELDS:
            value = row.get(f)
            if value is not None:
                view.setdefault(f, value)

    # Shadow model projections (Model D) — keyed as xpts_{model_id}
    for model_id, shadow_rows in context.shadow_projections.items():
        short_key = model_id.replace("v3_hist_", "xpts_")
        for row in shadow_rows:
            key = _norm_name(str(row.get("player", "")))
            if not key:
                continue
            view = index.setdefault(
                key, {"name": str(row.get("player")), "owned": False}
            )
            if "xpts" in row:
                view[short_key] = row["xpts"]

    return index


_NAME_RE = re.compile(r"[a-z0-9]+")


def _find_players(message: str, index: dict[str, dict]) -> list[str]:
    """Names found in the message, in order of appearance (longest first).

    Matches are whole-word so "Saka" does not match inside "Sakata".
    """
    norm_msg = _norm_name(message)
    found: list[tuple[int, str]] = []
    for key, view in index.items():
        tokens = key.split()
        if not tokens:
            continue
        pattern = re.compile(
            r"(?<![a-z0-9])"
            + r"[\- ]*".join(re.escape(t) for t in tokens)
            + r"(?![a-z0-9])"
        )
        m = pattern.search(norm_msg)
        if m:
            found.append((m.start(), view["name"]))
    found.sort(key=lambda pair: (pair[0], -len(pair[1])))
    return [name for _pos, name in found]


def _has_captaincy_intent(low: str) -> bool:
    return any(word in low for word in ("captain", "captaincy", "armband", "(c)"))


def _has_compare_intent(low: str) -> bool:
    return any(
        word in low for word in ("compare", "comparison", "versus", " vs ", "better")
    )


def _has_budget_intent(low: str) -> bool:
    return any(
        word in low
        for word in ("afford", "affordable", "cost", "bank", "price of", "budget")
    )


def _has_transfer_intent(low: str) -> bool:
    return any(
        word in low
        for word in (
            "sell",
            "buy",
            "bring in",
            "sign",
            "transfer",
            "swap",
            "replace",
            "downgrade",
            "upgrade",
            "drop",
            "remove",
            "get rid of",
        )
    ) or bool(re.search(r"\bout\b.*\bin\b|\bin\b.*\bout\b", low))


def _has_validate_intent(low: str) -> bool:
    return any(
        word in low
        for word in (
            "validate",
            "check squad",
            "squad valid",
            "is my squad legal",
            "is my team legal",
            "squad check",
            "check my team",
        )
    )


def _has_multi_transfer_intent(low: str) -> bool:
    """Detect intent for evaluating a complete multi-transfer plan."""
    return (
        "validate transfer" in low
        or "check transfer" in low
        or "transfer plan" in low
        or "will this work" in low
        or ("sell" in low and "buy" in low)
    )


# ---------------------------------------------------------------------------
# Individual tools
# ---------------------------------------------------------------------------


def _view_to_sources(context: ChatContext, view: dict) -> list[str]:
    gw = context.gameweek or "?"
    lines = []
    name = view["name"]
    if "xpts" in view:
        lines.append(f"V3 xPts GW{gw}: {name} {view['xpts']}")
    if "xpts_per_90" in view:
        lines.append(f"V3 xPts/90 GW{gw}: {name} {view['xpts_per_90']}")
    if "expected_minutes" in view:
        lines.append(
            f"V3 expected minutes GW{gw}: {name} {view['expected_minutes']:.0f}"
        )
    if "start_probability" in view:
        lines.append(
            f"V3 start probability GW{gw}: {name} {view['start_probability']:.0%}"
        )
    if "price" in view:
        lines.append(f"FPL price: {name} {view['price']}m")
    if "fixtures" in view:
        lines.append(f"FPL fixtures: {name} — {view['fixtures']}")
    return lines


def compare_players(context: ChatContext, names: list[str]) -> ToolResult:
    """Compare two or more players on every available V3/FPL field."""
    index = _build_player_index(context)
    rows = []
    sources: list[str] = []
    for name in names:
        key = _norm_name(name)
        view = index.get(key)
        if view is None:
            rows.append({"Player": name, "Status": "no V3 data in context"})
            sources.append(f"No V3 projection for {name} in this report")
            continue
        row: dict[str, Any] = {
            "Player": view["name"],
            "Pos": view.get("position", "-"),
            "xPts": view.get("xpts", "-"),
        }
        if "xpts_d_team" in view:
            row["Model D"] = view["xpts_d_team"]
        for field_, label in (
            ("xpts_per_90", "xPts/90"),
            ("expected_minutes", "Mins"),
            ("start_probability", "Start"),
            ("price", "Price"),
            ("form", "Form"),
            ("selected_by", "Owned"),
            ("ownership", "Diff Own"),
        ):
            value = view.get(field_)
            if value is not None:
                if field_ == "start_probability":
                    value = f"{value:.0%}"
                row[label] = value
        rows.append(row)
        sources.extend(_view_to_sources(context, view))

    columns = list(rows[0].keys())
    for row in rows[1:]:
        for key in row:
            if key not in columns:
                columns.append(key)
    lines = ["| " + " | ".join(columns) + " |"]
    lines.append("|" + "---|" * len(columns))
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(k, "-")) for k in columns) + " |")
    content = "\n".join(lines)
    return ToolResult(name="compare_players", content=content, sources=sources)


def evaluate_user_proposal(
    context: ChatContext, out_name: str, in_name: str, hits: int = 0
) -> ToolResult:
    """Score a user transfer proposal with exact V3 numbers.

    ``out`` must be owned; ``in`` may be any player with a projection. Uses
    price only when the report carries it (squad rows) — otherwise flags it.
    """
    index = _build_player_index(context)
    out = index.get(_norm_name(out_name))
    in_ = index.get(_norm_name(in_name))
    if out is None or not out.get("owned"):
        return ToolResult(
            name="evaluate_user_proposal",
            content=f"**{out_name}** is not in your squad, so this can't be a "
            "direct transfer. Choose an outgoing player from your squad.",
            sources=[f"Squad row for {out_name} not found in this report"],
        )
    if in_ is None or in_.get("xpts") is None:
        return ToolResult(
            name="evaluate_user_proposal",
            content=f"I don't have a V3 projection for **{in_name}** in this "
            "report, so I can't score that move. Try a player from the "
            "top V3 projections.",
            sources=[f"No V3 projection for {in_name} in this report"],
        )

    out_xpts = float(out["xpts"])
    in_xpts = float(in_["xpts"])
    delta = in_xpts - out_xpts
    hit_cost = 4 * max(int(hits), 0)
    net = delta - hit_cost

    lines = [
        f"**{in_['name']} in for {out['name']}** — V3 says:",
        "",
        f"- {out['name']} xPts: **{out_xpts:.1f}**",
        f"- {in_['name']} xPts: **{in_xpts:.1f}**",
        f"- xPts change: **{delta:+.1f}**",
    ]
    if "xpts_d_team" in out and "xpts_d_team" in in_:
        d_out = float(out["xpts_d_team"])
        d_in = float(in_["xpts_d_team"])
        d_delta = d_in - d_out
        lines.append(
            f"- Model D: {out['name']} {d_out:.1f} -> {in_['name']} {d_in:.1f} "
            f"(change {d_delta:+.1f})"
        )
    if hits:
        lines.append(f"- Hit cost: **-{hit_cost}** ({hits} transfer(s) past free)")
    lines.append(f"- **Net expected gain: {net:+.1f} points**")

    if "price" in out and "price" in in_:
        out_price = float(out["price"])
        in_price = float(in_["price"])
        extra = in_price - out_price
        affordable = context.bank + out_price >= in_price - 1e-6
        lines.append(
            f"- Price: {out['name']} {out_price}m -> {in_['name']} {in_price}m "
            f"(extra {extra:+.1f}m, bank {context.bank}m) "
            f"— **{'affordable' if affordable else 'over budget'}**"
        )
    else:
        lines.append("- Price: not available for one of these players in this report")

    if net >= 0.5:
        verdict = "V3 supports this move."
    elif net <= -0.5:
        verdict = "V3 argues against this move."
    else:
        verdict = "V3 says this is roughly neutral."
    if "xpts_d_team" in out and "xpts_d_team" in in_:
        d_delta = float(in_["xpts_d_team"]) - float(out["xpts_d_team"])
        if (d_delta > 0.5 and net > 0.5) or (d_delta < -0.5 and net < -0.5):
            verdict += " Model D agrees."
        elif (d_delta > 0.5 and net < -0.5) or (d_delta < -0.5 and net > 0.5):
            verdict += " Model D disagrees."
    lines.append(f"\n**Verdict:** {verdict}")

    if "start_probability" in in_ and float(in_["start_probability"]) < 0.6:
        lines.append(
            f"*Caution: {in_['name']} start probability is "
            f"{float(in_['start_probability']):.0%} this week.*"
        )

    sources = _view_to_sources(context, out) + _view_to_sources(context, in_)
    return ToolResult(
        name="evaluate_user_proposal", content="\n".join(lines), sources=sources
    )


def captaincy(context: ChatContext) -> ToolResult:
    """Top captain picks by V3 xPts, with start risk and fixtures.

    Prefers owned squad players. When the squad carries no V3 xPts (e.g. no
    live squad data yet), falls back to the top V3 projections so the advice
    stays useful.
    """
    index = _build_player_index(context)
    owned = [v for v in index.values() if v.get("owned") and "xpts" in v]
    if owned:
        ranked = sorted(owned, key=lambda v: float(v["xpts"]), reverse=True)
        heading = "Top captain picks from your squad, by V3 xPts:"
    else:
        ranked = [v for v in index.values() if v.get("xpts")]
        ranked = sorted(ranked, key=lambda v: float(v["xpts"]), reverse=True)
        if not ranked:
            return ToolResult(
                name="captaincy",
                content="No V3 xPts projections are available in this report to "
                "rank captain picks.",
                sources=["V3 xPts missing from this report"],
            )
        heading = (
            "No live squad data yet, so these are the top V3 captain picks "
            "available right now:"
        )
    lines = [
        heading,
        "",
        "| Player | xPts | Model D | Start | Form | Fixtures |",
        "|--------|------|---------|-------|------|----------|",
    ]
    sources: list[str] = []
    for view in ranked[:3]:
        start = (
            f"{float(view.get('start_probability', 0)):.0%}"
            if "start_probability" in view
            else "-"
        )
        d_val = view.get("xpts_d_team", "-")
        lines.append(
            f"| {view['name']} | {view['xpts']} | {d_val} | {start} | "
            f"{view.get('form', '-')} | {view.get('fixtures', '-')} |"
        )
        sources.extend(_view_to_sources(context, view))
    return ToolResult(name="captaincy", content="\n".join(lines), sources=sources)


def validate_current_squad(context: ChatContext) -> ToolResult:
    """Validate the user's current squad against all FPL rules.

    Returns a structured validation result showing whether the squad is legal,
    with specific error codes for any violations found.
    """
    if not context.squad:
        return ToolResult(
            name="validate_current_squad",
            content="No squad data available to validate.",
            sources=["No squad in context"],
        )

    # Build Player objects from context
    players = []
    for row in context.squad:
        try:
            players.append(Player(
                player_id=hash(row.get("player", "")) & 0xFFFFFFFF,
                web_name=str(row.get("player", "")),
                position=str(row.get("position", "")),
                team_id=0,  # not available in chat context
                price=float(row.get("price", 0)),
            ))
        except (ValueError, TypeError):
            continue

    if len(players) != SQUAD_SIZE:
        return ToolResult(
            name="validate_current_squad",
            content=format_validation_errors([
                __import__("utils.fpl_rules", fromlist=["ValidationError"]).ValidationError(
                    "INVALID_SQUAD_SIZE",
                    f"Squad has {len(players)} players, must have exactly {SQUAD_SIZE}.",
                )
            ]),
            sources=["Squad size check"],
        )

    squad = Squad(players=tuple(players))
    result = validate_squad(squad)

    # Format output
    lines = [
        "**Squad Validation Result:**",
        "",
        f"- Status: **{'VALID' if result.valid else 'INVALID'}**",
        f"- Squad size: {result.squad_size}",
        f"- Total cost: £{result.total_cost:.1f}m",
        f"- Bank: £{result.bank:.1f}m",
        f"- Position counts: {result.position_counts}",
    ]

    if result.errors:
        lines.append("")
        lines.append("**Issues found:**")
        for err in result.errors:
            lines.append(f"- [{err.code}] {err.message}")

    sources = [f"Squad validation: {len(players)} players, £{result.total_cost:.1f}m"]
    return ToolResult(
        name="validate_current_squad",
        content="\n".join(lines),
        sources=sources,
    )


def evaluate_transfer_plan(
    context: ChatContext,
    sell_names: list[str],
    buy_names: list[str],
) -> ToolResult:
    """Validate a complete multi-transfer plan by constructing and checking
    the resulting squad.

    Unlike evaluate_user_proposal (which checks one swap), this validates
    the ENTIRE resulting squad after all transfers are applied.

    This is the deterministic constraint layer that prevents illegal squads
    from reaching the user.
    """
    index = _build_player_index(context)

    # Resolve sell candidates
    sell_players = []
    for name in sell_names:
        view = index.get(_norm_name(name))
        if view is None or not view.get("owned"):
            return ToolResult(
                name="evaluate_transfer_plan",
                content=f"**{name}** is not in your squad — cannot sell them.",
                sources=[f"Sell target {name} not found in squad"],
            )
        sell_players.append(view)

    # Resolve buy candidates
    buy_players = []
    for name in buy_names:
        view = index.get(_norm_name(name))
        if view is None:
            return ToolResult(
                name="evaluate_transfer_plan",
                content=f"No data for **{name}** in this report.",
                sources=[f"Buy target {name} not found in projections"],
            )
        buy_players.append(view)

    # Must sell and buy the same number
    if len(sell_players) != len(buy_players):
        return ToolResult(
            name="evaluate_transfer_plan",
            content=(
                f"Selling {len(sell_players)} but buying {len(buy_players)} "
                "players. Must be equal to maintain a legal 15-player squad."
            ),
            sources=["Transfer count mismatch"],
        )

    # Build Squad from context
    squad_players = []
    for row in context.squad:
        try:
            squad_players.append(Player(
                player_id=hash(row.get("player", "")) & 0xFFFFFFFF,
                web_name=str(row.get("player", "")),
                position=str(row.get("position", "")),
                team_id=0,
                price=float(row.get("price", 0)),
            ))
        except (ValueError, TypeError):
            continue

    if len(squad_players) != SQUAD_SIZE:
        return ToolResult(
            name="evaluate_transfer_plan",
            content="Cannot validate — squad data incomplete.",
            sources=["Squad size mismatch"],
        )

    current_squad = Squad(players=tuple(squad_players))

    # Build Player objects for incoming players
    incoming = []
    for view in buy_players:
        try:
            incoming.append(Player(
                player_id=hash(view.get("name", "")) & 0xFFFFFFFF,
                web_name=str(view.get("name", "")),
                position=str(view.get("position", "")),
                team_id=0,
                price=float(view.get("price", 0)) if view.get("price") else 0.0,
            ))
        except (ValueError, TypeError):
            return ToolResult(
                name="evaluate_transfer_plan",
                content=f"Missing price data for **{view.get('name', '?')}**.",
                sources=["Price data incomplete"],
            )

    # Build sell IDs
    sell_ids = [hash(p.get("name", "")) & 0xFFFFFFFF for p in sell_players]

    # Validate the complete transfer plan
    from services.squad_validator import validate_transfer_proposal
    validation = validate_transfer_proposal(
        current_squad=current_squad,
        sold_ids=sell_ids,
        bought_players=incoming,
    )

    # Format output
    lines = [
        "**Transfer Plan Validation:**",
        "",
        f"- Sell: {', '.join(sell_names)}",
        f"- Buy: {', '.join(buy_names)}",
        f"- Status: **{'VALID' if validation.valid else 'INVALID'}**",
        f"- Resulting bank: £{validation.resulting_bank:.1f}m",
        f"- Cost change: £{validation.cost_change:+.1f}m",
    ]

    if validation.errors:
        lines.append("")
        lines.append("**Issues found:**")
        for err in validation.errors:
            lines.append(f"- [{err.code}] {err.message}")
        lines.append("")
        lines.append(
            "**This transfer plan is not legal under FPL rules. "
            "I will not recommend an invalid squad.**"
        )
    else:
        # Add xPts impact if available
        total_delta = 0.0
        for sell_v, buy_v in zip(sell_players, buy_players):
            sell_xpts = float(sell_v.get("xpts", 0) or 0)
            buy_xpts = float(buy_v.get("xpts", 0) or 0)
            delta = buy_xpts - sell_xpts
            total_delta += delta
            lines.append(
                f"- {sell_v['name']} ({sell_xpts:.1f} xPts) → "
                f"{buy_v['name']} ({buy_xpts:.1f} xPts): **{delta:+.1f}**"
            )
        lines.append(f"\n- **Total projected change: {total_delta:+.1f} xPts**")

    sources = []
    for v in sell_players + buy_players:
        sources.extend(_view_to_sources(context, v))

    return ToolResult(
        name="evaluate_transfer_plan",
        content="\n".join(lines),
        sources=sources,
    )


def budget_math(context: ChatContext, name: str) -> ToolResult:
    """What a player costs, and the most expensive player you could afford."""
    index = _build_player_index(context)
    view = index.get(_norm_name(name))
    if view is None:
        return ToolResult(
            name="budget_math",
            content=f"I don't have data for **{name}** in this report.",
            sources=[f"No context row for {name}"],
        )
    if "price" not in view:
        return ToolResult(
            name="budget_math",
            content=f"**{view['name']}** has a V3 projection but this report "
            "does not carry their price, so I can't do budget math for "
            "them. Prices are available for squad players.",
            sources=_view_to_sources(context, view),
        )
    price = float(view["price"])
    max_buy = context.bank + price
    lines = [
        f"**{view['name']}** costs **{price}m** (bank {context.bank}m).",
        (
            f"Keeping them, the most expensive player you could buy outright is "
            f"**{max_buy:.1f}m**."
        ),
        (
            f"Free transfers: **{context.free_transfers}**; saved: "
            f"**{context.saved_transfers}**."
        ),
    ]
    return ToolResult(
        name="budget_math",
        content="\n".join(lines),
        sources=_view_to_sources(context, view),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HIT_RE = re.compile(r"-(\d+)")


def _parse_hits(low: str) -> int:
    """Infer the number of transfers past free from a '-4' / '-8' mention."""
    m = _HIT_RE.search(low)
    if not m:
        return 0
    points = int(m.group(1))
    return max(0, points // 4)


def _parse_transfer(text: str, names: list[str]) -> tuple[str | None, str | None]:
    """Decide which matched name is outgoing and which is incoming."""
    low = text.lower()
    if len(names) < 2:
        return None, None

    def span(n: str) -> int:
        pos = low.find(_norm_name(n))
        return pos if pos >= 0 else 10**9

    ordered = sorted(names, key=span)

    # Explicit "X out ... Y in" or "Y in ... X out"
    m = re.search(r"\bout\b", low)
    m_in = re.search(r"\bin\b", low)
    if m and m_in:
        if m.start() < m_in.start():
            return ordered[0], ordered[1]
        return ordered[1], ordered[0]

    # Verb-led phrasing: "sell X for Y" / "buy Y for X"
    for out_verb in (
        "sell",
        "drop",
        "downgrade",
        "upgrade",
        "swap",
        "remove",
        "get rid of",
        "replace",
        "transfer",
    ):
        idx = low.find(out_verb)
        if idx >= 0:
            after = low[idx:]
            if any(nn in after for nn in ("for", "to", "with")):
                # First name after the verb is the outgoing player.
                return ordered[0], ordered[1]
    for in_verb in ("buy", "bring in", "sign"):
        if in_verb in low:
            return ordered[1], ordered[0]
    return ordered[0], ordered[1]


def run_tools(context: ChatContext, message: str) -> ToolResult | None:
    """Route one user message to a tool, or return ``None``.

    Priority: validate_squad > multi_transfer > captaincy > transfer proposal > comparison > budget.
    Requires a matched player name (captaincy works without one).
    Never raises — any unexpected issue simply falls through to the
    conversational provider.
    """
    if not message:
        return None
    low = message.lower()
    index = _build_player_index(context)
    names = _find_players(message, index)

    # Squad validation (no player match needed)
    if _has_validate_intent(low):
        return validate_current_squad(context)

    # Multi-transfer plan validation
    if _has_multi_transfer_intent(low) and len(names) >= 2:
        # Try to parse sell/buy from the message
        sell_names, buy_names = _parse_multi_transfer(message, names)
        if sell_names and buy_names:
            return evaluate_transfer_plan(context, sell_names, buy_names)

    if _has_captaincy_intent(low):
        return captaincy(context)

    if _has_transfer_intent(low):
        out_name, in_name = _parse_transfer(message, names)
        if out_name and in_name:
            return evaluate_user_proposal(
                context, out_name, in_name, hits=_parse_hits(low)
            )

    if len(names) >= 2 and _has_compare_intent(low):
        return compare_players(context, names)

    if len(names) == 1 and _has_budget_intent(low):
        return budget_math(context, names[0])

    return None


def _parse_multi_transfer(text: str, names: list[str]) -> tuple[list[str], list[str]]:
    """Parse sell and buy lists from a multi-transfer message.

    Tries to identify which names are being sold vs bought.
    """
    low = text.lower()
    sell_names = []
    buy_names = []

    # Look for explicit "sell X Y" and "buy A B" patterns
    sell_match = re.search(r"sell\s+(.+?)(?:\s+and|\s+buy|\s+for|\s+to)", low)
    buy_match = re.search(r"buy\s+(.+?)(?:\s+and|\s+sell|\s+for|\s+from)", low)

    if sell_match and buy_match:
        sell_text = sell_match.group(1)
        buy_text = buy_match.group(1)
        for name in names:
            if _norm_name(name) in _norm_name(sell_text):
                sell_names.append(name)
            elif _norm_name(name) in _norm_name(buy_text):
                buy_names.append(name)
    else:
        # Fallback: first half of names are sell, second half are buy
        mid = len(names) // 2
        if mid > 0:
            sell_names = names[:mid]
            buy_names = names[mid:]

    return sell_names, buy_names
