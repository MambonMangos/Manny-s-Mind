"""Fixture Engine – single source of truth for all fixture-related calculations.

Consolidates fixture map construction (previously duplicated 4x), fixture
score formulas (previously duplicated 3x), and DIFFICULTY_LABELS (previously
defined in 3 files).
"""

from __future__ import annotations

from services.fixture_service import Fixture
from services.assistant_manager.models import FixtureInfo

DIFFICULTY_LABELS: dict[int, str] = {
    1: "Very Easy",
    2: "Easy",
    3: "Neutral",
    4: "Hard",
    5: "Very Hard",
}


def build_fixture_map(fixtures: list[dict] | list[Fixture]) -> dict[int, list[dict]]:
    """Build fixture map: team_id → list of fixture dicts sorted by gameweek.

    Accepts either raw fixture dicts (from fixture_service) or Fixture objects.
    This is the SINGLE implementation — never build a fixture_map anywhere else.
    """
    fixture_map: dict[int, list[dict]] = {}
    for f in fixtures:
        if isinstance(f, Fixture):
            event = f.event
            tid_h = f.team_h
            tid_a = f.team_a
            diff_h = f.team_h_difficulty
            diff_a = f.team_a_difficulty
        else:
            event = f.get("event", 0)
            tid_h = f.get("team_h", 0)
            tid_a = f.get("team_a", 0)
            diff_h = f.get("team_h_difficulty", 3)
            diff_a = f.get("team_a_difficulty", 3)

        fixture_map.setdefault(tid_h, []).append({
            "gameweek": event,
            "opponent_id": tid_a,
            "home": True,
            "difficulty": diff_h,
        })
        fixture_map.setdefault(tid_a, []).append({
            "gameweek": event,
            "opponent_id": tid_h,
            "home": False,
            "difficulty": diff_a,
        })

    for tid in fixture_map:
        fixture_map[tid].sort(key=lambda x: x["gameweek"])

    return fixture_map


def compute_fixture_score(difficulty: int) -> float:
    """Convert a difficulty rating (1-5) to a 0-100 score.

    Difficulty 1 = easiest (score 100), difficulty 5 = hardest (score 0).
    This is the SINGLE implementation — never compute fixture score inline.
    """
    return ((5 - difficulty) / 4) * 100


def get_fixture_info(
    row,  # noqa: ANN001
    fixture_map: dict[int, list[dict]],
    team_name_map: dict[int, str],
    window_size: int = 6,
) -> tuple[list[FixtureInfo], list[FixtureInfo]]:
    """Build FixtureInfo lists for next N GWs for a player's team.

    Returns (next_3, next_6) or (first_half, second_half) depending on window_size.
    """
    team_id = int(row["team_id"])
    fixtures = fixture_map.get(team_id, [])

    result = []
    for f in fixtures[:window_size]:
        info = FixtureInfo(
            gameweek=f["gameweek"],
            opponent=team_name_map.get(f["opponent_id"], "?"),
            opponent_short=f"GW{f['gameweek']}",
            home=f["home"],
            difficulty=f["difficulty"],
            difficulty_label=DIFFICULTY_LABELS.get(f["difficulty"], "Neutral"),
        )
        result.append(info)

    return result[:3], result[:6]


def build_fixture_window(
    players,  # noqa: ANN001
    fixture_map: dict[int, list[dict]],
    team_name_map: dict[int, str],
    window_size: int,
):
    """Build a FixtureWindow for a squad over a given gameweek window."""
    from services.assistant_manager.models import FixtureWindow

    all_diffs: list[int] = []
    easy_count = 0
    hard_count = 0

    for p in players:
        team_fixtures = fixture_map.get(p.team_id, [])
        for f in team_fixtures[:window_size]:
            diff = f["difficulty"]
            all_diffs.append(diff)
            if diff <= 2:
                easy_count += 1
            elif diff >= 4:
                hard_count += 1

    if not all_diffs:
        return None

    avg_diff = sum(all_diffs) / len(all_diffs)
    return FixtureWindow(
        gameweek_start=1,
        gameweek_end=window_size,
        avg_difficulty=round(avg_diff, 2),
        easy_fixtures=easy_count,
        hard_fixtures=hard_count,
    )


