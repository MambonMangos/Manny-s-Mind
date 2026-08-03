"""Smoke tests — prove the application imports, configures, and boots.

These are fast, offline tests that catch import errors, broken config
references, and database initialisation failures before deployment.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_all_pages_parse_as_python():
    """Every Streamlit page must be syntactically valid Python."""
    import ast

    pages_dir = os.path.join(PROJECT_ROOT, "pages")
    pages = sorted(f for f in os.listdir(pages_dir) if f.endswith(".py"))
    assert pages, "No pages found"
    for page in pages:
        with open(os.path.join(pages_dir, page)) as fh:
            ast.parse(fh.read())
    # Also the entry point
    with open(os.path.join(PROJECT_ROOT, "app.py")) as fh:
        ast.parse(fh.read())


def test_config_system_loads_all_categories():
    """Every category in config/active.yaml must resolve to an existing file."""
    from utils.config import load_active_versions, load_config

    active = load_active_versions()
    assert "weights" in active, "weights category missing from active.yaml"
    for category, version in active.items():
        config = load_config(category, version)
        assert config, f"Config for {category}/{version} is empty"


def test_all_config_yamls_are_valid():
    """Every YAML file under config/ must parse."""
    import glob

    import yaml

    for path in glob.glob(os.path.join(PROJECT_ROOT, "config", "**", "*.yaml"), recursive=True):
        with open(path) as fh:
            data = yaml.safe_load(fh)
        assert data is not None, f"Config file is empty or invalid: {path}"


def test_environment_bootstrap_loads_dotenv():
    """utils.env must load .env without raising."""
    import utils.env
    assert callable(utils.env.load_env)


def test_database_initialises_on_fresh_sqlite(tmp_path):
    """Base.metadata.create_all must build the full schema on a fresh database."""
    from sqlalchemy import create_engine, inspect

    from database.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'smoke.db'}")
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    assert tables, "create_all must create tables"
    assert "players" in tables and "teams" in tables


def test_logging_setup_is_idempotent():
    """setup_logging() must be callable multiple times without raising."""
    from utils.logging_setup import setup_logging

    setup_logging()
    setup_logging()


def test_scoring_weights_import_assertion():
    """Importing utils.constants must not raise (weights sum guard)."""
    from utils.constants import WEIGHTS  # noqa: F401
