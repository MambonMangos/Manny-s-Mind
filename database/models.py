"""SQLAlchemy ORM models for Moneyball FPL.

Stores every field from bootstrap-static.json to future-proof the schema.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""



class Team(Base):
    """FPL team / club."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String, nullable=False)
    short_name = Column(String, nullable=False)
    strength_overall_home = Column(Integer, default=0)
    strength_overall_away = Column(Integer, default=0)
    strength_attack_home = Column(Integer, default=0)
    strength_attack_away = Column(Integer, default=0)
    strength_defence_home = Column(Integer, default=0)
    strength_defence_away = Column(Integer, default=0)
    pulse_id = Column(Integer, nullable=True)

    # relationships
    players = relationship("Player", back_populates="team", lazy="dynamic")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Team(id={self.id}, name={self.name!r})>"


class Player(Base):
    """FPL player – mirrors the full element object from bootstrap-static."""

    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=False)
    first_name = Column(String, nullable=True)
    second_name = Column(String, nullable=True)
    web_name = Column(String, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    element_type = Column(Integer, nullable=False)  # 1=GKP, 2=DEF, 3=MID, 4=FWD

    # cost
    now_cost = Column(Integer, default=0)  # price × 10
    cost_change_start = Column(Integer, default=0)
    cost_change_event = Column(Integer, default=0)
    cost_change_start_fall = Column(Integer, default=0)
    cost_change_event_fall = Column(Integer, default=0)
    value_form = Column(Float, default=0.0)
    value_season = Column(Float, default=0.0)

    # performance
    minutes = Column(Integer, default=0)
    goals_scored = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    clean_sheets = Column(Integer, default=0)
    goals_conceded = Column(Integer, default=0)
    own_goals = Column(Integer, default=0)
    penalties_saved = Column(Integer, default=0)
    penalties_missed = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    bonus = Column(Integer, default=0)
    bps = Column(Integer, default=0)
    influence = Column(Float, default=0.0)
    creativity = Column(Float, default=0.0)
    threat = Column(Float, default=0.0)
    ict_index = Column(Float, default=0.0)
    expected_goals = Column(Float, default=0.0)
    expected_assists = Column(Float, default=0.0)
    expected_goal_involvements = Column(Float, default=0.0)
    expected_goals_conceded = Column(Float, default=0.0)

    # overall points
    total_points = Column(Integer, default=0)
    event_points = Column(Integer, default=0)

    # form / ownership
    form = Column(Float, default=0.0)
    selected_by_percent = Column(Float, default=0.0)
    transfers_in_event = Column(Integer, default=0)
    transfers_out_event = Column(Integer, default=0)
    transfers_in = Column(Integer, default=0)
    transfers_out = Column(Integer, default=0)

    # status
    status = Column(String, default="a")  # a=doubtful, i=injured, etc.
    news = Column(String, default="")
    chance_of_playing_next_round = Column(Integer, nullable=True)
    chance_of_playing_this_round = Column(Integer, nullable=True)
    news_added = Column(String, nullable=True)

    # set pieces
    penalties_order = Column(Integer, nullable=True)
    direct_freekicks_order = Column(Integer, nullable=True)
    corners_and_indirect_freekicks_order = Column(Integer, nullable=True)

    # extra metadata
    is_locked = Column(Boolean, default=False)
    element_type_str = Column(String, nullable=True)

    # relationships
    team = relationship("Team", back_populates="players")
    gameweek_stats = relationship(
        "PlayerGameweekStat", back_populates="player", lazy="dynamic"
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<Player(id={self.id}, web_name={self.web_name!r}, "
            f"team_id={self.team_id})>"
        )


class Gameweek(Base):
    """Gameweek (event) metadata."""

    __tablename__ = "gameweeks"

    id = Column(Integer, primary_key=True, autoincrement=False)
    name = Column(String, nullable=False)
    deadline_time = Column(String, nullable=True)
    deadline_time_epoch = Column(Integer, nullable=True)
    deadline_time_game_offset = Column(Integer, default=0)
    finished = Column(Boolean, default=False)
    data_checked = Column(Boolean, default=False)
    is_previous = Column(Boolean, default=False)
    is_current = Column(Boolean, default=False)
    is_next = Column(Boolean, default=False)
    most_captained = Column(Integer, nullable=True)
    most_vice_captained = Column(Integer, nullable=True)
    transferred_in = Column(Integer, nullable=True)
    highest_score = Column(Integer, nullable=True)
    chip_plays = Column(String, nullable=True)  # JSON array

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Gameweek(id={self.id}, name={self.name!r})>"


class PlayerGameweekStat(Base):
    """Per-gameweek history for a player – future-proof for weekly snapshots."""

    __tablename__ = "player_gameweek_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False)
    opponent_team = Column(Integer, nullable=True)
    was_home = Column(Boolean, nullable=True)
    minutes = Column(Integer, default=0)
    goals_scored = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    clean_sheets = Column(Integer, default=0)
    goals_conceded = Column(Integer, default=0)
    own_goals = Column(Integer, default=0)
    penalties_saved = Column(Integer, default=0)
    penalties_missed = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    bonus = Column(Integer, default=0)
    bps = Column(Integer, default=0)
    influence = Column(Float, default=0.0)
    creativity = Column(Float, default=0.0)
    threat = Column(Float, default=0.0)
    ict_index = Column(Float, default=0.0)
    total_points = Column(Integer, default=0)
    expected_goals = Column(Float, default=0.0)
    expected_assists = Column(Float, default=0.0)
    expected_goal_involvements = Column(Float, default=0.0)
    expected_goals_conceded = Column(Float, default=0.0)
    value = Column(Float, default=0.0)
    selected = Column(Float, default=0.0)
    transfers_in = Column(Integer, default=0)
    transfers_out = Column(Integer, default=0)

    # relationships
    player = relationship("Player", back_populates="gameweek_stats")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<PlayerGameweekStat(player_id={self.player_id}, "
            f"gw={self.gameweek_id})>"
        )


class PriceHistory(Base):
    """Historical daily price data – future-proof for price tracking."""

    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    date = Column(String, nullable=False)  # e.g. "2025-08-15"
    price = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PriceHistory(player_id={self.player_id}, date={self.date!r})>"


class Snapshot(Base):
    """Weekly snapshot of the entire player pool – future-proof for trend analysis."""

    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False)
    snapshot_json = Column(String, nullable=False)  # JSON blob
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Snapshot(gw={self.gameweek_id})>"


class DecisionLog(Base):
    """Stores every recommendation the Assistant Manager makes and its outcome."""

    __tablename__ = "decision_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, index=True)
    gameweek_id = Column(Integer, nullable=False, index=True)
    recommendation_type = Column(String, nullable=False)  # transfer, chip, hold, captain
    recommendation_json = Column(String, nullable=False)  # JSON blob of the full recommendation
    action_taken = Column(String, nullable=True)  # what the user actually did
    action_json = Column(String, nullable=True)  # JSON blob of actual action
    predicted_points = Column(Float, nullable=True)
    actual_points = Column(Float, nullable=True)
    was_accurate = Column(Boolean, nullable=True)  # filled in after GW finishes
    confidence_rating = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<DecisionLog(gw={self.gameweek_id}, type={self.recommendation_type!r}, "
            f"accurate={self.was_accurate})>"
        )


class AuditLog(Base):
    """Append-only operational audit trail of mutating actions.

    Records who did what (result ingestion, validation cycles, data
    refreshes, persist-to-ledger comparisons). Never updated or deleted.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String, nullable=False, index=True)  # e.g. "ingest_results"
    actor = Column(String, nullable=True)  # e.g. "team:472930"
    resource = Column(String, nullable=True)  # e.g. "gameweek:5"
    detail = Column(JSON, nullable=True)  # event-specific payload
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(action={self.action!r}, actor={self.actor!r})>"


class ChipState(Base):
    """Tracks chip availability and usage for the user's team."""

    __tablename__ = "chip_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False, index=True)
    chip_name = Column(String, nullable=False)  # wildcard, free_hit, bboost, 3xc
    used = Column(Boolean, default=False)
    used_in_gameweek = Column(Integer, nullable=True)
    recommended_in_gameweek = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<ChipState(team={self.team_id}, chip={self.chip_name!r}, "
            f"used={self.used})>"
        )


class PlayerSnapshot(Base):
    """Frozen record of a player's state at a specific gameweek.

    Every engine writes to this table on each snapshot cycle. Enables
    point-in-time queries, time-series analysis, and rollback.
    """

    __tablename__ = "player_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False, index=True)
    snapshot_type = Column(String, nullable=False, default="pre")  # pre or post

    # Core stats (mirrors Player model for point-in-time capture)
    now_cost = Column(Integer, default=0)
    total_points = Column(Integer, default=0)
    minutes = Column(Integer, default=0)
    goals_scored = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    clean_sheets = Column(Integer, default=0)
    goals_conceded = Column(Integer, default=0)
    expected_goals = Column(Float, default=0.0)
    expected_assists = Column(Float, default=0.0)
    expected_goal_involvements = Column(Float, default=0.0)
    expected_goals_conceded = Column(Float, default=0.0)
    form = Column(Float, default=0.0)
    selected_by_percent = Column(Float, default=0.0)
    influence = Column(Float, default=0.0)
    creativity = Column(Float, default=0.0)
    threat = Column(Float, default=0.0)
    ict_index = Column(Float, default=0.0)
    status = Column(String, default="a")
    news = Column(String, default="")
    chance_of_playing_next_round = Column(Integer, nullable=True)
    chance_of_playing_this_round = Column(Integer, nullable=True)
    transfers_in_event = Column(Integer, default=0)
    transfers_out_event = Column(Integer, default=0)

    # Derived scores (computed by engines at snapshot time)
    xgi_per_90 = Column(Float, default=0.0)
    minutes_fraction = Column(Float, default=0.0)
    team_strength_raw = Column(Float, default=100.0)
    fixture_score_raw = Column(Float, default=50.0)
    set_piece_raw = Column(Float, default=0.0)

    # Full snapshot as JSON for forward-compat
    snapshot_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player")

    def __repr__(self) -> str:
        return (
            f"<PlayerSnapshot(player_id={self.player_id}, "
            f"gw={self.gameweek_id}, type={self.snapshot_type!r})>"
        )


class PredictionVersion(Base):
    """Tracks every projection run: model version, config, features, metrics.

    Each row is one forecast. Projections are appended, never overwritten.
    """

    __tablename__ = "prediction_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_tag = Column(String, nullable=False, unique=True)  # e.g. "v2.1.0-gw3"
    model_name = Column(String, nullable=False)  # e.g. "projection_v2"
    config_hash = Column(String, nullable=True)  # SHA-256 of weights YAML
    features_used = Column(JSON, nullable=True)  # list of feature column names
    weights_snapshot = Column(JSON, nullable=True)  # copy of weights used

    # Quality metrics
    mae = Column(Float, nullable=True)  # mean absolute error
    rmse = Column(Float, nullable=True)  # root mean squared error
    coverage_80 = Column(Float, nullable=True)  # actual in 80% CI %
    coverage_95 = Column(Float, nullable=True)  # actual in 95% CI %

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    projections = relationship("Projection", back_populates="version")

    def __repr__(self) -> str:
        return f"<PredictionVersion(tag={self.version_tag!r}, mae={self.mae})>"


class Projection(Base):
    """One projected points line per player per gameweek per version.

    This is the core output of the prediction engine. Always append, never update.
    """

    __tablename__ = "projections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("prediction_versions.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False, index=True)

    projected_points = Column(Float, nullable=False)
    ci_80_low = Column(Float, nullable=True)
    ci_80_high = Column(Float, nullable=True)
    ci_95_low = Column(Float, nullable=True)
    ci_95_high = Column(Float, nullable=True)

    # Component breakdown
    minutes_proj = Column(Float, nullable=True)
    goals_proj = Column(Float, nullable=True)
    assists_proj = Column(Float, nullable=True)
    clean_sheet_proj = Column(Float, nullable=True)
    bonus_proj = Column(Float, nullable=True)
    other_proj = Column(Float, nullable=True)

    # Actuals (filled in after GW finishes)
    actual_points = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    version = relationship("PredictionVersion", back_populates="projections")
    player = relationship("Player")

    def __repr__(self) -> str:
        return (
            f"<Projection(player_id={self.player_id}, gw={self.gameweek_id}, "
            f"pts={self.projected_points}, ci=[{self.ci_80_low},{self.ci_80_high}])>"
        )