def detect_fixture_swings(
    players,  # noqa: ANN001
    fixture_map: dict[int, list[dict]],
    team_name_map: dict[int, str],
) -> list[str]:
    """Detect fixture swings between first half and second half of a 6-GW window."""
    swings: list[str] = []

    for p in players:
        team_fixtures = fixture_map.get(p.team_id, [])
        first_half = team_fixtures[:3]
        second_half = team_fixtures[3:6]

        if first_half and second_half:
            avg1 = sum(f["difficulty"] for f in first_half) / len(first_half)
            avg2 = sum(f["difficulty"] for f in second_half) / len(second_half)
            diff = avg1 - avg2

            if diff > 1.0:
                swings.append(
                    f"{p.web_name} ({p.team_short}): fixtures improve "
                    f"(GW1-3 avg {avg1:.1f} → GW4-6 avg {avg2:.1f})"
                )
            elif diff < -1.0:
                swings.append(
                    f"{p.web_name} ({p.team_short}): fixtures worsen "
                    f"(GW1-3 avg {avg1:.1f} → GW4-6 avg {avg2:.1f})"
                )

    return swings


def compute_player_fixture_scores(
    comp_df,  # noqa: ANN001
    fixture_df,  # noqa: ANN001
) -> list[dict]:
    """Compute average fixture score for each player in a comparison DataFrame."""
    player_fixture_scores = []
    for _, prow in comp_df.iterrows():
        team_id = prow["team_id"]
        team_fix = fixture_df[fixture_df["team_id"] == team_id]
        avg = team_fix["fixture_score"].mean() if not team_fix.empty else 0
        player_fixture_scores.append({
            "player": prow["web_name"],
            "team": prow["team_short"],
            "score": round(avg, 1),
        })
    return player_fixture_scores


def build_fixture_heatmap_data(
    fixture_df,  # noqa: ANN001
) -> tuple:  # noqa: ANN001
    """Build pivot tables for fixture difficulty heatmap.

    Returns (pivot_diff, pivot_opp, text_labels).
    """
    import pandas as pd

    pivot_diff = fixture_df.pivot_table(
        index="gameweek",
        columns="team_name",
        values="difficulty",
        aggfunc="first",
    )
    pivot_opp = fixture_df.pivot_table(
        index="gameweek",
        columns="team_name",
        values="opponent_name",
        aggfunc="first",
    )

    text_labels = pivot_diff.copy().astype(str)
    for gw in pivot_diff.index:
        for team in pivot_diff.columns:
            diff = pivot_diff.loc[gw, team]
            opp = pivot_opp.loc[gw, team] if team in pivot_opp.columns else ""
            text_labels.loc[gw, team] = f"{opp}\n{int(diff)}"

    return pivot_diff, pivot_opp, text_labels


def build_fixture_summary(
    comp_df,  # noqa: ANN001
    fixture_df,  # noqa: ANN001
) -> list[dict]:
    """Build per-player fixture summary rows."""
    import pandas as pd

    summary_rows = []
    for _, row in comp_df.iterrows():
        team_id = row["team_id"]
        team_fix = fixture_df[fixture_df["team_id"] == team_id]
        if team_fix.empty:
            continue
        avg_diff = team_fix["difficulty"].mean()
        avg_score = team_fix["fixture_score"].mean()
        easy = len(team_fix[team_fix["difficulty"] <= 2])
        hard = len(team_fix[team_fix["difficulty"] >= 4])
        summary_rows.append({
            "Player": row["web_name"],
            "Team": row["team_short"],
            "Avg Difficulty": round(avg_diff, 1),
            "Avg Score": round(avg_score, 1),
            "Easy Fixtures (1-2)": easy,
            "Hard Fixtures (4-5)": hard,
            "Total GWs": len(team_fix),
        })
    return summary_rows


# ------------------------------------------------------------------
# Enhanced fixture features (Phase 2B)
# ------------------------------------------------------------------

