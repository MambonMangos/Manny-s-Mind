"""Football formation engine – fixed tactical zone positioning.

Every formation maps to rows (GK → DEF → MID → FWD). Each row has a
fixed vertical position and a set of horizontal positions based on the
number of players in that row. All coordinates are pitch-proportional:

    x = 0 (left touchline) → 1 (right touchline)
    y = 0 (own goal line)  → 1 (opponent goal line)

The FPL app shows a vertical pitch attacking upward. Player zones:

    GK   ≈  0.06   – on the goal line
    DEF  ≈  0.20   – lower third
    MID  ≈  0.45   – central band (around halfway)
    FWD  ≈  0.75   – attacking third (just outside penalty area)
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Vertical positions (own goal = 0, opponent goal = 1) ────────────────────

Y_GK: float = 0.06
Y_DEF: float = 0.20
Y_MID: float = 0.45
Y_FWD: float = 0.75

# ── Horizontal positions by row count ───────────────────────────────────────
# Left to right, 0–1 (touchline to touchline).
# Wingers are pushed wide; central players cluster near x=0.5.

X_POSITIONS: dict[int, list[float]] = {
    1: [0.50],
    2: [0.35, 0.65],
    3: [0.22, 0.50, 0.78],
    4: [0.12, 0.36, 0.64, 0.88],
    5: [0.08, 0.28, 0.50, 0.72, 0.92],
}


@dataclass(frozen=True)
class FormationRow:
    """A single tactical row with its fixed coordinates."""
    fpl_position: str   # "GKP", "DEF", "MID", "FWD"
    y: float
    label: str


# ── Formation definitions ───────────────────────────────────────────────────
# Each formation is an ordered list of rows (back to front).

FORMATIONS: dict[str, list[FormationRow]] = {
    "4-4-2": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
    "4-3-3": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
    "4-5-1": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forward"),
    ],
    "3-5-2": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
    "3-4-3": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
    "5-4-1": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forward"),
    ],
    "5-3-2": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
    "5-2-3": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
    "4-2-3-1": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", 0.34, "Defensive Mid"),
        FormationRow("MID", 0.56, "Attacking Mid"),
        FormationRow("FWD", Y_FWD, "Forward"),
    ],
    "4-1-4-1": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", 0.34, "Defensive Mid"),
        FormationRow("MID", 0.56, "Attacking Mid"),
        FormationRow("FWD", Y_FWD, "Forward"),
    ],
    "4-1-2-1-2": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", 0.32, "Defensive Mid"),
        FormationRow("MID", 0.46, "Central Mid"),
        FormationRow("MID", 0.60, "Attacking Mid"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
    "3-4-2-1": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", Y_MID, "Midfielders"),
        FormationRow("FWD", 0.62, "Attacking Mid"),
        FormationRow("FWD", Y_FWD, "Forward"),
    ],
    "3-1-4-2": [
        FormationRow("GKP", Y_GK, "Goalkeeper"),
        FormationRow("DEF", Y_DEF, "Defenders"),
        FormationRow("MID", 0.32, "Defensive Mid"),
        FormationRow("MID", 0.52, "Midfielders"),
        FormationRow("FWD", Y_FWD, "Forwards"),
    ],
}


def get_or_build_formation(defs: int, mids: int, fwds: int) -> list[FormationRow]:
    """Return the formation rows for a given DEF-MID-FWD count.

    Looks up the registered formation first. If not found, builds one
    using the standard vertical positions and correct row counts.
    """
    name = f"{defs}-{mids}-{fwds}"
    if name in FORMATIONS:
        return FORMATIONS[name]

    rows: list[FormationRow] = [FormationRow("GKP", Y_GK, "Goalkeeper")]
    if defs:
        rows.append(FormationRow("DEF", Y_DEF, "Defenders"))
    if mids:
        rows.append(FormationRow("MID", Y_MID, "Midfielders"))
    if fwds:
        rows.append(FormationRow("FWD", Y_FWD, "Forwards"))
    return rows


def get_positions(rows: list[FormationRow], player_df) -> list[dict]:
    """Map players to their tactical coordinates.

    Takes a list of FormationRow and a DataFrame of the starting XI.
    Returns a list of dicts with keys: x, y, web_name, team_short,
    is_captain, is_vice_captain, position.

    Players are assigned to rows in order (GK first, then DEF left to
    right, MID left to right, FWD left to right).
    """

    result: list[dict] = []

    for row in rows:
        row_players = player_df[player_df["position"] == row.fpl_position].sort_values("squad_position")
        if row_players.empty:
            continue

        n = len(row_players)
        xs = X_POSITIONS.get(n, X_POSITIONS.get(3, [0.20, 0.50, 0.80]))[:n]

        for x, (_, player) in zip(xs, row_players.iterrows()):
            result.append({
                "x": x,
                "y": row.y,
                "web_name": player["web_name"],
                "team_short": player["team_short"],
                "is_captain": bool(player.get("is_captain", False)),
                "is_vice_captain": bool(player.get("is_vice_captain", False)),
                "position": row.fpl_position,
                "row_label": row.label,
            })

    return result
