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
import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from shared.model_config import get_neo4j_config

logger = logging.getLogger(__name__)

_HTTP_PORT = 7474
_MAX_RETRIES = 3
_CACHE_TTL = 300  # seconds
_CACHE_MAX_SIZE = 256

_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


def _cache_key(cypher: str, params: dict[str, Any] | None) -> str | None:
    """Build a cache key from cypher + params, or None if uncacheable."""
    serialized = json.dumps(params or {}, sort_keys=True, default=str)
    if len(serialized) > 4096:
        return None
    raw = f"{cypher}\x00{serialized}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> list[dict] | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, data = entry
        if time.monotonic() - ts > _CACHE_TTL:
            del _cache[key]
            return None
        return data


def _cache_put(key: str, data: list[dict]) -> None:
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX_SIZE:
            oldest_key = min(_cache, key=lambda k: _cache[k][0])
            del _cache[oldest_key]
        _cache[key] = (time.monotonic(), data)


_CYPHER_ALLOWED_PREFIXES = frozenset(
    [
        "MATCH",
        "OPTIONAL",
        "RETURN",
        "WITH",
        "UNWIND",
        "CALL DB.",
        "CALL DBMS.CLUSTER",  # read-only cluster info
    ]
)
_CYPHER_BLOCKED_KEYWORDS = frozenset(
    [
        "DELETE",
        "DETACH",
        "REMOVE",
        "DROP",
        "CREATE",
        "MERGE",
        "SET ",
        "CREATE INDEX",
        "CREATE CONSTRAINT",
        "CALL DBMS",
        "LOAD CSV",
    ]
)


def _neo4j_http_query(
    cypher: str,
    params: dict[str, Any] | None = None,
    *,
    retries: int = _MAX_RETRIES,
) -> list[dict]:
    """Execute a Cypher query via the Neo4j HTTP Transactional API."""
    ck = _cache_key(cypher, params)
    if ck is not None:
        cached = _cache_get(ck)
        if cached is not None:
            return cached

    cfg = get_neo4j_config()
    db = cfg.get("database", "neo4j")
    http_url = cfg.get("http_url", "")
    if http_url:
        url = f"{http_url.rstrip('/')}/db/{db}/tx/commit"
    else:
        bolt_uri = cfg["uri"]
        host = bolt_uri.split("://")[-1].split(":")[0]
        url = f"http://{host}:{_HTTP_PORT}/db/{db}/tx/commit"
    creds = base64.b64encode(f"{cfg['user']}:{cfg['password']}".encode()).decode()
    body = json.dumps({"statements": [{"statement": cypher, "parameters": params or {}}]}).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {creds}",
    }

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read().decode())
            if data.get("errors"):
                raise RuntimeError(f"Neo4j query error: {data['errors'][0].get('message', data['errors'])}")
            results = data.get("results", [{}])[0]
            columns = results.get("columns", [])
            rows = results.get("data", [])
            records = [dict(zip(columns, row["row"], strict=False)) for row in rows]
            if ck is not None:
                _cache_put(ck, records)
            return records
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode()[:500] if e.fp else ""
            last_err = RuntimeError(f"Neo4j HTTP {e.code}: {resp_body}")
            if e.code < 500:
                raise last_err from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
        if attempt < retries - 1:
            wait = 2**attempt
            logger.warning("Neo4j query attempt %d failed, retrying in %ds", attempt + 1, wait)
            time.sleep(wait)

    raise RuntimeError(f"Neo4j query failed after {retries} attempts") from last_err


def _skill_match_clause(var: str = "s", param: str = "identifier") -> str:
    """Cypher WHERE clause matching a Skill by name OR id."""
    return f"({var}.name = ${param} OR {var}.id = ${param})"


