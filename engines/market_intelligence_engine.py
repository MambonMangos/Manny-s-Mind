"""Market Intelligence Engine — analyzes transfer activity, price changes, ownership trends.

Owns:
  - Transfer velocity analysis
  - Price change prediction
  - Ownership momentum tracking
  - Differential/template classification

Reads from: FeatureStore
Config: config/features/features_v1.yaml (market section)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class MarketSignal:
    """Market analysis for a single player."""

    player_id: int
    web_name: str
    position: str

    # Transfer activity
    net_transfers: int
    transfer_velocity: float  # net transfers as % of owners
    transfer_direction: str  # "buying", "selling", "stable"

    # Ownership
    selected_by_percent: float
    ownership_tier: str  # "differential" (<5%), "mid" (5-20%), "template" (>20%)

    # Price
    price_direction: str  # "rising", "stable", "falling"
    price_change_event: float
    price_change_start: float

    # Market sentiment
    market_sentiment: str  # "hot", "warm", "cold"
    sentiment_score: float  # -1 to 1

    # Investment signal
    investment_signal: str  # "buy", "hold", "sell"
    signal_confidence: float  # 0-100


def compute_market_signals(
    store,
) -> list[MarketSignal]:
    """Analyze market dynamics for all players.

    Returns a list of MarketSignal, one per player.
    """
    cfg = load_config("features")
    market_cfg = cfg.get("market", {})
    market_cfg.get("velocity_window", 3)

    df = store.df
    signals = []

    for _, row in df.iterrows():
        signal = _analyze_player_market(row, market_cfg)
        signals.append(signal)

    return signals


def get_market_summary(
    signals: list[MarketSignal],
) -> dict:
    """Summarize market landscape."""
    hot_buys = [s for s in signals if s.investment_signal == "buy" and s.signal_confidence > 60]
    hot_sells = [s for s in signals if s.investment_signal == "sell" and s.signal_confidence > 60]
    differentials = [s for s in signals if s.ownership_tier == "differential"]

    return {
        "total_players": len(signals),
        "hot_buys": len(hot_buys),
        "hot_sells": len(hot_sells),
        "differentails": len(differentials),
        "top_buys": sorted(hot_buys, key=lambda s: s.signal_confidence, reverse=True)[:10],
        "top_sells": sorted(hot_sells, key=lambda s: s.signal_confidence, reverse=True)[:10],
        "biggest_differentials": sorted(
            differentials, key=lambda s: s.transfer_velocity, reverse=True,
        )[:10],
    }


def identify_differentials(
    signals: list[MarketSignal],
    min_sentiment: float = 0.3,
) -> list[MarketSignal]:
    """Find low-ownership players with positive market momentum."""
    return [
        s for s in signals
        if s.ownership_tier == "differential"
        and s.sentiment_score >= min_sentiment
        and s.transfer_direction in ("buying", "stable")
    ]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _analyze_player_market(
    row: pd.Series,
    market_cfg: dict,
) -> MarketSignal:
    """Analyze market dynamics for a single player."""
    player_id = int(row.get("player_id", 0))
    web_name = str(row.get("web_name", ""))
    position = str(row.get("position", ""))

    # Read canonical market features from Feature Store (SSOT)
    net_transfers = int(row.get("net_transfers", 0))
    transfer_velocity = float(row.get("transfer_velocity", 0.0))
    ownership_tier = str(row.get("ownership_tier", "mid"))

    selected = float(row.get("selected_by_percent", 0) or 0)

    # Transfer direction
    if transfer_velocity > 0.1:
        transfer_direction = "buying"
    elif transfer_velocity < -0.1:
        transfer_direction = "selling"
    else:
        transfer_direction = "stable"

    # Read canonical price direction from Feature Store (SSOT)
    price_direction = str(row.get("price_direction_label", "stable"))
    cost_change_event = float(row.get("cost_change_event", 0) or 0)
    cost_change_start = float(row.get("cost_change_start", 0) or 0)

    # Market sentiment (composite)
    sentiment_score = _compute_sentiment(
        transfer_velocity=transfer_velocity,
        selected=selected,
        price_direction=price_direction,
        cost_change_start=cost_change_start,
    )

    if sentiment_score > 0.3:
        market_sentiment = "hot"
    elif sentiment_score > -0.3:
        market_sentiment = "warm"
    else:
        market_sentiment = "cold"

    # Investment signal
    investment_signal, signal_confidence = _compute_investment_signal(
        transfer_velocity=transfer_velocity,
        sentiment_score=sentiment_score,
        price_direction=price_direction,
        ownership_tier=ownership_tier,
        selected=selected,
    )

    return MarketSignal(
        player_id=player_id,
        web_name=web_name,
        position=position,
        net_transfers=net_transfers,
        transfer_velocity=round(transfer_velocity, 4),
        transfer_direction=transfer_direction,
        selected_by_percent=selected,
        ownership_tier=ownership_tier,
        price_direction=price_direction,
        price_change_event=cost_change_event,
        price_change_start=cost_change_start,
        market_sentiment=market_sentiment,
        sentiment_score=round(sentiment_score, 3),
        investment_signal=investment_signal,
        signal_confidence=round(signal_confidence, 1),
    )


def _compute_sentiment(
    transfer_velocity: float,
    selected: float,
    price_direction: str,
    cost_change_start: float,
) -> float:
    """Compute market sentiment score (-1 to 1)."""
    score = 0.0

    # Transfer momentum
    score += np.clip(transfer_velocity * 10, -0.4, 0.4)

    # Price momentum
    if price_direction == "rising":
        score += 0.2
    elif price_direction == "falling":
        score -= 0.2

    # Price change magnitude
    score += np.clip(cost_change_start / 10, -0.2, 0.2)

    # Ownership effect: high ownership = more consensus
    if selected > 20:
        score += 0.1  # template consensus

    return np.clip(score, -1.0, 1.0)


def _compute_investment_signal(
    transfer_velocity: float,
    sentiment_score: float,
    price_direction: str,
    ownership_tier: str,
    selected: float,
) -> tuple[str, float]:
    """Compute investment signal and confidence."""
    score = 0.0

    # Strong buying momentum
    if transfer_velocity > 0.5:
        score += 30
    elif transfer_velocity > 0.1:
        score += 15
    elif transfer_velocity < -0.5:
        score -= 30
    elif transfer_velocity < -0.1:
        score -= 15

    # Sentiment alignment
    score += sentiment_score * 20

    # Price momentum
    if price_direction == "rising":
        score += 10
    elif price_direction == "falling":
        score -= 10

    # Differential bonus: low ownership + positive momentum = opportunity
    if ownership_tier == "differential" and sentiment_score > 0:
        score += 15

    # Determine signal
    if score > 20:
        signal = "buy"
    elif score < -20:
        signal = "sell"
    else:
        signal = "hold"

    confidence = min(abs(score) + 30, 95)

    return signal, confidence
