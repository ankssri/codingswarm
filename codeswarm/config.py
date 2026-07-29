"""Configuration loading and merging.

Precedence (low -> high): built-in defaults < config file < CLI overrides.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into a copy of `base`."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(config_path: str | os.PathLike | None = None, overrides: dict[str, Any] | None = None) -> dict:
    """Load default config, optionally overlay a user file, then CLI overrides."""
    with open(_DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}
        config = _deep_merge(config, user_cfg)

    if overrides:
        config = _deep_merge(config, overrides)

    return config


def resolve_role(config: dict, role: str) -> tuple[str, str, dict]:
    """Return (provider_name, provider_cfg, role_cfg) for a given agent role.

    A role can override the top-level provider and/or model via config["agents"].
    """
    role_cfg = (config.get("agents") or {}).get(role) or {}
    provider_name = role_cfg.get("provider") or config.get("provider", "mock")

    providers = config.get("providers") or {}
    if provider_name not in providers:
        raise ValueError(
            f"Provider '{provider_name}' (for role '{role}') is not defined under 'providers' in config."
        )
    provider_cfg = dict(providers[provider_name])
    return provider_name, provider_cfg, role_cfg
