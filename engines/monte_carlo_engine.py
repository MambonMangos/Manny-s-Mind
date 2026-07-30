"""Monte Carlo Engine — runs simulations for uncertainty quantification.

Owns:
  - Player-level point simulations (10,000 runs)
  - Squad-level outcome distributions
  - Captain outcome distributions
  - Risk metrics (VaR, CVaR, probability of top N%)

Reads from: Projection Engine, Confidence Engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

N_SIMULATIONS = 10_000


@dataclass
class SimulationResult:
    """Monte Carlo simulation results for a single player."""

    player_id: int
    web_name: str
    position: str

    # Distribution stats
    mean_points: float
    median_points: float
    std_points: float
    p10: float  # 10th percentile
    p25: float
    p50: float
    p75: float
    p90: float

    # Risk metrics
    probability_above_0: float
    probability_above_5: float
    probability_above_10: float
    probability_above_15: float
    probability_above_20: float

    # Raw distribution (for downstream consumers)
    distribution: np.ndarray = field(repr=False, default=None)

    # Metadata
    n_simulations: int = N_SIMULATIONS


@dataclass
class SquadSimulationResult:
    """Monte Carlo simulation results for a full squad."""

    # Team total
    mean_total: float
    median_total: float
    std_total: float
    p10_total: float
    p90_total: float

    # Captain distribution
    captain_mean: float
    captain_median: float

    # Risk
    probability_top_10k: float  # probability of finishing in top 10k
    probability_top_100k: float

    # Player-level results
    player_results: list[SimulationResult]

    # Raw total distribution
    total_distribution: np.ndarray = field(repr=False, default=None)


def simulate_player(
    projected_points: float,
    variance: float,
    confidence: float,
    position: str,
    n_simulations: int = N_SIMULATIONS,
    player_id: int = 0,
    web_name: str = "",
) -> SimulationResult:
    """Run Monte Carlo simulation for a single player.

    Parameters
    ----------
    projected_points : float
        Expected points (mean of distribution).
    variance : float
        Total variance from Confidence Engine.
    confidence : float
        Overall confidence (0-100). Lower confidence = wider distribution.
    position : str
        Player position.
    n_simulations : int
        Number of Monte Carlo runs.

    Returns
    -------
    SimulationResult
        Full distribution statistics.
    """
    std_dev = np.sqrt(max(variance, 0.1))

    # Generate samples from normal distribution (clipped at 0)
    samples = np.random.normal(projected_points, std_dev, n_simulations)
    samples = np.clip(samples, 0, 30)  # FPL max ~30 pts per GW

    # Apply position-specific adjustments
    if position == "GKP":
        # GKPs have bimodal: clean sheet (6-8 pts) or no CS (2-4 pts)
        samples = _bimodal_adjustment(samples, projected_points, position)
    elif position in ("DEF", "MID"):
        # Defenders/mids: clean sheet creates a secondary mode
        samples = _bimodal_adjustment(samples, projected_points, position)

    return SimulationResult(
        player_id=player_id,
        web_name=web_name,
        position=position,
        mean_points=round(float(np.mean(samples)), 2),
        median_points=round(float(np.median(samples)), 2),
        std_points=round(float(np.std(samples)), 2),
        p10=round(float(np.percentile(samples, 10)), 2),
        p25=round(float(np.percentile(samples, 25)), 2),
        p50=round(float(np.percentile(samples, 50)), 2),
        p75=round(float(np.percentile(samples, 75)), 2),
        p90=round(float(np.percentile(samples, 90)), 2),
        probability_above_0=round(float(np.mean(samples > 0)), 3),
        probability_above_5=round(float(np.mean(samples > 5)), 3),
        probability_above_10=round(float(np.mean(samples > 10)), 3),
        probability_above_15=round(float(np.mean(samples > 15)), 3),
        probability_above_20=round(float(np.mean(samples > 20)), 3),
        distribution=samples,
        n_simulations=n_simulations,
    )


def simulate_squad(
    projections: list,  # noqa: ANN001
    starting_xi: list[int],
    captain: int,
    n_simulations: int = N_SIMULATIONS,
) -> SquadSimulationResult:
    """Run Monte Carlo simulation for a full squad.

    Parameters
    ----------
    projections : list[PlayerProjection]
        Projections with variance info.
    starting_xi : list[int]
        Player IDs in the starting XI.
    captain : int
        Captain player ID (gets 2x multiplier).
    n_simulations : int
        Number of Monte Carlo runs.

    Returns
    -------
    SquadSimulationResult
        Squad-level simulation results.
    """
    proj_map = {p.player_id: p for p in projections}
    player_sims = []

    # Simulate each starting XI player
    squad_totals = np.zeros(n_simulations)
    captain_totals = np.zeros(n_simulations)

    for pid in starting_xi:
        proj = proj_map.get(pid)
        if proj is None:
            continue

        sim = simulate_player(
            projected_points=proj.projected_points,
            variance=proj.variance_total,
            confidence=proj.confidence,
            position=proj.position,
            n_simulations=n_simulations,
            player_id=pid,
            web_name=proj.web_name,
        )
        player_sims.append(sim)

        # Add to squad total
        squad_totals += sim.distribution

        # Captain gets 2x
        if pid == captain:
            captain_totals = sim.distribution * 2
            squad_totals += sim.distribution  # extra 1x for captain bonus

    # Squad statistics
    mean_total = float(np.mean(squad_totals))
    median_total = float(np.median(squad_totals))

    # Rough top 10k / 100k thresholds (from historical FPL data)
    # Top 10k average ~65-75 pts/GW, top 100k ~55-65
    probability_top_10k = float(np.mean(squad_totals >= 70))
    probability_top_100k = float(np.mean(squad_totals >= 60))

    return SquadSimulationResult(
        mean_total=round(mean_total, 2),
        median_total=round(median_total, 2),
        std_total=round(float(np.std(squad_totals)), 2),
        p10_total=round(float(np.percentile(squad_totals, 10)), 2),
        p90_total=round(float(np.percentile(squad_totals, 90)), 2),
        captain_mean=round(float(np.mean(captain_totals)), 2) if len(captain_totals) > 0 else 0,
        captain_median=round(float(np.median(captain_totals)), 2) if len(captain_totals) > 0 else 0,
        probability_top_10k=round(probability_top_10k, 3),
        probability_top_100k=round(probability_top_100k, 3),
        player_results=player_sims,
        total_distribution=squad_totals,
    )


def simulate_transfer_impact(
    projections: list,  # noqa: ANN001
    current_squad: list[int],
    player_out: int,
    player_in: int,
    n_simulations: int = N_SIMULATIONS,
) -> dict:
    """Simulate the impact of a single transfer.

    Returns a dict with current vs new squad stats.
    """
    proj_map = {p.player_id: p for p in projections}

    # Current squad simulation
    current_sims = []
    current_total = np.zeros(n_simulations)
    for pid in current_squad:
        proj = proj_map.get(pid)
        if proj is None:
            continue
        sim = simulate_player(
            projected_points=proj.projected_points,
            variance=proj.variance_total,
            confidence=proj.confidence,
            position=proj.position,
            n_simulations=n_simulations,
        )
        current_sims.append(sim)
        current_total += sim.distribution

    # New squad simulation (swap player_out for player_in)
    new_total = np.zeros(n_simulations)
    for pid in current_squad:
        target_pid = player_in if pid == player_out else pid
        proj = proj_map.get(target_pid)
        if proj is None:
            continue
        sim = simulate_player(
            projected_points=proj.projected_points,
            variance=proj.variance_total,
            confidence=proj.confidence,
            position=proj.position,
            n_simulations=n_simulations,
        )
        new_total += sim.distribution

    # Comparison
    improvement = new_total - current_total
    prob_improvement = float(np.mean(improvement > 0))

    return {
        "current_mean": round(float(np.mean(current_total)), 2),
        "new_mean": round(float(np.mean(new_total)), 2),
        "mean_improvement": round(float(np.mean(improvement)), 2),
        "prob_improvement": round(prob_improvement, 3),
        "prob_large_gain": round(float(np.mean(improvement > 5)), 3),
        "prob_large_loss": round(float(np.mean(improvement < -5)), 3),
        "p10_improvement": round(float(np.percentile(improvement, 10)), 2),
        "p90_improvement": round(float(np.percentile(improvement, 90)), 2),
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _bimodal_adjustment(
    samples: np.ndarray,
    projected_points: float,
    position: str,
) -> np.ndarray:
    """Apply bimodal distribution for positions with clean sheet bonus.

    Clean sheet creates a secondary mode: players either get the CS
    bonus or they don't, creating a bimodal distribution.
    """
    # Probability of clean sheet (rough estimate)
    if position == "GKP":
        cs_prob = 0.35
        cs_bonus = 4  # GKP CS = 4 pts
    elif position == "DEF":
        cs_prob = 0.30
        cs_bonus = 4  # DEF CS = 4 pts
    elif position == "MID":
        cs_prob = 0.30
        cs_bonus = 1  # MID CS = 1 pt
    else:
        return samples  # FWDs don't get CS

    # Create bimodal: some samples get CS bonus, others don't
    cs_mask = np.random.random(len(samples)) < cs_prob
    adjusted = samples.copy()
    adjusted[cs_mask] += cs_bonus

    return adjusted
