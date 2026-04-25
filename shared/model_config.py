"""Centralized configuration loader for all SMP agents.

Reads config.yaml from the project root. Environment variables
can override secrets via ${VAR_NAME} syntax in YAML values.
"""

import logging
import os
import pathlib
import re
from functools import lru_cache
from typing import Any

import yaml
from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)

_PROJECT_ROOT = pathlib.Path(__file__).parent.parent
_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${VAR_NAME} and ${VAR:-default} references."""
    if isinstance(value, str):

        def _replace(m: re.Match) -> str:
            var_name = m.group(1)
            default = m.group(2)
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return env_val
            if default is not None:
                return default
            return m.group(0)

        return _ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


_REQUIRED_ENV_VARS = ["NEO4J_PASSWORD"]


def validate_env() -> list[str]:
    """Check that required environment variables are set. Returns missing names."""
    return [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Load and cache the project configuration from config.yaml."""
    config_path = _PROJECT_ROOT / "config.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. Copy config.yaml.example to config.yaml and set values."
        )
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise RuntimeError(f"Invalid YAML in {config_path}: {e}") from e
    if not isinstance(raw, dict):
        raise RuntimeError(f"Expected mapping in {config_path}, got {type(raw).__name__}")
    return _resolve_env_vars(raw)


def get_agent_model() -> LiteLlm:
    """Returns a LiteLlm instance from config."""
    cfg = load_config()["model"]["agent"]
    kwargs: dict[str, Any] = {"model": cfg["id"], "api_base": cfg["api_base"]}
    if cfg.get("api_key"):
        kwargs["api_key"] = cfg["api_key"]
    return LiteLlm(**kwargs)


def get_neo4j_config() -> dict:
    """Returns Neo4j connection parameters from config."""
    return load_config()["neo4j"]


def get_oci_config() -> dict:
    """Returns OCI registry parameters from config."""
    return load_config()["oci"]


def get_embedding_config() -> dict:
    """Returns embedding model parameters from config."""
    return load_config()["model"]["embedding"]


def get_agent_config(agent_name: str) -> dict:
    """Returns agent-specific configuration."""
    return load_config()["agents"][agent_name]
