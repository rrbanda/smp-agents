"""Tests for shared.neo4j_tools."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from shared.neo4j_tools import (
    _cache,
    _check_cypher_safety,
    _neo4j_http_query,
    _skill_match_clause,
    explore_skill_neighborhood,
    find_skill,
    get_complementary_skills,
    get_graph_context,
    get_skill_alternatives,
    get_skill_dependencies,
    get_skill_similarity,
    query_skill_graph,
)

# ---- Cypher safety --------------------------------------------------------


class TestCypherSafety:
    # --- Allowed read-only queries ---

    def test_allows_match(self):
        _check_cypher_safety("MATCH (s:Skill) RETURN s LIMIT 10")

    def test_allows_optional_match(self):
        _check_cypher_safety("OPTIONAL MATCH (s:Skill)-[r]->(t) RETURN s, r, t")

    def test_allows_return(self):
        _check_cypher_safety("RETURN 1 AS ping")

    def test_allows_with(self):
        _check_cypher_safety("WITH 'test' AS val RETURN val")

    def test_allows_unwind(self):
        _check_cypher_safety("UNWIND [1,2,3] AS x RETURN x")

    def test_allows_call_db_vector(self):
        _check_cypher_safety(
            "CALL db.index.vector.queryNodes('skill_embedding_idx', 10, [0.1]) YIELD node, score RETURN node, score"
        )

    # --- Blocked by allowlist (bad prefix) ---

    def test_blocks_create_node_prefix(self):
        with pytest.raises(ValueError, match="read-only clause"):
            _check_cypher_safety("CREATE (n:Skill {name: 'injected'})")

    def test_blocks_merge_prefix(self):
        with pytest.raises(ValueError, match="read-only clause"):
            _check_cypher_safety("MERGE (n:Skill {name: 'injected'})")

    # --- Blocked by blocklist (write keywords inside valid prefix) ---

    def test_blocks_delete(self):
        with pytest.raises(ValueError, match="DELETE"):
            _check_cypher_safety("MATCH (n) DELETE n")

    def test_blocks_detach_delete(self):
        with pytest.raises(ValueError, match="DELETE|DETACH"):
            _check_cypher_safety("MATCH (n) DETACH DELETE n")

    def test_blocks_drop(self):
        with pytest.raises(ValueError, match="read-only clause"):
            _check_cypher_safety("DROP INDEX foo")

    def test_blocks_remove(self):
        with pytest.raises(ValueError, match="REMOVE"):
            _check_cypher_safety("MATCH (n) REMOVE n.prop")

    def test_blocks_load_csv(self):
        with pytest.raises(ValueError, match="read-only clause"):
            _check_cypher_safety("LOAD CSV FROM 'file:///data.csv' AS row")

    def test_case_insensitive(self):
        with pytest.raises(ValueError):
            _check_cypher_safety("match (n) delete n")

    def test_blocks_create_index(self):
        with pytest.raises(ValueError, match="CREATE"):
            _check_cypher_safety("CREATE INDEX ON :Skill(name)")

    def test_blocks_call_dbms(self):
        with pytest.raises(ValueError, match="read-only clause"):
            _check_cypher_safety("CALL dbms.security.createUser('bad','pw',false)")

    def test_blocks_set_in_match(self):
        with pytest.raises(ValueError, match="SET"):
            _check_cypher_safety("MATCH (n:Skill) SET n.hacked = true")

    def test_blocks_create_in_match(self):
        with pytest.raises(ValueError, match="CREATE"):
            _check_cypher_safety("MATCH (a:Skill), (b:Skill) CREATE (a)-[:HACKED]->(b)")

    def test_blocks_merge_in_match(self):
        with pytest.raises(ValueError, match="MERGE"):
            _check_cypher_safety("MATCH (a:Skill) MERGE (a)-[:HACKED]->(b:Skill)")

    def test_allows_whitespace_prefix(self):
        _check_cypher_safety("  MATCH (s:Skill) RETURN s")


# ---- Match clause ---------------------------------------------------------


class TestSkillMatchClause:
    def test_default(self):
        clause = _skill_match_clause()
        assert clause == "(s.name = $identifier OR s.id = $identifier)"

    def test_custom_var(self):
        clause = _skill_match_clause(var="x", param="p")
        assert clause == "(x.name = $p OR x.id = $p)"


# ---- query_skill_graph ----------------------------------------------------


class TestQuerySkillGraph:
    @patch("shared.neo4j_tools._neo4j_http_query")
    def test_valid_query(self, mock_query):
        mock_query.return_value = [{"name": "test"}]
        result = query_skill_graph("MATCH (s:Skill) RETURN s.name AS name", "{}")
        assert json.loads(result) == [{"name": "test"}]

    def test_blocked_query(self):
        with pytest.raises(ValueError, match="DELETE"):
            query_skill_graph("MATCH (n) DELETE n")

    def test_invalid_json_parameters(self):
        result = query_skill_graph("MATCH (s:Skill) RETURN s", "not-json")
        parsed = json.loads(result)
        assert "error" in parsed

    @patch("shared.neo4j_tools._neo4j_http_query")
    def test_empty_params(self, mock_query):
        mock_query.return_value = []
        query_skill_graph("MATCH (s:Skill) RETURN s.name")
        mock_query.assert_called_once_with("MATCH (s:Skill) RETURN s.name", {})


# ---- Retry logic in _neo4j_http_query -------------------------------------


class TestNeo4jHttpQueryRetry:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        _cache.clear()

    def _make_success_response(self):
        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {
                "results": [{"columns": ["n"], "data": [{"row": [1]}]}],
                "errors": [],
            }
        ).encode()
        return resp

    @patch("shared.neo4j_tools.time.sleep")
    @patch("shared.neo4j_tools.urllib.request.urlopen")
    @patch("shared.neo4j_tools.get_neo4j_config")
    def test_retries_on_url_error(self, mock_cfg, mock_urlopen, mock_sleep):
        mock_cfg.return_value = {
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "pw",
            "database": "neo4j",
        }
        mock_urlopen.side_effect = [
            urllib.error.URLError("fail1"),
            urllib.error.URLError("fail2"),
            self._make_success_response(),
        ]
        result = _neo4j_http_query("RETURN 1 AS n")
        assert result == [{"n": 1}]
        assert mock_urlopen.call_count == 3

    @patch("shared.neo4j_tools.time.sleep")
    @patch("shared.neo4j_tools.urllib.request.urlopen")
    @patch("shared.neo4j_tools.get_neo4j_config")
    def test_retries_on_http_500(self, mock_cfg, mock_urlopen, mock_sleep):
        mock_cfg.return_value = {
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "pw",
            "database": "neo4j",
        }
        err = urllib.error.HTTPError(
            "http://localhost",
            500,
            "Internal Server Error",
            {},
            io.BytesIO(b"server error"),
        )
        mock_urlopen.side_effect = [err, self._make_success_response()]
        result = _neo4j_http_query("RETURN 1 AS n", retries=2)
        assert result == [{"n": 1}]
        assert mock_urlopen.call_count == 2

    @patch("shared.neo4j_tools.urllib.request.urlopen")
    @patch("shared.neo4j_tools.get_neo4j_config")
    def test_no_retry_on_http_400(self, mock_cfg, mock_urlopen):
        mock_cfg.return_value = {
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "pw",
            "database": "neo4j",
        }
        err = urllib.error.HTTPError(
            "http://localhost",
            400,
            "Bad Request",
            {},
            io.BytesIO(b"bad request"),
        )
        mock_urlopen.side_effect = err
        with pytest.raises(RuntimeError, match="Neo4j HTTP 400"):
            _neo4j_http_query("RETURN 1 AS n")
        assert mock_urlopen.call_count == 1

    @patch("shared.neo4j_tools.time.sleep")
    @patch("shared.neo4j_tools.urllib.request.urlopen")
    @patch("shared.neo4j_tools.get_neo4j_config")
    def test_raises_after_all_retries(self, mock_cfg, mock_urlopen, mock_sleep):
        mock_cfg.return_value = {
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "pw",
            "database": "neo4j",
        }
        mock_urlopen.side_effect = urllib.error.URLError("always fails")
        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            _neo4j_http_query("RETURN 1 AS n")


# ---- Depth / confidence clamping ------------------------------------------


class TestGetSkillDependencies:
    @patch("shared.neo4j_tools.query_skill_graph")
    def test_max_depth_clamped_high(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_skill_dependencies("test", max_depth=100)
        call_args = mock_qsg.call_args[0][0]
        assert "*1..10" in call_args

    @patch("shared.neo4j_tools.query_skill_graph")
    def test_max_depth_clamped_low(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_skill_dependencies("test", max_depth=-5)
        call_args = mock_qsg.call_args[0][0]
        assert "*1..1" in call_args

    @patch("shared.neo4j_tools.query_skill_graph")
    def test_default_depth(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_skill_dependencies("test")
        call_args = mock_qsg.call_args[0][0]
        assert "*1..5" in call_args


class TestGetComplementarySkills:
    @patch("shared.neo4j_tools.query_skill_graph")
    def test_min_confidence_clamped(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_complementary_skills("test", min_confidence=5.0)
        params = json.loads(mock_qsg.call_args[0][1])
        assert params["min_conf"] == 1.0

    @patch("shared.neo4j_tools.query_skill_graph")
    def test_min_confidence_negative(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_complementary_skills("test", min_confidence=-1.0)
        params = json.loads(mock_qsg.call_args[0][1])
        assert params["min_conf"] == 0.0


# ---- Remaining tool functions ---------------------------------------------


class TestFindSkill:
    @patch("shared.neo4j_tools.query_skill_graph")
    def test_calls_with_identifier(self, mock_qsg):
        mock_qsg.return_value = '[{"skill": {"name": "test"}}]'
        find_skill("my-skill")
        params = json.loads(mock_qsg.call_args[0][1])
        assert params["identifier"] == "my-skill"


class TestGetSkillAlternatives:
    @patch("shared.neo4j_tools.query_skill_graph")
    def test_calls_with_identifier(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_skill_alternatives("my-skill")
        params = json.loads(mock_qsg.call_args[0][1])
        assert params["identifier"] == "my-skill"
        assert "ALTERNATIVE_TO" in mock_qsg.call_args[0][0]


class TestExploreSkillNeighborhood:
    @patch("shared.neo4j_tools.query_skill_graph")
    def test_calls_with_identifier(self, mock_qsg):
        mock_qsg.return_value = "[]"
        explore_skill_neighborhood("my-skill")
        params = json.loads(mock_qsg.call_args[0][1])
        assert params["identifier"] == "my-skill"


class TestGetGraphContext:
    @patch("shared.neo4j_tools.query_skill_graph")
    def test_calls_with_identifier(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_graph_context("my-skill")
        params = json.loads(mock_qsg.call_args[0][1])
        assert params["identifier"] == "my-skill"
        cypher = mock_qsg.call_args[0][0]
        assert "relationships" in cypher
        assert "OPTIONAL MATCH" in cypher


class TestGetSkillSimilarity:
    @patch("shared.neo4j_tools.query_skill_graph")
    def test_calls_with_both_ids(self, mock_qsg):
        mock_qsg.return_value = "[]"
        get_skill_similarity("skill-a", "skill-b")
        params = json.loads(mock_qsg.call_args[0][1])
        assert params["id_a"] == "skill-a"
        assert params["id_b"] == "skill-b"
        assert "SIMILAR_TO" in mock_qsg.call_args[0][0]
