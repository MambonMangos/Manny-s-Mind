"""Feature Store — single source of truth for all derived player features.

Every engine reads features from here. Features are computed once per
snapshot cycle and shared across all analytical layers.

Usage::

    from features import FeatureStore, build_feature_store
    from services.scoring import add_derived_columns

    store = build_feature_store(
        players_df=raw_df,
        fixture_map=fmap,
        team_name_map=tmap,
        gameweek_history=history_df,
    )

    # Engines consume features
    minutes_features = store.minutes_features()
    fixture_features = store.fixture_features(gameweek=3)
    value_features = store.value_features()
"""

from features.store import FeatureStore, build_feature_store

__all__ = ["FeatureStore", "build_feature_store"]
