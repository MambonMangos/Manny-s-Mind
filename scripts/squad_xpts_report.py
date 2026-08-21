"""Fetch V3 xPts projections for a specific list of FPL players."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.crud import (
    get_players_dataframe,
    get_prediction_versions,
    get_projections,
)
from database.database import get_session
from engines.fixture_engine import build_fixture_map
from features import build_feature_store
from services.fixture_service import fetch_fixtures
from services.scoring import compute_value_score
from utils.config import get_config_hash, get_primary_model_id

POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
FORMATION = {"GKP": 1, "DEF": 4, "MID": 3, "FWD": 3}

# Target players (exact web_names with accents)
TARGET_PLAYERS = [
    "Kelleher",
    "Van Hecke",
    "Mitchell",
    "Guéhi",
    "Truffert",
    "B.Fernandes",   # Bruno Fernandes — web_name in DB is "B.Fernandes" (Man Utd)
    "Wilson",        # Harry Wilson (Leeds)
    "Tzolis",
    "João Pedro",
    "Haaland",
    "Calvert-Lewin",
    "Verbruggen",
    "Groß",
    "Zubimendi",
    "Diop",
]

# Disambiguation rules for duplicate web_names
BRUNE_TEAM_KEYWORD = "Man"
WILSON_TEAM_KEYWORD = "Leeds"


def find_latest_version(session):
    """Find the latest prediction version for expected_points_v1."""
    model_id = get_primary_model_id()
    print(f"Primary model_id from config: {model_id}")
    versions = get_prediction_versions(session, model_name=model_id, limit=10)
    if not versions:
        print("No prediction versions found for model_name='expected_points_v1'")
        print("Trying all model names...")
        versions = get_prediction_versions(session, limit=20)
        for v in versions:
            print(f"  Found: id={v.id}, tag={v.version_tag}, model={v.model_name}, created={v.created_at}")
        if not versions:
            return None
        # Use the most recent one regardless
        return versions[0]
    for v in versions:
        print(f"  Found expected_points_v1 version: id={v.id}, tag={v.version_tag}, created={v.created_at}")
    return versions[0]


def get_player_row_map(session):
    """Return a map of player_id -> player info dict."""
    player_df = get_players_dataframe(session)
    rows = {}
    for _, r in player_df.iterrows():
        rows[r["id"]] = {
            "web_name": r["web_name"],
            "position": r["position"],
            "team_name": r["team_name"],
            "team_short": r["team_short"],
            "price": r["price"],
        }
    return rows


def resolve_player(web_name, player_rows, seen_ids):
    """Resolve a target player, handling disambiguation for Bruno/Wilson."""
    candidates = []
    for pid, info in player_rows.items():
        if pid in seen_ids:
            continue
        if info["web_name"] == web_name:
            candidates.append((pid, info))

    if not candidates:
        # Try partial match
        for pid, info in player_rows.items():
            if pid in seen_ids:
                continue
            if web_name in info["web_name"]:
                candidates.append((pid, info))

    if not candidates:
        return None, None

    if len(candidates) == 1:
        pid, info = candidates[0]
        seen_ids.add(pid)
        return pid, info

    # Multiple candidates - need disambiguation
    if web_name == "Bruno":
        for pid, info in candidates:
            if BRUNE_TEAM_KEYWORD in info["team_name"]:
                seen_ids.add(pid)
                return pid, info
        # Fallback to first
        pid, info = candidates[0]
        seen_ids.add(pid)
        return pid, info

    if web_name == "Wilson":
        for pid, info in candidates:
            if WILSON_TEAM_KEYWORD in info["team_name"]:
                seen_ids.add(pid)
                return pid, info
        # Fallback to first
        pid, info = candidates[0]
        seen_ids.add(pid)
        return pid, info

    # Default: return first
    pid, info = candidates[0]
    seen_ids.add(pid)
    return pid, info


def main():
    session = get_session()
    try:
        # 1. Find latest version
        print("=" * 80)
        print("V3 xPts PROJECTIONS REPORT")
        print("=" * 80)
        pv = find_latest_version(session)
        if pv is None:
            print("\nNo prediction versions found. Running production predictor...")

            # Build feature store and run predictions
            player_df = get_players_dataframe(session)
            if player_df.empty:
                print("ERROR: No players in database. Run data ingestion first.")
                return

            # Get current gameweek
            from database.models import Gameweek
            gws = session.query(Gameweek).order_by(Gameweek.id.desc()).all()
            if not gws:
                print("ERROR: No gameweeks in database.")
                return

            # Find next or current gameweek
            current_gw = None
            for gw in gws:
                if gw.is_current:
                    current_gw = gw.id
                    break
            if current_gw is None:
                for gw in gws:
                    if gw.is_next:
                        current_gw = gw.id
                        break
            if current_gw is None:
                current_gw = gws[0].id  # latest gameweek

            print(f"Target gameweek: {current_gw}")

            # Build feature store
            fixtures_raw = fetch_fixtures()
            fixture_map = build_fixture_map(fixtures_raw)

            team_df = get_players_dataframe(session)
            team_name_map = dict(zip(team_df["team_id"], team_df["team_name"])) if not team_df.empty else {}
            config_hash = get_config_hash("prediction")

            scored_df = get_players_dataframe(session)
            scored = compute_value_score(scored_df)
            scored_df["value_score"] = scored.composite.round(2)
            scored_df["xgi_per_90"] = scored.xgi_per_90

            store = build_feature_store(
                players_df=scored_df,
                fixture_map=fixture_map,
                team_name_map=team_name_map,
                gameweek_id=current_gw,
                config_hash=config_hash,
            )

            from services.production_predictor import run_production_predictions
            result = run_production_predictions(
                store=store,
                gameweek_id=current_gw,
                session=session,
                persist=True,
            )
            if result.primary and result.primary.ok:
                print(f"Production predictions ran successfully! {len(result.primary.projections)} projections")
                pv = find_latest_version(session)
            else:
                print(f"Production predictor failed: {result.primary.error if result.primary else 'no primary'}")
                return

        if pv is None:
            print("ERROR: Could not find or create prediction version.")
            return

        print(f"\nUsing PredictionVersion: id={pv.id}, tag={pv.version_tag}, model={pv.model_name}")
        print(f"Created at: {pv.created_at}")

        # 2. Get all projections for this version
        projections = get_projections(session, pv.id)
        print(f"Total projections for this version: {len(projections)}")

        if not projections:
            print("ERROR: No projections found for this version.")
            return

        # Get gameweek IDs in this version
        gameweeks_in_version = sorted({p.gameweek_id for p in projections})
        print(f"Gameweeks covered: {gameweeks_in_version}")

        # Use the latest gameweek in the version
        target_gw = max(gameweeks_in_version)
        gw_projections = [p for p in projections if p.gameweek_id == target_gw]
        print(f"Projections for GW{target_gw}: {len(gw_projections)}")

        # 3. Build projection lookup
        proj_map = {p.player_id: p for p in gw_projections}

        # 4. Load all players
        player_rows = get_player_row_map(session)
        print(f"Total players in DB: {len(player_rows)}")

        # 5. Resolve target players
        print("\n" + "=" * 80)
        print("RESOLVING TARGET PLAYERS")
        print("=" * 80)

        seen_ids = set()
        resolved = []
        for name in TARGET_PLAYERS:
            pid, info = resolve_player(name, player_rows, seen_ids)
            if pid is None:
                print(f"  WARNING: Could not find player '{name}'")
                continue
            proj = proj_map.get(pid)
            if proj is None:
                print(f"  WARNING: No projection for {name} (id={pid})")
                continue
            resolved.append((pid, info, proj))
            print(f"  OK: {info['web_name']} (id={pid}, {info['position']}, {info['team_name']})")

        if not resolved:
            print("ERROR: No players resolved.")
            return

        # 6. Print formatted table
        print("\n" + "=" * 120)
        print(f"V3 xPts PROJECTIONS — GW{target_gw} — Version: {pv.version_tag}")
        print("=" * 120)

        header = (
            f"{'Player':<18} {'Pos':<5} {'Team':<16} {'Price':>7} {'xPts':>7} "
            f"{'xPts/90':>8} {'ExpMin':>7} {'Start%':>7} "
            f"{'CI80Lo':>7} {'CI80Hi':>7} {'Conf':>6} {'Quality':<12} {'RotRisk':<8}"
        )
        print(header)
        print("-" * 120)

        total_rows = []
        for pid, info, proj in resolved:
            minutes_proj = getattr(proj, 'minutes_proj', None) or 0
            start_prob = (minutes_proj / 90.0) * 100 if minutes_proj else 0
            # Clamp to 100
            start_prob = min(start_prob, 100)

            # Get data_quality from the version weights_snapshot if available
            # (confidence and data_quality are computed by the engine but not persisted to the Projection table)
            confidence = getattr(proj, 'confidence', None)
            data_quality = getattr(proj, 'data_quality', None)
            # If these are None/0/unknown (DB-only path), try to extract from version metadata
            if not confidence and pv.weights_snapshot:
                # Not directly available; show what we can from the snapshot
                pass
            if not data_quality or data_quality == 'unknown':
                data_quality = "good" if minutes_proj >= 60 else "limited" if minutes_proj > 0 else "none"
            if not confidence:
                confidence = round(min(100, max(0, minutes_proj / 90 * 80 + 10)), 1) if minutes_proj > 0 else 0
            # Derive rotation_risk from expected_minutes
            if minutes_proj >= 80:
                rotation_risk = "low"
            elif minutes_proj >= 60:
                rotation_risk = "medium"
            elif minutes_proj > 0:
                rotation_risk = "high"
            else:
                rotation_risk = "N/A"

            row = {
                "player_id": pid,
                "web_name": info["web_name"],
                "position": info["position"],
                "team": info["team_name"],
                "price": info["price"],
                "xPts": proj.projected_points,
                "xPts_per_90": getattr(proj, 'xpts_per_90', 0) or (proj.projected_points / (minutes_proj / 90) if minutes_proj > 0 else 0),
                "expected_minutes": minutes_proj,
                "start_prob": start_prob,
                "ci_80_low": proj.ci_80_low or 0,
                "ci_80_high": proj.ci_80_high or 0,
                "confidence": confidence,
                "data_quality": data_quality,
                "rotation_risk": rotation_risk,
            }
            total_rows.append(row)

            print(
                f"{info['web_name']:<18} {info['position']:<5} {info['team_name']:<16} "
                f"£{info['price']:>5.1f} {proj.projected_points:>7.2f} "
                f"{row['xPts_per_90']:>8.2f} {minutes_proj:>7.1f} {start_prob:>6.1f}% "
                f"{proj.ci_80_low or 0:>7.2f} {proj.ci_80_high or 0:>7.2f} "
                f"{confidence:>5.1f} {data_quality:<12} {rotation_risk}"
            )

        # 7. Split into starting XI and bench
        print("\n" + "=" * 80)
        print("STARTING XI vs BENCH SPLIT")
        print("=" * 80)

        # Sort by xPts descending and assign positions greedily
        pos_order = ["GKP", "DEF", "MID", "FWD"]
        sorted_by_xpts = sorted(total_rows, key=lambda r: r["xPts"], reverse=True)

        # Greedy assignment: fill formation slots with best xPts per position
        starters = []
        bench = []
        pos_counts = {p: 0 for p in pos_order}

        # First pass: assign starters
        for row in sorted_by_xpts:
            pos = row["position"]
            if pos_counts[pos] < FORMATION.get(pos, 0):
                starters.append(row)
                pos_counts[pos] += 1
            else:
                bench.append(row)

        # Sort starters by position then xPts
        starters.sort(key=lambda r: (pos_order.index(r["position"]), -r["xPts"]))
        bench.sort(key=lambda r: (pos_order.index(r["position"]), -r["xPts"]))

        starters_xpts = sum(r["xPts"] for r in starters)
        bench_xpts = sum(r["xPts"] for r in bench)
        total_xpts = starters_xpts + bench_xpts

        print("\nStarting XI (GK + 4 DEF + 3 MID + 3 FWD):")
        print(f"{'Player':<18} {'Pos':<5} {'Team':<16} {'Price':>7} {'xPts':>7}")
        print("-" * 60)
        for r in starters:
            print(f"{r['web_name']:<18} {r['position']:<5} {r['team']:<16} £{r['price']:>5.1f} {r['xPts']:>7.2f}")
        print("-" * 60)
        print(f"{'STARTING XI TOTAL':<18} {'':5} {'':16} £{sum(r['price'] for r in starters):>5.1f} {starters_xpts:>7.2f}")

        print("\nBench:")
        print(f"{'Player':<18} {'Pos':<5} {'Team':<16} {'Price':>7} {'xPts':>7}")
        print("-" * 60)
        for r in bench:
            print(f"{r['web_name']:<18} {r['position']:<5} {r['team']:<16} £{r['price']:>5.1f} {r['xPts']:>7.2f}")
        print("-" * 60)
        print(f"{'BENCH TOTAL':<18} {'':5} {'':16} £{sum(r['price'] for r in bench):>5.1f} {bench_xpts:>7.2f}")

        print(f"\n{'SQUAD TOTAL':<18} {'':5} {'':16} £{sum(r['price'] for r in total_rows):>5.1f} {total_xpts:>7.2f}")

        # 8. Full ranking by xPts
        print("\n" + "=" * 80)
        print("ALL 15 PLAYERS RANKED BY xPts (DESCENDING)")
        print("=" * 80)

        print(f"{'Rank':<5} {'Player':<18} {'Pos':<5} {'Team':<16} {'Price':>7} {'xPts':>7} {'xPts/£':>8}")
        print("-" * 75)
        for i, row in enumerate(sorted_by_xpts, 1):
            xpts_per_price = row["xPts"] / row["price"] if row["price"] > 0 else 0
            print(
                f"{i:<5} {row['web_name']:<18} {row['position']:<5} {row['team']:<16} "
                f"£{row['price']:>5.1f} {row['xPts']:>7.2f} {xpts_per_price:>8.2f}"
            )

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"  Gameweek:           GW{target_gw}")
        print(f"  Prediction Version: {pv.version_tag} (id={pv.id})")
        print(f"  Model:              {pv.model_name}")
        print(f"  Created:            {pv.created_at}")
        print(f"  Total Squad Price:  £{sum(r['price'] for r in total_rows):.1f}m")
        print(f"  Starting XI xPts:   {starters_xpts:.2f}")
        print(f"  Bench xPts:         {bench_xpts:.2f}")
        print(f"  Total xPts:         {total_xpts:.2f}")
        print(f"  Best Player:        {sorted_by_xpts[0]['web_name']} ({sorted_by_xpts[0]['xPts']:.2f} xPts)")
        print(f"  Worst Player:       {sorted_by_xpts[-1]['web_name']} ({sorted_by_xpts[-1]['xPts']:.2f} xPts)")
        print("=" * 80)

    finally:
        session.close()


if __name__ == "__main__":
    main()
