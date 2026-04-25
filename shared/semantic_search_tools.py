"""Semantic search tools for finding skills by meaning.

Uses the embedding model from config.yaml and a Neo4j vector index
to perform cosine-similarity search over skill descriptions.
"""

from __future__ import annotations

import json
from typing import Any

import requests
from neo4j import GraphDatabase

from shared.model_config import get_embedding_config, get_neo4j_config


def _get_embedding(text: str) -> list[float]:
    """Call the embedding model endpoint to vectorize text."""
    cfg = get_embedding_config()
    response = requests.post(
        f"{cfg['api_base']}/embeddings",
        json={"model": cfg["id"], "input": text},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["data"][0]["embedding"]


def semantic_search_skills(query: str, top_k: int = 10) -> str:
    """Search for skills by semantic similarity to a natural-language query.

    Args:
        query: Natural-language description of what the user is looking for.
        top_k: Number of top results to return (default 10).

    Returns:
        JSON-encoded list of matching skills with similarity scores.
    """
    embedding = _get_embedding(query)
    neo4j_cfg = get_neo4j_config()
    embed_cfg = get_embedding_config()
    dimension = embed_cfg.get("dimension", 768)

    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )
    try:
        with driver.session(database=neo4j_cfg.get("database", "neo4j")) as session:
            result = session.run(
                "CALL db.index.vector.queryNodes("
                "'skill_embedding_idx', $top_k, $embedding"
                ") YIELD node, score "
                "RETURN coalesce(node.name, node.id) AS name, "
                "node.description AS description, "
                "node.domain AS domain, node.plugin AS plugin, score "
                "ORDER BY score DESC",
                {"top_k": top_k, "embedding": embedding},
            )
            records = [dict(r) for r in result]
            return json.dumps(records, default=str)
    finally:
        driver.close()
