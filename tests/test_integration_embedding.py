"""Integration tests for the embedding model and semantic search.

Require a live embedding endpoint. Skipped automatically if unreachable.
"""

from __future__ import annotations

import json

from shared.semantic_search_tools import _get_embedding, semantic_search_skills
from tests.conftest import llm_available


@llm_available
class TestEmbeddingEndpoint:
    def test_embedding_returns_floats(self):
        vec = _get_embedding("test query for embeddings")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_embedding_dimension(self):
        vec = _get_embedding("another test query")
        assert len(vec) == 768


@llm_available
class TestSemanticSearch:
    def test_returns_results(self):
        result = json.loads(semantic_search_skills("kubernetes deployment"))
        assert isinstance(result, list)

    def test_top_k_respected(self):
        result = json.loads(semantic_search_skills("security scanning", top_k=3))
        assert len(result) <= 3
