#!/usr/bin/env python3
"""Bootstrap vector embeddings for all Skill nodes in Neo4j.

1. Drops the existing vector index (may be wrong dimension)
2. Recreates at 768 dimensions (nomic-embed-text-v1-5)
3. Embeds all skills in batches via LlamaStack /v1/embeddings
4. Writes embeddings back to Neo4j
5. Computes SIMILAR_TO edges for top-k neighbors
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.model_config import get_neo4j_config, get_embedding_config

BATCH_SIZE = 32
SIMILAR_TOP_K = 5
SIMILAR_THRESHOLD = 0.7


def _get_all_skills(session) -> list[dict]:
    result = session.run(
        "MATCH (s:Skill) "
        "RETURN elementId(s) AS eid, coalesce(s.name, s.id) AS identifier, "
        "coalesce(s.description, '') AS description "
        "ORDER BY identifier"
    )
    return [dict(r) for r in result]


def _embed_batch(texts: list[str], cfg: dict) -> list[list[float]]:
    resp = requests.post(
        f"{cfg['api_base']}/embeddings",
        json={"model": cfg["id"], "input": texts},
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


def main():
    neo4j_cfg = get_neo4j_config()
    embed_cfg = get_embedding_config()
    dimension = embed_cfg.get("dimension", 768)

    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )

    with driver.session(database=neo4j_cfg.get("database", "neo4j")) as session:
        print("Step 1: Drop existing vector index (if any)")
        try:
            session.run("DROP INDEX skill_embedding_idx IF EXISTS")
            print("  Dropped skill_embedding_idx")
        except Exception:
            print("  No existing index to drop")

        try:
            session.run("DROP INDEX skill_embedding IF EXISTS")
            print("  Dropped skill_embedding")
        except Exception:
            pass

        print(f"Step 2: Create vector index ({dimension} dimensions, COSINE)")
        session.run(
            "CREATE VECTOR INDEX skill_embedding_idx IF NOT EXISTS "
            "FOR (s:Skill) ON (s.embedding) "
            f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}"
        )
        print("  Index created")

        print("Step 3: Fetch all skills")
        skills = _get_all_skills(session)
        print(f"  Found {len(skills)} skills")

        if not skills:
            print("No skills to embed. Run sync_oci_skills.py first.")
            driver.close()
            return

        print(f"Step 4: Embed in batches of {BATCH_SIZE}")
        embedded_count = 0
        for i in range(0, len(skills), BATCH_SIZE):
            batch = skills[i : i + BATCH_SIZE]
            texts = [
                f"{s['identifier']}: {s['description']}" if s["description"]
                else s["identifier"]
                for s in batch
            ]

            try:
                embeddings = _embed_batch(texts, embed_cfg)
            except Exception as e:
                print(f"  ERROR embedding batch {i}-{i+len(batch)}: {e}")
                continue

            for skill, embedding in zip(batch, embeddings):
                session.run(
                    "MATCH (s:Skill) WHERE elementId(s) = $eid "
                    "SET s.embedding = $embedding",
                    eid=skill["eid"],
                    embedding=embedding,
                )

            embedded_count += len(batch)
            if (i // BATCH_SIZE + 1) % 10 == 0:
                print(f"  [{embedded_count}/{len(skills)}] embedded")

        print(f"  Embedded {embedded_count} skills")

        time.sleep(2)

        print(f"Step 5: Compute SIMILAR_TO edges (top-{SIMILAR_TOP_K}, threshold {SIMILAR_THRESHOLD})")
        skills_with_embeddings = session.run(
            "MATCH (s:Skill) WHERE s.embedding IS NOT NULL "
            "RETURN elementId(s) AS eid, coalesce(s.name, s.id) AS identifier, s.embedding AS embedding"
        )
        skills_list = [dict(r) for r in skills_with_embeddings]
        print(f"  {len(skills_list)} skills with embeddings")

        similar_count = 0
        for idx, skill in enumerate(skills_list):
            if idx % 200 == 0 and idx > 0:
                print(f"  [{idx}/{len(skills_list)}] SIMILAR_TO edges created: {similar_count}")

            try:
                result = session.run(
                    "CALL db.index.vector.queryNodes('skill_embedding_idx', $top_k, $embedding) "
                    "YIELD node, score "
                    "WHERE elementId(node) <> $self_eid AND score >= $threshold "
                    "RETURN elementId(node) AS eid, score",
                    top_k=SIMILAR_TOP_K + 1,
                    embedding=skill["embedding"],
                    self_eid=skill["eid"],
                    threshold=SIMILAR_THRESHOLD,
                )
                neighbors = [dict(r) for r in result]
            except Exception:
                continue

            for neighbor in neighbors:
                for attempt in range(3):
                    try:
                        session.run(
                            "MATCH (a:Skill) WHERE elementId(a) = $a_eid "
                            "MATCH (b:Skill) WHERE elementId(b) = $b_eid "
                            "MERGE (a)-[r:SIMILAR_TO]-(b) "
                            "SET r.score = $score",
                            a_eid=skill["eid"],
                            b_eid=neighbor["eid"],
                            score=neighbor["score"],
                        )
                        similar_count += 1
                        break
                    except Exception:
                        if attempt < 2:
                            time.sleep(1)

        print(f"  Created {similar_count} SIMILAR_TO edges")

    driver.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
