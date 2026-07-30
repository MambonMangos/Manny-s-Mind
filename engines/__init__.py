"""Analytical engines – single source of truth for all business logic.

V1 Engines (legacy, still active):
  - value_engine: Value scores, position ratings
  - fixture_engine: Fixture difficulty, swings, windows
  - market_engine: Transfers, ownership, price trends
  - prediction_engine: Projected points, minutes projection (V1)
  - captain_engine: Captaincy analysis

V2 Engines (probabilistic forecasting platform):
  - minutes_engine: Minutes projection with rotation risk
  - fixture_engine: Enhanced with multi-GW windows, home/away split
  - regression_engine: Over/underperformance detection
  - market_intelligence_engine: Transfer activity, ownership trends
  - bookmaker_engine: Odds integration for fixture predictions
  - projection_engine: Points projection with confidence intervals
  - confidence_engine: Uncertainty quantification
  - opportunity_engine: Undervalued player detection
  - squad_optimizer: Budget-constrained squad optimization
  - monte_carlo_engine: Simulation for uncertainty quantification

Validation Platform (evidence-based model improvement):
  - validation_engine: Accuracy metrics, CI calibration, engine scorecard

Pipeline:
  - services/pipeline.py: Orchestrates all V2 engines in sequence
"""
