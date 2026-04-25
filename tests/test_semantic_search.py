"""Tests for shared.semantic_search_tools."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from shared.semantic_search_tools import _get_embedding, semantic_search_skills


class TestTopKClamping:
    @patch("shared.semantic_search_tools._get_embedding", return_value=[0.1] * 768)
    @patch("shared.semantic_search_tools._neo4j_http_query")
    def test_top_k_clamped_high(self, mock_query, mock_embed):
        mock_query.return_value = []
        semantic_search_skills("test", top_k=100)
        call_params = mock_query.call_args[0][1]
        assert call_params["top_k"] == 50

    @patch("shared.semantic_search_tools._get_embedding", return_value=[0.1] * 768)
    @patch("shared.semantic_search_tools._neo4j_http_query")
    def test_top_k_clamped_low(self, mock_query, mock_embed):
        mock_query.return_value = []
        semantic_search_skills("test", top_k=-5)
        call_params = mock_query.call_args[0][1]
        assert call_params["top_k"] == 1

    @patch("shared.semantic_search_tools._get_embedding", return_value=[0.1] * 768)
    @patch("shared.semantic_search_tools._neo4j_http_query")
    def test_top_k_default(self, mock_query, mock_embed):
        mock_query.return_value = []
        semantic_search_skills("test")
        call_params = mock_query.call_args[0][1]
        assert call_params["top_k"] == 10


class TestGetEmbedding:
    @patch("shared.semantic_search_tools.get_embedding_config")
    @patch("shared.semantic_search_tools.requests.post")
    def test_success(self, mock_post, mock_cfg):
        mock_cfg.return_value = {"id": "test-model", "api_base": "http://localhost"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        result = _get_embedding("hello")
        assert result == [0.1, 0.2, 0.3]

    @patch("shared.semantic_search_tools.time.sleep")
    @patch("shared.semantic_search_tools.get_embedding_config")
    @patch("shared.semantic_search_tools.requests.post")
    def test_retries_on_failure(self, mock_post, mock_cfg, mock_sleep):
        mock_cfg.return_value = {"id": "test-model", "api_base": "http://localhost"}
        mock_post.side_effect = [
            requests.ConnectionError("fail1"),
            requests.ConnectionError("fail2"),
            MagicMock(
                json=MagicMock(return_value={"data": [{"embedding": [1.0]}]}),
                raise_for_status=MagicMock(),
            ),
        ]
        result = _get_embedding("hello")
        assert result == [1.0]
        assert mock_post.call_count == 3

    @patch("shared.semantic_search_tools.time.sleep")
    @patch("shared.semantic_search_tools.get_embedding_config")
    @patch("shared.semantic_search_tools.requests.post")
    def test_raises_after_max_retries(self, mock_post, mock_cfg, mock_sleep):
        mock_cfg.return_value = {"id": "test-model", "api_base": "http://localhost"}
        mock_post.side_effect = requests.ConnectionError("always fails")
        with pytest.raises(RuntimeError, match="Embedding failed after"):
            _get_embedding("hello")
        assert mock_post.call_count == 3


class TestSemanticSearchSkills:
    @patch("shared.semantic_search_tools._get_embedding", return_value=[0.1] * 768)
    @patch("shared.semantic_search_tools._neo4j_http_query")
    def test_returns_json(self, mock_query, mock_embed):
        mock_query.return_value = [
            {"name": "test-skill", "description": "A test", "domain": "d", "plugin": "p", "score": 0.9}
        ]
        result = semantic_search_skills("kubernetes")
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "test-skill"
