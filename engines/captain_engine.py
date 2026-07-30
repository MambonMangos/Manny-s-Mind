"""Captain Engine – single source of truth for captaincy analysis.

Enhances the existing recommend_captain with fixture awareness.
"""

from __future__ import annotations

import pandas as pd


def rank_captains(
    squad_df: pd.DataFrame,
    fixture_map: dict[int, list[dict]] | None = None,
    top_n: int = 3,
) -> pd.DataFrame:
    """Pick the top N captain candidates from the squad.

    If fixture_map is provided, incorporates fixture difficulty into the ranking.
    This is the SINGLE implementation — never compute captain rankings inline.
    """
    if squad_df.empty or "value_score" not in squad_df.columns:
        return pd.DataFrame()

    candidates = squad_df.nlargest(top_n * 2, "value_score").copy()

    # If fixture map available, adjust by upcoming difficulty
    if fixture_map is not None and "team_id" in candidates.columns:
        avg_diffs = []
        for _, row in candidates.iterrows():
            team_id = int(row["team_id"])
            fixtures = fixture_map.get(team_id, [])
            if fixtures:
                avg_d3 = sum(f["difficulty"] for f in fixtures[:3]) / min(len(fixtures), 3)
            else:
                avg_d3 = 3.0
            avg_diffs.append(avg_d3)
        candidates["avg_fixture_difficulty"] = avg_diffs
        # Lower difficulty = easier fixtures = bonus
        candidates["captain_score"] = candidates["value_score"] + (5 - candidates["avg_fixture_difficulty"]) * 3
    else:
        candidates["captain_score"] = candidates["value_score"]

    candidates = candidates.nlargest(top_n, "captain_score")
    candidates = candidates[
        [c for c in ["web_name", "team_short", "position", "price", "total_points",
         "expected_goal_involvements", "xgi_per_90", "value_score", "captain_score"]
         if c in candidates.columns]
    ].copy()
    candidates["captain_rank"] = range(1, len(candidates) + 1)
    return candidates
