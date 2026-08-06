"""Decision Log — Section 6 of the Assistant Manager.

Stores recommendations, tracks actual outcomes, and computes accuracy metrics
over time.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from database.models import ChipState, DecisionLog


def log_recommendation(
    session: Session,
    team_id: int,
    gameweek: int,
    recommendation_type: str,
    recommendation: dict,
    confidence: float | None = None,
    predicted_points: float | None = None,
) -> DecisionLog:
    """Store a recommendation in the decision log."""
    entry = DecisionLog(
        team_id=team_id,
        gameweek_id=gameweek,
        recommendation_type=recommendation_type,
        recommendation_json=json.dumps(recommendation, default=str),
        confidence_rating=confidence,
        predicted_points=predicted_points,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def record_actual_action(
    session: Session,
    decision_id: int,
    action_taken: str,
    action_json: dict | None = None,
) -> None:
    """Record what the user actually did for a recommendation."""
    entry = session.get(DecisionLog, decision_id)
    if entry:
        entry.action_taken = action_taken
        if action_json:
            entry.action_json = json.dumps(action_json, default=str)
        session.commit()


def update_outcome(
    session: Session,
    decision_id: int,
    actual_points: float,
    was_accurate: bool | None = None,
) -> None:
    """Update the outcome of a decision after a gameweek finishes."""
    entry = session.get(DecisionLog, decision_id)
    if entry:
        entry.actual_points = actual_points
        if was_accurate is None and entry.predicted_points is not None:
            entry.was_accurate = actual_points >= entry.predicted_points * 0.7
        elif was_accurate is not None:
            entry.was_accurate = was_accurate
        session.commit()


def get_decision_history(
    session: Session,
    team_id: int,
    gameweek: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Retrieve decision history."""
    query = session.query(DecisionLog).filter_by(team_id=team_id)
    if gameweek is not None:
        query = query.filter_by(gameweek_id=gameweek)
    entries = query.order_by(DecisionLog.gameweek_id.desc()).limit(limit).all()

    return [
        {
            "id": e.id,
            "gameweek": e.gameweek_id,
            "type": e.recommendation_type,
            "recommendation": json.loads(e.recommendation_json) if e.recommendation_json else {},
            "action_taken": e.action_taken,
            "predicted_points": e.predicted_points,
            "actual_points": e.actual_points,
            "was_accurate": e.was_accurate,
            "confidence": e.confidence_rating,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


def compute_accuracy_metrics(session: Session, team_id: int) -> dict:
    """Compute aggregate accuracy metrics."""
    entries = (
        session.query(DecisionLog)
        .filter_by(team_id=team_id)
        .filter(DecisionLog.actual_points.isnot(None))
        .all()
    )

    if not entries:
        return {
            "total_decisions": 0,
            "accuracy_rate": 0.0,
            "avg_predicted_points": 0.0,
            "avg_actual_points": 0.0,
            "avg_points_delta": 0.0,
            "best_decision": None,
            "worst_decision": None,
        }

    total = len(entries)
    accurate = sum(1 for e in entries if e.was_accurate)
    avg_predicted = sum(e.predicted_points or 0 for e in entries) / total
    avg_actual = sum(e.actual_points or 0 for e in entries) / total
    avg_delta = avg_actual - avg_predicted

    # Find best and worst
    sorted_entries = sorted(entries, key=lambda e: (e.actual_points or 0) - (e.predicted_points or 0), reverse=True)
    best = sorted_entries[0] if sorted_entries else None
    worst = sorted_entries[-1] if sorted_entries else None

    return {
        "total_decisions": total,
        "accuracy_rate": round(accurate / total * 100, 1) if total > 0 else 0,
        "avg_predicted_points": round(avg_predicted, 1),
        "avg_actual_points": round(avg_actual, 1),
        "avg_points_delta": round(avg_delta, 1),
        "best_decision": {
            "type": best.recommendation_type,
            "predicted": best.predicted_points,
            "actual": best.actual_points,
            "gameweek": best.gameweek_id,
        } if best else None,
        "worst_decision": {
            "type": worst.recommendation_type,
            "predicted": worst.predicted_points,
            "actual": worst.actual_points,
            "gameweek": worst.gameweek_id,
        } if worst else None,
    }


def get_chip_states(session: Session, team_id: int) -> dict[str, dict]:
    """Get the current state of all chips."""
    states = session.query(ChipState).filter_by(team_id=team_id).all()
    result = {}
    for s in states:
        result[s.chip_name] = {
            "used": s.used,
            "used_in_gameweek": s.used_in_gameweek,
        }
    return result


def sync_chip_states(session: Session, team_id: int, chips_from_api: list[dict]) -> dict[str, dict]:
    """Sync chip states from the FPL API history response."""
    for chip_data in chips_from_api:
        chip_name = chip_data.get("chip_name", "")
        if not chip_name:
            continue

        state = (
            session.query(ChipState)
            .filter_by(team_id=team_id, chip_name=chip_name)
            .first()
        )
        if state is None:
            state = ChipState(team_id=team_id, chip_name=chip_name)
            session.add(state)

        if chip_data.get("num_played", 0) > 0:
            state.used = True
            state.used_in_gameweek = chip_data.get("chip_played_in_event")

    session.commit()
    return get_chip_states(session, team_id)