class ExperimentRun(Base):
    """Tracks one experiment: config, changes made, results vs. baseline.

    Enables A/B comparison between model versions.
    """

    __tablename__ = "experiment_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_name = Column(String, nullable=False)
    experiment_type = Column(String, nullable=False)  # "new_weights", "new_feature", "ab_test"
    baseline_version = Column(String, nullable=True)  # version_tag of baseline
    treatment_version = Column(String, nullable=True)  # version_tag of treatment

    # Config diff
    config_diff = Column(JSON, nullable=True)  # what changed vs. baseline

    # Results
    baseline_mae = Column(Float, nullable=True)
    treatment_mae = Column(Float, nullable=True)
    improvement_pct = Column(Float, nullable=True)

    status = Column(String, default="pending")  # pending, running, completed, failed
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ExperimentRun(name={self.run_name!r}, "
            f"status={self.status!r}, improvement={self.improvement_pct})>"
        )


# ------------------------------------------------------------------
# Validation Platform Models
# ------------------------------------------------------------------

class ValidationMetrics(Base):
    """Computed accuracy metrics for a prediction version against a gameweek.

    Written by the Validation Engine after actuals are attached.
    One row per (version_id, gameweek_id).
    """

    __tablename__ = "validation_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("prediction_versions.id"), nullable=False, index=True)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False, index=True)

    # Overall metrics
    mae = Column(Float, nullable=True)
    rmse = Column(Float, nullable=True)
    bias = Column(Float, nullable=True)  # mean(actual - projected), positive = underpredicted
    median_ae = Column(Float, nullable=True)

    # Confidence interval calibration
    coverage_80 = Column(Float, nullable=True)
    coverage_95 = Column(Float, nullable=True)
    ci_width_avg = Column(Float, nullable=True)

    # Per-position breakdown (JSON dict: {"GKP": 3.2, "DEF": 4.1, ...})
    mae_by_position = Column(JSON, nullable=True)
    rmse_by_position = Column(JSON, nullable=True)
    n_by_position = Column(JSON, nullable=True)

    # Top/bottom players
    best_predicted_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    worst_predicted_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    worst_error = Column(Float, nullable=True)

    # Metadata
    n_projections = Column(Integer, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow)

    version = relationship("PredictionVersion")

    def __repr__(self) -> str:
        return (
            f"<ValidationMetrics(version_id={self.version_id}, "
            f"gw={self.gameweek_id}, mae={self.mae})>"
        )


