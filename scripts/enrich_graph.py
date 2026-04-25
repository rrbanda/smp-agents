#!/usr/bin/env python3
"""Enrich the Neo4j graph with LLM-classified relationships.

For each pair of SIMILAR_TO-connected skills, asks the LLM to classify
additional relationship types: DEPENDS_ON, ALTERNATIVE_TO, EXTENDS,
PRECEDES, COMPLEMENTS.

Non-destructive: only creates edges via MERGE, never deletes.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

from shared.model_config import load_config

RELATIONSHIP_TYPES = ["DEPENDS_ON", "ALTERNATIVE_TO", "EXTENDS", "PRECEDES", "COMPLEMENTS"]

CLASSIFIER_PROMPT = """\
You are a relationship classifier for AI agent skills.

Given two skills A and B (with names and descriptions), determine which
relationships exist between them. Return ONLY a JSON array of objects.

Possible relationship types:
- DEPENDS_ON: A functionally requires B to work properly (directional: A->B)
- ALTERNATIVE_TO: A and B solve the same problem interchangeably (bidirectional)
- EXTENDS: A specializes or deepens B (directional: A->B)
- PRECEDES: A should run before B in a pipeline (directional: A->B)
- COMPLEMENTS: A and B work well together but neither requires the other (bidirectional)

Rules:
1. Only include relationships you are confident about (confidence >= 0.6)
2. A pair might have 0 relationships (return empty array [])
3. A pair might have multiple relationships
4. For directional relationships, specify direction as "A_TO_B" or "B_TO_A"
5. For bidirectional relationships, use "BIDIRECTIONAL"

Output format (JSON array, no markdown):
[{"type": "DEPENDS_ON", "direction": "A_TO_B", "confidence": 0.85, "reason": "A requires B's output"}]

Skill A: {name_a}
Description: {desc_a}

Skill B: {name_b}
Description: {desc_b}
"""

BATCH_SIZE = 5
MAX_PAIRS = 2000


_LLM_MAX_RETRIES = 3


def _classify_pair(name_a: str, desc_a: str, name_b: str, desc_b: str, llm_cfg: dict) -> list[dict]:
    """Ask the LLM to classify relationships between two skills."""
    prompt = CLASSIFIER_PROMPT.format(
        name_a=name_a,
        desc_a=desc_a or "No description",
        name_b=name_b,
        desc_b=desc_b or "No description",
    )

    for attempt in range(_LLM_MAX_RETRIES):
        try:
            resp = requests.post(
                f"{llm_cfg['api_base']}/chat/completions",
                json={
                    "model": llm_cfg["id"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 512,
                },
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2**attempt
                logger.warning("LLM returned %d, retrying in %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()

            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]

            relationships = json.loads(content)
            valid = []
            for r in relationships:
                if isinstance(r, dict) and r.get("type") in RELATIONSHIP_TYPES and r.get("confidence", 0) >= 0.6:
                    valid.append(r)
            return valid
        except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError) as e:
            if attempt < _LLM_MAX_RETRIES - 1:
                logger.warning("Classify attempt %d failed for %s <-> %s: %s", attempt + 1, name_a, name_b, e)
                time.sleep(2**attempt)
            else:
                logger.exception(
                    "Failed to classify pair %s <-> %s after %d attempts", name_a, name_b, _LLM_MAX_RETRIES
                )
    return []


def _write_relationship(session, eid_a: str, eid_b: str, rel: dict):
    """MERGE a classified relationship into Neo4j."""
    rel_type = rel["type"]
    direction = rel.get("direction", "BIDIRECTIONAL")
    confidence = rel.get("confidence", 0.7)
    reason = rel.get("reason", "")

    if direction == "B_TO_A":
        eid_a, eid_b = eid_b, eid_a
        direction = "A_TO_B"

    session.run(
        f"MATCH (a:Skill) WHERE elementId(a) = $eid_a "
        f"MATCH (b:Skill) WHERE elementId(b) = $eid_b "
        f"MERGE (a)-[r:{rel_type}]->(b) "
        f"SET r.confidence = $confidence, r.description = $reason, r.direction = $direction",
        eid_a=eid_a,
        eid_b=eid_b,
        confidence=confidence,
        reason=reason,
        direction=direction,
    )


def main():
    cfg = load_config()
    neo4j_cfg = cfg["neo4j"]
    llm_cfg = cfg["model"]["agent"]

    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )

    with driver.session(database=neo4j_cfg.get("database", "neo4j")) as session:
        logger.info("Step 1: Fetch SIMILAR_TO pairs for classification")
        result = session.run(
            "MATCH (a:Skill)-[r:SIMILAR_TO]-(b:Skill) "
            "WHERE elementId(a) < elementId(b) "
            "RETURN elementId(a) AS eid_a, coalesce(a.name, a.id) AS name_a, "
            "coalesce(a.description, '') AS desc_a, "
            "elementId(b) AS eid_b, coalesce(b.name, b.id) AS name_b, "
            "coalesce(b.description, '') AS desc_b, "
            "r.score AS sim_score "
            "ORDER BY r.score DESC "
            f"LIMIT {MAX_PAIRS}"
        )
        pairs = [dict(r) for r in result]
        logger.info("Found %d SIMILAR_TO pairs to classify", len(pairs))

        if not pairs:
            logger.warning("No pairs to classify. Run bootstrap_embeddings.py first.")
            driver.close()
            return

        classified = 0
        edges_created = 0
        for i, pair in enumerate(pairs):
            if i % 50 == 0 and i > 0:
                logger.info("[%d/%d] classified=%d, edges=%d", i, len(pairs), classified, edges_created)

            relationships = _classify_pair(
                pair["name_a"],
                pair["desc_a"],
                pair["name_b"],
                pair["desc_b"],
                llm_cfg,
            )

            for rel in relationships:
                _write_relationship(session, pair["eid_a"], pair["eid_b"], rel)
                edges_created += 1

            classified += 1

            if classified % BATCH_SIZE == 0:
                time.sleep(0.5)

        logger.info("Done. Classified: %d pairs, Created: %d edges", classified, edges_created)

    driver.close()


if __name__ == "__main__":
    main()
