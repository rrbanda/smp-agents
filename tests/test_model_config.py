"""Tests for shared.model_config."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from shared.model_config import _resolve_env_vars, load_config, validate_env


class TestResolveEnvVars:
    def test_simple_string(self):
        assert _resolve_env_vars("hello") == "hello"

    def test_env_var_substitution(self):
        with patch.dict(os.environ, {"TEST_VAR": "replaced"}):
            assert _resolve_env_vars("${TEST_VAR}") == "replaced"

    def test_env_var_with_default(self):
        os.environ.pop("MISSING_VAR", None)
        assert _resolve_env_vars("${MISSING_VAR:-fallback}") == "fallback"

    def test_env_var_overrides_default(self):
        with patch.dict(os.environ, {"PRESENT_VAR": "actual"}):
            assert _resolve_env_vars("${PRESENT_VAR:-fallback}") == "actual"

    def test_unresolved_env_var(self):
        os.environ.pop("UNSET_VAR", None)
        assert _resolve_env_vars("${UNSET_VAR}") == "${UNSET_VAR}"

    def test_dict_recursion(self):
        with patch.dict(os.environ, {"A": "1"}):
            result = _resolve_env_vars({"key": "${A}", "nested": {"inner": "${A}"}})
            assert result == {"key": "1", "nested": {"inner": "1"}}

    def test_list_recursion(self):
        with patch.dict(os.environ, {"B": "2"}):
            result = _resolve_env_vars(["${B}", "plain", ["${B}"]])
            assert result == ["2", "plain", ["2"]]

    def test_non_string_passthrough(self):
        assert _resolve_env_vars(42) == 42
        assert _resolve_env_vars(True) is True
        assert _resolve_env_vars(None) is None


class TestValidateEnv:
    def test_returns_empty_when_set(self):
        with patch.dict(os.environ, {"NEO4J_PASSWORD": "secret"}):
            assert validate_env() == []

    def test_returns_missing_when_unset(self):
        os.environ.pop("NEO4J_PASSWORD", None)
        result = validate_env()
        assert "NEO4J_PASSWORD" in result


class TestLoadConfig:
    def test_missing_config_raises(self, tmp_path):
        load_config.cache_clear()
        with patch("shared.model_config._PROJECT_ROOT", tmp_path), pytest.raises(FileNotFoundError):
            load_config()
        load_config.cache_clear()

    def test_invalid_yaml_raises(self, tmp_path):
        load_config.cache_clear()
        bad_yaml = tmp_path / "config.yaml"
        bad_yaml.write_text("key: [unclosed bracket", encoding="utf-8")
        with (
            patch("shared.model_config._PROJECT_ROOT", tmp_path),
            pytest.raises(RuntimeError, match="Invalid YAML"),
        ):
            load_config()
        load_config.cache_clear()

    def test_non_dict_yaml_raises(self, tmp_path):
        load_config.cache_clear()
        bad_yaml = tmp_path / "config.yaml"
        bad_yaml.write_text('"just a string"', encoding="utf-8")
        with (
            patch("shared.model_config._PROJECT_ROOT", tmp_path),
            pytest.raises(RuntimeError, match="Expected mapping"),
        ):
            load_config()
        load_config.cache_clear()

    def test_valid_yaml_loads(self, tmp_path):
        load_config.cache_clear()
        good_yaml = tmp_path / "config.yaml"
        good_yaml.write_text("model:\n  agent:\n    id: test\n", encoding="utf-8")
        with patch("shared.model_config._PROJECT_ROOT", tmp_path):
            cfg = load_config()
        assert cfg["model"]["agent"]["id"] == "test"
        load_config.cache_clear()
