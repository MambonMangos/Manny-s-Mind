"""League Intelligence Layer — league-aware strategy, layered on predictions.

Never modifies the prediction engine. Consumes projections + feature store +
(optional) league/rival/community data and produces strategic recommendations.

Public API: ``engine.run_league_intelligence``.
"""

from services.league_intelligence.engine import run_league_intelligence
from services.league_intelligence.models import LeagueIntelligenceReport

__all__ = ["LeagueIntelligenceReport", "run_league_intelligence"]
