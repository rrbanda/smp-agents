#!/usr/bin/env python3
"""Validate the Neo4j knowledge graph structure and data integrity.

Runs a suite of Cypher-based assertions against the graph and reports
pass/fail for each check.  Can be used standalone or imported by
build_knowledge_graph.py.

Usage:
    python scripts/validate_graph.py
    python scripts/validate_graph.py --check-embeddings
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("validate_graph")

EXPECTED_DOMAINS = {
    "ai-ml", "cloud-infra", "data", "development", "devops",
    "documentation", "general", "identity", "integration",
}
MIN_SKILL_COUNT = 100
SPOT_CHECK_SKILL = "agent-framework-azure-ai-py"
SPOT_CHECK_DOMAIN = "ai-ml"


def _run_query(session: Any, cypher: str, **params: Any) -> list[dict]:
    result = session.run(cypher, **params)
    return [dict(r) for r in result]


def _check(name: str, passed: bool, detail: str = "") -> dict:
    return {"name": name, "passed": passed, "detail": detail}


def validate_graph(
    driver: Any,
    database: str = "neo4j",
    *,
    check_embeddings: bool = False,
) -> dict:
    """Run all validation checks. Returns {"checks": [...], "summary": str}."""
    checks: list[dict] = []

    with driver.session(database=database) as session:
        # 1. Minimum skill count
        rows = _run_query(session, "MATCH (s:Skill) RETURN count(s) AS c")
        skill_count = rows[0]["c"] if rows else 0
        checks.append(_check(
            f"Skill count >= {MIN_SKILL_COUNT}",
            skill_count >= MIN_SKILL_COUNT,
            f"found {skill_count}",
        ))

        # 2. Every catalog-synced skill has BELONGS_TO domain
        rows = _run_query(
            session,
            "MATCH (s:Skill) WHERE s.syncedFromCatalog = true "
            "AND NOT (s)-[:BELONGS_TO]->(:Domain) RETURN count(s) AS c",
        )
        orphan_skills = rows[0]["c"] if rows else 0
        checks.append(_check(
            "All catalog-synced skills have BELONGS_TO domain",
            orphan_skills == 0,
            f"{orphan_skills} skills without domain" if orphan_skills else "",
        ))

        # 3. Every catalog-synced skill has at least one tag
        rows = _run_query(
            session,
            "MATCH (s:Skill) WHERE s.syncedFromCatalog = true "
            "AND NOT (s)-[:TAGGED_WITH]->(:Tag) RETURN count(s) AS c",
        )
        untagged = rows[0]["c"] if rows else 0
        checks.append(_check(
            "All catalog-synced skills have at least one tag",
            untagged == 0,
            f"{untagged} skills without tags" if untagged else "",
        ))

        # 4. Domain count matches expected taxonomy
        rows = _run_query(session, "MATCH (d:Domain) RETURN d.name AS name")
        actual_domains = {r["name"] for r in rows}
        missing = EXPECTED_DOMAINS - actual_domains
        extra = actual_domains - EXPECTED_DOMAINS
        detail_parts = []
        if missing:
            detail_parts.append(f"missing: {missing}")
        if extra:
            detail_parts.append(f"extra: {extra}")
        checks.append(_check(
            f"Domain count matches expected ({len(EXPECTED_DOMAINS)})",
            EXPECTED_DOMAINS.issubset(actual_domains),
            "; ".join(detail_parts) if detail_parts else f"found {len(actual_domains)}",
        ))

        # 5. No orphan Tag nodes
        rows = _run_query(
            session,
            "MATCH (t:Tag) WHERE NOT ()-[:TAGGED_WITH]->(t) RETURN count(t) AS c",
        )
        orphan_tags = rows[0]["c"] if rows else 0
        checks.append(_check(
            "No orphan Tag nodes",
            orphan_tags == 0,
            f"{orphan_tags} orphan tags" if orphan_tags else "",
        ))

        # 6. No orphan Tool nodes
        rows = _run_query(
            session,
            "MATCH (t:Tool) WHERE NOT ()-[:USES_TOOL]->(t) RETURN count(t) AS c",
        )
        orphan_tools = rows[0]["c"] if rows else 0
        checks.append(_check(
            "No orphan Tool nodes",
            orphan_tools == 0,
            f"{orphan_tools} orphan tools" if orphan_tools else "",
        ))

        # 7. Spot check: known skill has correct domain property and BELONGS_TO
        rows = _run_query(
            session,
            "MATCH (s:Skill {name: $name}) "
            "OPTIONAL MATCH (s)-[:BELONGS_TO]->(d:Domain) "
            "RETURN s.domain AS prop_domain, collect(d.name) AS domains",
            name=SPOT_CHECK_SKILL,
        )
        if rows:
            prop_domain = rows[0]["prop_domain"]
            linked_domains = rows[0]["domains"]
            has_correct = (
                prop_domain == SPOT_CHECK_DOMAIN
                and SPOT_CHECK_DOMAIN in linked_domains
            )
            detail = ""
            if not has_correct:
                detail = f"property={prop_domain}, BELONGS_TO={linked_domains}"
            checks.append(_check(
                f"Spot check: {SPOT_CHECK_SKILL} in domain {SPOT_CHECK_DOMAIN}",
                has_correct,
                detail,
            ))
        else:
            checks.append(_check(
                f"Spot check: {SPOT_CHECK_SKILL} exists",
                False,
                "skill not found in graph",
            ))

        # 8. SAME_PLUGIN relationships exist
        rows = _run_query(session, "MATCH ()-[r:SAME_PLUGIN]-() RETURN count(r) AS c")
        plugin_count = rows[0]["c"] if rows else 0
        checks.append(_check(
            "SAME_PLUGIN relationships exist",
            plugin_count > 0,
            f"found {plugin_count}",
        ))

        # 9. USES_TOOL relationships exist
        rows = _run_query(session, "MATCH ()-[r:USES_TOOL]->() RETURN count(r) AS c")
        tool_count = rows[0]["c"] if rows else 0
        checks.append(_check(
            "USES_TOOL relationships exist",
            tool_count > 0,
            f"found {tool_count}",
        ))

        # Embedding checks (optional)
        if check_embeddings:
            # 10. Vector index exists
            try:
                rows = _run_query(
                    session,
                    "SHOW INDEXES YIELD name, type WHERE name = 'skill_embedding_idx' "
                    "RETURN name, type",
                )
                checks.append(_check(
                    "Vector index skill_embedding_idx exists",
                    len(rows) > 0,
                    "" if rows else "index not found",
                ))
            except Exception:
                checks.append(_check(
                    "Vector index skill_embedding_idx exists",
                    False,
                    "SHOW INDEXES not supported or failed",
                ))

            # 11. Skills have embeddings
            rows = _run_query(
                session,
                "MATCH (s:Skill) WHERE s.embedding IS NOT NULL RETURN count(s) AS c",
            )
            emb_count = rows[0]["c"] if rows else 0
            checks.append(_check(
                "Skills have embeddings",
                emb_count > 0,
                f"{emb_count}/{skill_count} with embeddings",
            ))

            # 12. SIMILAR_TO edges exist
            rows = _run_query(
                session, "MATCH ()-[r:SIMILAR_TO]-() RETURN count(r) AS c"
            )
            sim_count = rows[0]["c"] if rows else 0
            checks.append(_check(
                "SIMILAR_TO edges exist",
                sim_count > 0,
                f"found {sim_count}",
            ))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    summary = f"{passed}/{total} checks passed"

    return {"checks": checks, "summary": summary, "passed": passed, "total": total}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Neo4j knowledge graph")
    parser.add_argument(
        "--check-embeddings", action="store_true",
        help="Also validate vector embeddings and SIMILAR_TO edges",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    from neo4j import GraphDatabase

    from shared.model_config import get_neo4j_config

    neo4j_cfg = get_neo4j_config()
    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )
    database = neo4j_cfg.get("database", "neo4j")

    results = validate_graph(driver, database, check_embeddings=args.check_embeddings)
    driver.close()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print()
        print("=" * 50)
        print("  Knowledge Graph Validation")
        print("=" * 50)
        for check in results["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  [{status}] {check['name']}")
            if not check["passed"] and check.get("detail"):
                print(f"         {check['detail']}")
        print()
        print(f"  Result: {results['summary']}")
        print("=" * 50)
        print()

    if results["passed"] < results["total"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
