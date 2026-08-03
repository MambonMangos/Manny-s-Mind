"""Configuration loader — single source of truth for all config access.

Reads versioned YAML config files from the config/ directory.
Every config has a version. Never overwrite old versions.
Switch versions by updating config/active.yaml.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_ACTIVE_FILE = _CONFIG_DIR / "active.yaml"
_cache: dict[str, dict] = {}
_active_cache: dict[str, str] | None = None

# Versions become part of a filesystem path. Restrict to a safe character set
# so a future caller can never turn a version string into a path traversal.
_SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _hash_config(config: dict) -> str:
    """Compute SHA256 hash of a config dict for experiment tracking."""
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _read_yaml(path: Path) -> dict:
    """Read a YAML file and return parsed dict."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_active_versions() -> dict[str, str]:
    """Load the active version map from active.yaml."""
    global _active_cache
    if _active_cache is not None:
        return _active_cache
    data = _read_yaml(_ACTIVE_FILE)
    _active_cache = data.get("active_versions", {})
    return _active_cache


def invalidate_cache() -> None:
    """Clear all cached configs. Call after config changes."""
    global _active_cache
    _cache.clear()
    _active_cache = None


def load_config(category: str, version: str | None = None) -> dict:
    """Load a config by category and optional version.

    Parameters
    ----------
    category : str
        Config category: "weights", "fixtures", "minutes", "prediction",
        "bookmaker", "features"
    version : str | None
        Specific version to load (e.g. "weights_v2").
        If None, loads the active version from active.yaml.

    Returns
    -------
    dict
        Parsed config dictionary.

    Raises
    ------
    FileNotFoundError
        If the config file does not exist.
    """
    if version is None:
        active = load_active_versions()
        version = active.get(category)
        if version is None:
            raise FileNotFoundError(
                f"No active version set for category '{category}' in active.yaml"
            )

    cache_key = f"{category}/{version}"
    if cache_key in _cache:
        return _cache[cache_key]

    if not _SAFE_VERSION_RE.match(version):
        raise ValueError(f"Invalid config version: {version!r}")

    category_dir = _CONFIG_DIR / category
    if not category_dir.is_dir():
        raise FileNotFoundError(f"No config category: {category}")

    config_path = (category_dir / f"{version}.yaml").resolve()
    if not str(config_path).startswith(str(category_dir.resolve())):
        raise ValueError(f"Config path escapes category directory: {config_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    config = _read_yaml(config_path)
    _cache[cache_key] = config
    logger.debug("Loaded config: %s (version %s)", category, version)
    return config


def get_active_version(category: str) -> str:
    """Get the active version string for a category."""
    active = load_active_versions()
    version = active.get(category)
    if version is None:
        raise FileNotFoundError(f"No active version for '{category}'")
    return version


def list_versions(category: str) -> list[str]:
    """List all available versions for a config category."""
    category_dir = _CONFIG_DIR / category
    if not category_dir.exists():
        return []
    versions = []
    for f in sorted(category_dir.glob("*.yaml")):
        versions.append(f.stem)
    return versions


def compare_versions(category: str, v1: str, v2: str) -> dict:
    """Diff two config versions. Returns dict with added, removed, changed keys."""
    c1 = load_config(category, v1)
    c2 = load_config(category, v2)

    keys1 = set(_flatten_keys(c1).keys())
    keys2 = set(_flatten_keys(c2).keys())

    added = keys2 - keys1
    removed = keys1 - keys2
    common = keys1 & keys2

    changed = {}
    flat1 = _flatten_keys(c1)
    flat2 = _flatten_keys(c2)
    for k in common:
        if flat1[k] != flat2[k]:
            changed[k] = {"old": flat1[k], "new": flat2[k]}

    return {
        "version_1": v1,
        "version_2": v2,
        "added": sorted(added),
        "removed": sorted(removed),
        "changed": changed,
    }


def get_config_hash(category: str, version: str | None = None) -> str:
    """Get SHA256 hash of a config for experiment tracking."""
    config = load_config(category, version)
    return _hash_config(config)


def get_all_config_hashes() -> dict[str, str]:
    """Get hashes of all active configs. Useful for experiment metadata."""
    active = load_active_versions()
    hashes = {}
    for category, version in active.items():
        hashes[category] = get_config_hash(category, version)
    return hashes


def _flatten_keys(d: dict, prefix: str = "") -> dict:
    """Flatten nested dict into dot-separated keys."""
    items = {}
    for k, v in d.items():
        new_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten_keys(v, new_key))
        else:
            items[new_key] = v
    return items