def _check_cypher_safety(cypher: str) -> None:
    """Reject Cypher containing write/destructive operations.

    Uses a two-layer defense: first checks that the query starts with a
    known read-only prefix (allowlist), then scans for blocked keywords
    anywhere in the query body (blocklist).
    """
    stripped = cypher.strip()
    upper = stripped.upper()

    prefix_ok = any(upper.startswith(prefix) for prefix in _CYPHER_ALLOWED_PREFIXES)
    if not prefix_ok:
        raise ValueError(
            f"Cypher query must start with a read-only clause "
            f"(MATCH, OPTIONAL MATCH, RETURN, WITH, UNWIND, CALL db.*). "
            f"Got: {stripped[:60]!r}"
        )

    for keyword in _CYPHER_BLOCKED_KEYWORDS:
        if keyword in upper:
            raise ValueError(f"Blocked Cypher operation: {keyword}")


def query_skill_graph(cypher_query: str, parameters: str = "{}") -> str:
    """Execute a read-only Cypher query against the Neo4j skill knowledge graph.

    Args:
        cypher_query: A valid Cypher query string (read-only).
        parameters: JSON-encoded dict of query parameters.

    Returns:
        JSON-encoded list of result records.
    """
    _check_cypher_safety(cypher_query)
    try:
        params: dict[str, Any] = json.loads(parameters)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": f"Invalid JSON parameters: {e}"})
    records = _neo4j_http_query(cypher_query, params)
    return json.dumps(records, default=str)


def find_skill(identifier: str) -> str:
    """Find a skill by name or id and return its full properties.

    Args:
        identifier: The skill name (kebab-case) or id.

    Returns:
        JSON-encoded skill record, or empty list if not found.
    """
    cypher = f"MATCH (s:Skill) WHERE {_skill_match_clause()} RETURN s{{.*, _labels: labels(s)}} AS skill LIMIT 1"
    return query_skill_graph(cypher, json.dumps({"identifier": identifier}))


def get_skill_dependencies(identifier: str, max_depth: int = 5) -> str:
    """Get transitive dependencies for a skill (DEPENDS_ON chain).

    Args:
        identifier: The skill name or id.
        max_depth: Maximum traversal depth (1-10, default 5).

    Returns:
        JSON-encoded list of dependency records with name/id and depth.
    """
    max_depth = max(1, min(int(max_depth), 10))
    cypher = (
        f"MATCH (s:Skill) WHERE {_skill_match_clause()} "
        f"MATCH path = (s)-[:DEPENDS_ON*1..{max_depth}]->(dep:Skill) "
        "RETURN coalesce(dep.name, dep.id) AS dependency, "
        "dep.description AS description, length(path) AS depth "
        "ORDER BY depth"
    )
    return query_skill_graph(cypher, json.dumps({"identifier": identifier}))


def get_complementary_skills(identifier: str, min_confidence: float = 0.6) -> str:
    """Find skills that complement the given skill.

    Args:
        identifier: The skill name or id.
        min_confidence: Minimum confidence threshold (0.0-1.0, default 0.6).

    Returns:
        JSON-encoded list of complementary skills with confidence.
    """
    min_confidence = max(0.0, min(float(min_confidence), 1.0))
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


def get_graph_context(identifier: str) -> str:
    """Get a compact summary of a skill's full graph neighborhood in one call.

    Returns the skill's properties plus all connected nodes grouped by
    relationship type (tags, domain, dependencies, complements, alternatives,
    similar skills). Useful for giving the LLM rich context without needing
    multiple sequential tool calls.

    Args:
        identifier: The skill name or id.

    Returns:
        JSON-encoded summary with skill properties and grouped relationships.
    """
    cypher = (
        f"MATCH (s:Skill) WHERE {_skill_match_clause()} "
        "OPTIONAL MATCH (s)-[r]-(neighbor) "
        "WITH s, type(r) AS rel_type, "
        "collect(DISTINCT {name: coalesce(neighbor.name, neighbor.id), "
        "label: labels(neighbor)[0], "
        "direction: CASE WHEN startNode(r) = s THEN 'out' ELSE 'in' END, "
        "confidence: r.confidence, score: r.score}) AS neighbors "
        "WITH s, collect({type: rel_type, nodes: neighbors}) AS relationships "
        "RETURN coalesce(s.name, s.id) AS identifier, "
        "s.description AS description, s.domain AS domain, "
        "s.plugin AS plugin, s.category AS category, "
        "s.tags AS tags, s.version AS version, "
        "relationships"
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