def compute_fixture_windows(
    store,  # noqa: ANN001
) -> pd.DataFrame:
    """Compute multi-GW fixture window features for all players.

    Returns a DataFrame with:
      player_id, fixture_avg_1gw, fixture_avg_3gw, fixture_avg_6gw,
      home_count_next_3, easy_count, hard_count, fixture_swing,
      home_away_split_score, opponent_tier_avg
    """
    from utils.config import load_config

    cfg = load_config("fixtures")
    home_advantage = cfg.get("home_advantage", 0.3)
    dgw_multiplier = cfg.get("dgw_multiplier", 1.8)
    swing_threshold = cfg.get("swing_threshold", 1.0)

    df = store.df
    fixture_map = store.fixture_map
    results = []

    for _, row in df.iterrows():
        team_id = int(row.get("team_id", 0) or 0)
        fixtures = fixture_map.get(team_id, [])

        # Multi-GW averages
        avg_1 = _avg_difficulty(fixtures, 1)
        avg_3 = _avg_difficulty(fixtures, 3)
        avg_6 = _avg_difficulty(fixtures, 6)

        # Home/away split for next 3
        home_3 = _home_count(fixtures, 3)
        away_3 = 3 - home_3 if len(fixtures) >= 3 else len(fixtures) - home_3

        # Home/away score adjustment
        home_diffs = [f["difficulty"] for f in fixtures[:3] if f.get("home", False)]
        away_diffs = [f["difficulty"] for f in fixtures[:3] if not f.get("home", False)]
        home_avg = np.mean(home_diffs) if home_diffs else 3.0
        away_avg = np.mean(away_diffs) if away_diffs else 3.0
        home_away_split = away_avg - home_avg  # positive = easier at home

        # Fixture swing
        first_3 = [f["difficulty"] for f in fixtures[:3]]
        second_3 = [f["difficulty"] for f in fixtures[3:6]]
        swing = 0.0
        if first_3 and second_3:
            swing = np.mean(first_3) - np.mean(second_3)

        # Easy/hard counts
        easy = sum(1 for f in fixtures[:6] if f.get("difficulty", 3) <= 2)
        hard = sum(1 for f in fixtures[:6] if f.get("difficulty", 3) >= 4)

        # Opponent tier average (difficulty distribution)
        all_diffs = [f["difficulty"] for f in fixtures[:6]]
        opponent_tier = _classify_opponent_tier(all_diffs)

        # DGW detection
        gw_counts = {}
        for f in fixtures[:6]:
            gw = f.get("gameweek", 0)
            gw_counts[gw] = gw_counts.get(gw, 0) + 1
        has_dgw = any(c > 1 for c in gw_counts.values())

        results.append({
            "player_id": int(row.get("player_id", 0)),
            "web_name": row.get("web_name", ""),
            "position": row.get("position", ""),
            "fixture_avg_1gw": round(avg_1, 2),
            "fixture_avg_3gw": round(avg_3, 2),
            "fixture_avg_6gw": round(avg_6, 2),
            "home_count_next_3": home_3,
            "away_count_next_3": away_3,
            "fixture_easy_count": easy,
            "fixture_hard_count": hard,
            "fixture_swing": round(swing, 2),
            "home_away_split_score": round(home_away_split, 2),
            "home_avg_difficulty": round(home_avg, 2),
            "away_avg_difficulty": round(away_avg, 2),
            "opponent_tier": opponent_tier,
            "has_dgw_next_6": has_dgw,
        })

    return pd.DataFrame(results)


def _avg_difficulty(fixtures: list[dict], n: int) -> float:
    """Average difficulty over next n fixtures."""
    diffs = [f["difficulty"] for f in fixtures[:n]]
    return np.mean(diffs) if diffs else 3.0


def _home_count(fixtures: list[dict], n: int) -> int:
    """Count home fixtures in next n."""
    return sum(1 for f in fixtures[:n] if f.get("home", False))


def _classify_opponent_tier(diffs: list[float]) -> str:
    """Classify overall opponent difficulty tier."""
    if not diffs:
        return "unknown"
    avg = np.mean(diffs)
    if avg <= 2.0:
        return "easy"
    if avg <= 3.0:
        return "average"
    if avg <= 4.0:
        return "hard"
    return "very_hard"


def compute_fixture_score_enhanced(
    difficulty: int,
    home: bool = False,
    rest_days: int = 3,
    is_dgw: bool = False,
    config: dict | None = None,
) -> float:
    """Enhanced fixture score with home advantage, rest, and DGW modifiers.

    Parameters
    ----------
    difficulty : int
        FPL difficulty rating (1-5).
    home : bool
        Whether the team is playing at home.
    rest_days : int
        Days since last match.
    is_dgw : bool
        Whether this is a double gameweek.
    config : dict, optional
        Overrides from fixtures_v1.yaml.

    Returns
    -------
    float
        Score 0-100 (higher = more favorable).
    """
    cfg = config or {}
    base_score = ((5 - difficulty) / 4) * 100

    # Home advantage
    if home:
        base_score += cfg.get("home_advantage", 0.3) * 100

    # Rest days
    rest_mods = cfg.get("rest_modifiers", {})
    rest_thresholds = cfg.get("rest_days", {})
    if rest_days < rest_thresholds.get("very_tired", 2):
        base_score += rest_mods.get("very_tired", -0.4) * 100
    elif rest_days < rest_thresholds.get("tired", 3):
        base_score += rest_mods.get("tired", -0.2) * 100
    elif rest_days > rest_thresholds.get("very_fresh", 7):
        base_score += rest_mods.get("very_fresh", 0.25) * 100
    elif rest_days > rest_thresholds.get("fresh", 5):
        base_score += rest_mods.get("fresh", 0.15) * 100

    # DGW multiplier
    if is_dgw:
        base_score *= cfg.get("dgw_multiplier", 1.8)

    return np.clip(base_score, 0, 150)  # can exceed 100 for DGW
