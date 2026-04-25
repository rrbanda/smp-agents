"""Integration tests for Neo4j connectivity and graph queries.

Require a live Neo4j instance. Skipped automatically if unreachable.
"""

from __future__ import annotations

import json

import pytest

from shared.neo4j_tools import (
    _neo4j_http_query,
    explore_skill_neighborhood,
    find_skill,
    get_skill_dependencies,
    query_skill_graph,
)
from tests.conftest import neo4j_available


@neo4j_available
class TestNeo4jConnectivity:
    def test_ping(self):
        result = _neo4j_http_query("RETURN 1 AS ping")
        assert result == [{"ping": 1}]

    def test_skill_count_positive(self):
        result = _neo4j_http_query("MATCH (s:Skill) RETURN count(s) AS cnt")
        assert result[0]["cnt"] > 0


@neo4j_available
class TestFindSkill:
    def test_existing_skill(self):
        result = json.loads(find_skill("code-review"))
        if isinstance(result, list) and len(result) > 0:
            assert "skill" in result[0]

    def test_nonexistent_skill(self):
        result = json.loads(find_skill("nonexistent-skill-zzz-999"))
        assert isinstance(result, list)
        assert len(result) == 0


@neo4j_available
class TestDependenciesAndNeighborhood:
    def test_get_skill_dependencies(self):
        result = json.loads(get_skill_dependencies("code-review"))
        assert isinstance(result, list)

    def test_explore_skill_neighborhood(self):
        result = json.loads(explore_skill_neighborhood("code-review"))
        assert isinstance(result, list)


@neo4j_available
class TestSafetyGuardrails:
    def test_destructive_cypher_blocked(self):
        with pytest.raises(ValueError, match="DELETE"):
            query_skill_graph("MATCH (n) DELETE n")

    def test_bad_json_params_returns_error(self):
        result = json.loads(query_skill_graph("MATCH (s:Skill) RETURN s LIMIT 1", "not-json"))
        assert "error" in result