class ErrorClassification(Base):
    """Rule-based classification of prediction errors.

    One row per mispredicted player per version per GW.
    Categorizes WHY the prediction was wrong.
    """

    __tablename__ = "error_classifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("prediction_versions.id"), nullable=False, index=True)
    projection_id = Column(Integer, ForeignKey("projections.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False, index=True)

    # Error measurement
    error = Column(Float, nullable=False)  # actual - projected
    abs_error = Column(Float, nullable=False)
    error_direction = Column(String, nullable=False)  # "over" or "under"

    # Classification categories (rule-based, not ML)
    error_type = Column(String, nullable=False)  # e.g. "minutes_miss", "outlier_performance", "fixture_mismatch"
    error_severity = Column(String, nullable=False)  # "minor", "moderate", "severe"
    root_cause = Column(String, nullable=True)  # e.g. "unexpected_rotation", "red_card", "hat_trick"

    # Context
    predicted_minutes = Column(Float, nullable=True)
    actual_minutes = Column(Float, nullable=True)
    predicted_goals = Column(Float, nullable=True)
    actual_goals = Column(Integer, nullable=True)
    predicted_assists = Column(Float, nullable=True)
    actual_assists = Column(Integer, nullable=True)

    # Metadata
    classified_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<ErrorClassification(player_id={self.player_id}, "
            f"type={self.error_type!r}, severity={self.error_severity!r})>"
        )


class RecommendationOutcome(Base):
    """Tracks the actual outcome of a recommendation from the Assistant Manager.

    One row per recommendation per GW. Compared against DecisionLog to
    measure recommendation accuracy.
    """

    __tablename__ = "recommendation_outcomes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_log_id = Column(Integer, ForeignKey("decision_log.id"), nullable=False, index=True)
    version_id = Column(Integer, ForeignKey("prediction_versions.id"), nullable=False, index=True)
    team_id = Column(Integer, nullable=False)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False, index=True)
    recommendation_type = Column(String, nullable=False)  # transfer, chip, captain, hold

    # What we predicted
    predicted_value = Column(Float, nullable=True)  # projected points gain
    confidence = Column(Float, nullable=True)

    # What actually happened
    actual_value = Column(Float, nullable=True)  # actual points gained
    was_correct = Column(Boolean, nullable=True)

    # For transfers: which players were involved
    player_out_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    player_in_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    player_out_actual_pts = Column(Float, nullable=True)
    player_in_actual_pts = Column(Float, nullable=True)

    # Decision
    was_acted_on = Column(Boolean, nullable=True)  # did the user follow the recommendation?

    computed_at = Column(DateTime, default=datetime.utcnow)

    decision_log = relationship("DecisionLog")
    version = relationship("PredictionVersion")

    def __repr__(self) -> str:
        return (
            f"<RecommendationOutcome(type={self.recommendation_type!r}, "
            f"gw={self.gameweek_id}, correct={self.was_correct})>"
        )


class EngineAccuracy(Base):
    """Per-engine accuracy metrics per version per GW.

    Tracks which analytical engines contribute most to prediction quality.
    Enables engine-level scoring and feature importance analysis.
    """

    __tablename__ = "engine_accuracy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("prediction_versions.id"), nullable=False, index=True)
    gameweek_id = Column(Integer, ForeignKey("gameweeks.id"), nullable=False, index=True)

    # Engine identifiers
    engine_name = Column(String, nullable=False)  # e.g. "projection_v2", "minutes_engine", "fixture_engine"
    engine_version = Column(String, nullable=True)

    # Contribution metrics (how much did this engine's output correlate with accuracy?)
    mae = Column(Float, nullable=True)
    correlation = Column(Float, nullable=True)  # correlation between engine output and actual points
    contribution_score = Column(Float, nullable=True)  # 0-1, how much this engine contributed

    # Feature-level accuracy
    feature_importance = Column(JSON, nullable=True)  # {"xgi_per_90": 0.42, "fixture_score": 0.28, ...}

    # Metadata
    n_samples = Column(Integer, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow)

    version = relationship("PredictionVersion")

    def __repr__(self) -> str:
        return (
            f"<EngineAccuracy(engine={self.engine_name!r}, "
            f"gw={self.gameweek_id}, mae={self.mae})>"
        )
