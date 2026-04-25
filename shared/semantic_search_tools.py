"""Semantic search tools for finding skills by meaning.

Uses the embedding model from config.yaml and the Neo4j HTTP API
to perform cosine-similarity search over skill descriptions.
"""

from __future__ import annotations

import json
import logging
import time

import requests

from shared.model_config import get_embedding_config
from shared.neo4j_tools import _neo4j_http_query

logger = logging.getLogger(__name__)

_MAX_TOP_K = 50
_EMBED_MAX_RETRIES = 3


def _get_embedding(text: str) -> list[float]:
    """Call the embedding model endpoint to vectorize text."""
    cfg = get_embedding_config()
    last_err: Exception | None = None
    for attempt in range(_EMBED_MAX_RETRIES):
        try:
            response = requests.post(
                f"{cfg['api_base']}/embeddings",
                json={"model": cfg["id"], "input": text},
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]  # type: ignore[no-any-return]
        except (requests.RequestException, KeyError, IndexError) as e:
            last_err = e
            if attempt < _EMBED_MAX_RETRIES - 1:
                wait = 2**attempt
                logger.warning("Embedding attempt %d failed: %s, retrying in %ds", attempt + 1, e, wait)
                time.sleep(wait)
    raise RuntimeError(f"Embedding failed after {_EMBED_MAX_RETRIES} attempts") from last_err


def semantic_search_skills(query: str, top_k: int = 10) -> str:
    """Search for skills by semantic similarity to a natural-language query.

    Args:
        query: Natural-language description of what the user is looking for.
        top_k: Number of top results to return (default 10, max 50).

    Returns:
        JSON-encoded list of matching skills with similarity scores.
    """
    top_k = max(1, min(int(top_k), _MAX_TOP_K))
    embedding = _get_embedding(query)
    cypher = (
        "CALL db.index.vector.queryNodes("
        "'skill_embedding_idx', $top_k, $embedding"
        ") YIELD node, score "
        "RETURN coalesce(node.name, node.id) AS name, "
        "node.description AS description, "
        "node.domain AS domain, node.plugin AS plugin, score "
        "ORDER BY score DESC"
    )
    records = _neo4j_http_query(cypher, {"top_k": top_k, "embedding": embedding})
    return json.dumps(records, default=str)
