"""Neo4j graph database tools for querying the skill knowledge graph.

All connection parameters come from config.yaml with secrets resolved
from environment variables.

Uses the Neo4j HTTP Transactional API to avoid Bolt-protocol issues
when running behind an Envoy/Kagenti sidecar proxy.

Graph has two Skill populations:
  - Registry skills keyed by ``id`` (e.g. "docs-code-reviewer")
  - OCI-synced skills keyed by ``name`` (e.g. "active-directory-attacks")
All query helpers accept a generic identifier and match both keys.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from typing import Any

from shared.model_config import get_neo4j_config

_HTTP_PORT = 7474


def _neo4j_http_query(cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Execute a Cypher query via the Neo4j HTTP Transactional API."""
    cfg = get_neo4j_config()
    bolt_uri = cfg["uri"]
    host = bolt_uri.split("://")[-1].split(":")[0]
    db = cfg.get("database", "neo4j")
    url = f"http://{host}:{_HTTP_PORT}/db/{db}/tx/commit"
    creds = base64.b64encode(
        f"{cfg['user']}:{cfg['password']}".encode()
    ).decode()
    body = json.dumps(
        {"statements": [{"statement": cypher, "parameters": params or {}}]}
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {creds}",
        },
    )
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())
    if data.get("errors"):
        raise RuntimeError(
            f"Neo4j query error: {data['errors'][0].get('message', data['errors'])}"
        )
    results = data.get("results", [{}])[0]
    columns = results.get("columns", [])
    rows = results.get("data", [])
    return [dict(zip(columns, row["row"])) for row in rows]


def _skill_match_clause(var: str = "s", param: str = "identifier") -> str:
    """Cypher WHERE clause matching a Skill by name OR id."""
    return f"({var}.name = ${param} OR {var}.id = ${param})"


def query_skill_graph(cypher_query: str, parameters: str = "{}") -> str:
    """Execute a Cypher query against the Neo4j skill knowledge graph.

    Args:
        cypher_query: A valid Cypher query string.
        parameters: JSON-encoded dict of query parameters.

    Returns:
        JSON-encoded list of result records.
    """
    params: dict[str, Any] = json.loads(parameters)
    records = _neo4j_http_query(cypher_query, params)
    return json.dumps(records, default=str)


def find_skill(identifier: str) -> str:
    """Find a skill by name or id and return its full properties.

    Args:
        identifier: The skill name (kebab-case) or id.

    Returns:
        JSON-encoded skill record, or empty list if not found.
    """
    cypher = (
        f"MATCH (s:Skill) WHERE {_skill_match_clause()} "
        "RETURN s{.*, _labels: labels(s)} AS skill LIMIT 1"
    )
    return query_skill_graph(cypher, json.dumps({"identifier": identifier}))


def get_skill_dependencies(identifier: str, max_depth: int = 5) -> str:
    """Get transitive dependencies for a skill (DEPENDS_ON chain).

    Args:
        identifier: The skill name or id.
        max_depth: Maximum traversal depth (default 5).

    Returns:
        JSON-encoded list of dependency records with name/id and depth.
    """
    cypher = (
        f"MATCH (s:Skill) WHERE {_skill_match_clause()} "
        "MATCH path = (s)-[:DEPENDS_ON*1..5]->(dep:Skill) "
        "RETURN coalesce(dep.name, dep.id) AS dependency, "
        "dep.description AS description, length(path) AS depth "
        "ORDER BY depth"
    )
    return query_skill_graph(cypher, json.dumps({"identifier": identifier}))


def get_complementary_skills(identifier: str, min_confidence: float = 0.6) -> str:
    """Find skills that complement the given skill.

    Args:
        identifier: The skill name or id.
        min_confidence: Minimum confidence threshold (default 0.6).

    Returns:
        JSON-encoded list of complementary skills with confidence.
    """
    cypher = (
        f"MATCH (s:Skill) WHERE {_skill_match_clause()} "
        "MATCH (s)-[r:COMPLEMENTS]-(other:Skill) "
        "WHERE coalesce(r.confidence, 1.0) >= $min_conf "
        "RETURN coalesce(other.name, other.id) AS skill, "
        "other.description AS description, "
        "r.confidence AS confidence, r.description AS reason "
        "ORDER BY r.confidence DESC"
    )
    return query_skill_graph(
        cypher,
        json.dumps({"identifier": identifier, "min_conf": min_confidence}),
    )


def get_skill_alternatives(identifier: str) -> str:
    """Find alternative/interchangeable skills (ALTERNATIVE_TO).

    Args:
        identifier: The skill name or id.

    Returns:
        JSON-encoded list of alternative skills.
    """
    cypher = (
        f"MATCH (s:Skill) WHERE {_skill_match_clause()} "
        "MATCH (s)-[r:ALTERNATIVE_TO]-(alt:Skill) "
        "RETURN coalesce(alt.name, alt.id) AS skill, "
        "alt.description AS description, "
        "r.confidence AS confidence, r.description AS reason "
        "ORDER BY r.confidence DESC"
    )
    return query_skill_graph(cypher, json.dumps({"identifier": identifier}))


def explore_skill_neighborhood(identifier: str) -> str:
    """One-hop traversal across all relationship types for a skill.

    Args:
        identifier: The skill name or id.

    Returns:
        JSON-encoded list of neighbors with relationship type and direction.
    """
    cypher = (
        f"MATCH (s:Skill) WHERE {_skill_match_clause()} "
        "MATCH (s)-[r]-(neighbor) "
        "RETURN coalesce(neighbor.name, neighbor.id) AS neighbor, "
        "labels(neighbor)[0] AS label, "
        "type(r) AS relationship, "
        "CASE WHEN startNode(r) = s THEN 'outgoing' ELSE 'incoming' END AS direction, "
        "r.confidence AS confidence "
        "ORDER BY type(r), coalesce(neighbor.name, neighbor.id)"
    )
    return query_skill_graph(cypher, json.dumps({"identifier": identifier}))


def get_skill_similarity(identifier_a: str, identifier_b: str) -> str:
    """Get the similarity score between two skills (SIMILAR_TO edge).

    Args:
        identifier_a: First skill name or id.
        identifier_b: Second skill name or id.

    Returns:
        JSON-encoded similarity result.
    """
    cypher = (
        "MATCH (a:Skill) WHERE (a.name = $id_a OR a.id = $id_a) "
        "MATCH (b:Skill) WHERE (b.name = $id_b OR b.id = $id_b) "
        "OPTIONAL MATCH (a)-[r:SIMILAR_TO]-(b) "
        "RETURN coalesce(a.name, a.id) AS skill_a, "
        "coalesce(b.name, b.id) AS skill_b, "
        "r.score AS similarity_score"
    )
    return query_skill_graph(
        cypher,
        json.dumps({"id_a": identifier_a, "id_b": identifier_b}),
    )
