#!/usr/bin/env python3
"""Build a complete knowledge graph from the Skill Catalog API into Neo4j.

Orchestrates the full pipeline:
  1. Trigger catalog sync (re-index from OCI registry)
  2. Fetch all skills from catalog API
  3. MERGE Skill/Domain/Tag/Tool nodes + relationships into Neo4j
  4. Post-process SAME_PLUGIN edges (single pass)
  5. Bootstrap vector embeddings + SIMILAR_TO edges (optional)
  6. Validate the resulting graph

Usage:
    python scripts/build_knowledge_graph.py
    python scripts/build_knowledge_graph.py --skip-embeddings
    python scripts/build_knowledge_graph.py --skip-validation --dry-run
    python scripts/build_knowledge_graph.py --no-tls-verify
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("build_knowledge_graph")

_TIMEOUT = 30
_TLS_VERIFY = True


def _get_tls_ctx() -> ssl.SSLContext:
    if _TLS_VERIFY:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_get(url: str, *, accept: str = "application/json") -> Any:
    req = urllib.request.Request(url, headers={"Accept": accept})
    resp = urllib.request.urlopen(req, timeout=_TIMEOUT, context=_get_tls_ctx())
    body = resp.read().decode("utf-8")
    if "json" in resp.headers.get("Content-Type", ""):
        return json.loads(body)
    return body


def _http_post(url: str) -> Any:
    req = urllib.request.Request(url, method="POST")
    resp = urllib.request.urlopen(req, timeout=_TIMEOUT, context=_get_tls_ctx())
    return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Step 1: Trigger catalog sync
# ---------------------------------------------------------------------------

def trigger_catalog_sync(base_url: str) -> None:
    url = f"{base_url.rstrip('/')}/api/v1/sync"
    logger.info("Triggering catalog sync: POST %s", url)
    try:
        result = _http_post(url)
        logger.info("Sync response: %s", result)
    except Exception as exc:
        logger.warning("Could not trigger sync (non-fatal): %s", exc)

    logger.info("Waiting 10s for catalog to re-index...")
    time.sleep(10)


# ---------------------------------------------------------------------------
# Step 2: Fetch skills from catalog
# ---------------------------------------------------------------------------

def fetch_all_skills(base_url: str) -> list[dict]:
    all_skills: list[dict] = []
    page = 1
    per_page = 100
    while True:
        url = f"{base_url.rstrip('/')}/api/v1/skills?page={page}&per_page={per_page}"
        data = _http_get(url)
        if not isinstance(data, dict):
            logger.error("Unexpected API response type: %s", type(data).__name__)
            break
        skills = data.get("data", [])
        all_skills.extend(skills)
        if len(skills) < per_page:
            break
        page += 1
    return all_skills


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def parse_tags(tags_json: str) -> list[str]:
    if not tags_json:
        return []
    try:
        tags = json.loads(tags_json)
        return tags if isinstance(tags, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def build_skill_data(skill: dict) -> dict:
    """Transform a catalog API skill dict into the shape needed for Neo4j upsert."""
    tags = parse_tags(skill.get("tags_json", ""))
    bundle_skills = (
        skill.get("bundle_skills", "").split(",") if skill.get("bundle_skills") else []
    )

    return {
        "name": skill.get("display_name") or skill.get("name", ""),
        "description": skill.get("description", ""),
        "namespace": skill.get("namespace", ""),
        "version": skill.get("version", ""),
        "status": skill.get("status", ""),
        "display_name": skill.get("display_name") or skill.get("name", ""),
        "authors": skill.get("authors", ""),
        "license": skill.get("license", ""),
        "compatibility": skill.get("compatibility", ""),
        "category": skill.get("category", skill.get("compatibility", "")),
        "plugin": skill.get("plugin", ""),
        "lang": skill.get("lang", ""),
        "tools": skill.get("tools") or [],
        "bundle": skill.get("bundle", False),
        "word_count": skill.get("word_count", 0),
        "digest": skill.get("digest", ""),
        "repository": skill.get("repository", ""),
        "tags": [t for t in tags if t],
        "bundle_skills_list": [b.strip() for b in bundle_skills if b.strip()],
    }


# ---------------------------------------------------------------------------
# Step 3: MERGE into Neo4j
# ---------------------------------------------------------------------------

def upsert_skill(tx: Any, skill_data: dict) -> None:
    name = skill_data.get("name")
    if not name:
        return

    tx.run(
        """
        MERGE (s:Skill {name: $name})
        SET s.description = $description,
            s.domain = $domain,
            s.namespace = $namespace,
            s.version = $version,
            s.status = $status,
            s.author = $author,
            s.license = $license,
            s.compatibility = $compatibility,
            s.category = $category,
            s.plugin = $plugin,
            s.lang = $lang,
            s.displayName = $displayName,
            s.bundle = $bundle,
            s.wordCount = $wordCount,
            s.digest = $digest,
            s.repository = $repository,
            s.syncedFromCatalog = true
        """,
        name=name,
        description=skill_data.get("description", ""),
        domain=skill_data.get("namespace", ""),
        namespace=skill_data.get("namespace", ""),
        version=skill_data.get("version", ""),
        status=skill_data.get("status", ""),
        author=skill_data.get("authors", ""),
        license=skill_data.get("license", ""),
        compatibility=skill_data.get("compatibility", ""),
        category=skill_data.get("category", ""),
        plugin=skill_data.get("plugin", ""),
        lang=skill_data.get("lang", ""),
        displayName=skill_data.get("display_name", name),
        bundle=skill_data.get("bundle", False),
        wordCount=skill_data.get("word_count", 0),
        digest=skill_data.get("digest", ""),
        repository=skill_data.get("repository", ""),
    ).consume()

    if skill_data.get("prompt"):
        tx.run(
            "MATCH (s:Skill {name: $name}) SET s.prompt = $prompt",
            name=name,
            prompt=skill_data["prompt"],
        ).consume()

    # Delete stale edges before re-creating from current data
    tx.run(
        "MATCH (s:Skill {name: $name})-[r:TAGGED_WITH]->() DELETE r",
        name=name,
    ).consume()
    tx.run(
        "MATCH (s:Skill {name: $name})-[r:BELONGS_TO]->() DELETE r",
        name=name,
    ).consume()
    tx.run(
        "MATCH (s:Skill {name: $name})-[r:USES_TOOL]->() DELETE r",
        name=name,
    ).consume()

    tags = skill_data.get("tags", [])
    if tags:
        tx.run(
            """
            MATCH (s:Skill {name: $name})
            UNWIND $tags AS tag_name
            MERGE (t:Tag {name: tag_name})
            MERGE (s)-[:TAGGED_WITH]->(t)
            """,
            name=name,
            tags=tags,
        ).consume()

    ns = skill_data.get("namespace", "")
    if ns:
        tx.run(
            """
            MERGE (d:Domain {name: $domain})
            WITH d
            MATCH (s:Skill {name: $skill_name})
            MERGE (s)-[:BELONGS_TO]->(d)
            """,
            domain=ns,
            skill_name=name,
        ).consume()

    tools = [t for t in skill_data.get("tools", []) if t]
    if tools:
        tx.run(
            """
            MATCH (s:Skill {name: $name})
            UNWIND $tools AS tool_name
            MERGE (t:Tool {name: tool_name})
            MERGE (s)-[:USES_TOOL]->(t)
            """,
            name=name,
            tools=tools,
        ).consume()

    bundle_list = skill_data.get("bundle_skills_list", [])
    if bundle_list:
        tx.run(
            """
            MATCH (s:Skill {name: $parent})
            UNWIND $bundled_names AS bname
            MERGE (b:Skill {name: bname})
            MERGE (s)-[:BUNDLES]->(b)
            """,
            parent=name,
            bundled_names=bundle_list,
        ).consume()


def create_same_plugin_edges(driver: Any, database: str) -> int:
    """Single-pass SAME_PLUGIN edge creation -- replaces O(n^2) per-skill approach."""
    with driver.session(database=database) as session:
        session.run(
            "MATCH ()-[r:SAME_PLUGIN]-() DELETE r"
        ).consume()

        result = session.run(
            """
            MATCH (a:Skill), (b:Skill)
            WHERE a.plugin IS NOT NULL AND a.plugin <> ''
              AND a.plugin = b.plugin AND id(a) < id(b)
            MERGE (a)-[:SAME_PLUGIN]-(b)
            RETURN count(*) AS created
            """
        )
        record = result.single()
        return record["created"] if record else 0


def sync_to_neo4j(
    skills: list[dict], driver: Any, database: str
) -> tuple[int, int]:
    synced = 0
    failed = 0

    with driver.session(database=database) as session:
        for i, skill in enumerate(skills, 1):
            if i % 50 == 0:
                logger.info("  [%d/%d] synced=%d failed=%d", i, len(skills), synced, failed)

            sd = build_skill_data(skill)
            try:
                session.execute_write(upsert_skill, sd)
                synced += 1
            except Exception:
                logger.exception(
                    "Error syncing %s",
                    skill.get("display_name") or skill.get("name", "?"),
                )
                failed += 1

    return synced, failed


# ---------------------------------------------------------------------------
# Step 4: Bootstrap embeddings (optional)
# ---------------------------------------------------------------------------

def bootstrap_embeddings(driver: Any, database: str) -> dict[str, int]:
    """Create vector index, embed all skills, compute SIMILAR_TO edges."""
    try:
        import requests
        from shared.model_config import get_embedding_config
    except ImportError:
        logger.warning("requests or shared.model_config not available; skipping embeddings")
        return {"embedded": 0, "similar_to": 0}

    embed_cfg = get_embedding_config()
    dimension = embed_cfg.get("dimension", 768)
    embed_failures = 0

    with driver.session(database=database) as session:
        logger.info("  Creating vector index (%d dims, cosine)", dimension)
        session.run("DROP INDEX skill_embedding_idx IF EXISTS")
        session.run(
            "CREATE VECTOR INDEX skill_embedding_idx IF NOT EXISTS "
            "FOR (s:Skill) ON (s.embedding) "
            f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, "
            f"`vector.similarity_function`: 'cosine'}}}}"
        )

        result = session.run(
            "MATCH (s:Skill) "
            "RETURN elementId(s) AS eid, coalesce(s.name, s.id) AS identifier, "
            "coalesce(s.description, '') AS description "
            "ORDER BY identifier"
        )
        skills = [dict(r) for r in result]
        logger.info("  %d skills to embed", len(skills))

        if not skills:
            return {"embedded": 0, "similar_to": 0}

        batch_size = 32
        embedded = 0
        for i in range(0, len(skills), batch_size):
            batch = skills[i : i + batch_size]
            texts = [
                f"{s['identifier']}: {s['description']}" if s["description"] else s["identifier"]
                for s in batch
            ]
            try:
                resp = requests.post(
                    f"{embed_cfg['api_base']}/embeddings",
                    json={"model": embed_cfg["id"], "input": texts},
                    headers={"Content-Type": "application/json"},
                    timeout=60,
                )
                resp.raise_for_status()
                embeddings = [
                    item["embedding"]
                    for item in sorted(resp.json()["data"], key=lambda x: x["index"])
                ]
            except Exception:
                logger.exception("Embedding batch %d-%d failed", i, i + len(batch))
                embed_failures += 1
                continue

            for skill, embedding in zip(batch, embeddings):
                session.run(
                    "MATCH (s:Skill) WHERE elementId(s) = $eid SET s.embedding = $embedding",
                    eid=skill["eid"],
                    embedding=embedding,
                )
            embedded += len(batch)

        if embed_failures:
            logger.error("  %d embedding batches failed out of %d",
                         embed_failures, (len(skills) + batch_size - 1) // batch_size)
        logger.info("  Embedded %d/%d skills", embedded, len(skills))
        time.sleep(2)

        skills_emb = [
            dict(r)
            for r in session.run(
                "MATCH (s:Skill) WHERE s.embedding IS NOT NULL "
                "RETURN elementId(s) AS eid, s.embedding AS embedding"
            )
        ]
        similar_count = 0
        similar_failures = 0
        top_k = 5
        threshold = 0.7
        for skill in skills_emb:
            try:
                neighbors = [
                    dict(r)
                    for r in session.run(
                        "CALL db.index.vector.queryNodes('skill_embedding_idx', $top_k, $embedding) "
                        "YIELD node, score "
                        "WHERE elementId(node) <> $self_eid AND score >= $threshold "
                        "RETURN elementId(node) AS eid, score",
                        top_k=top_k + 1,
                        embedding=skill["embedding"],
                        self_eid=skill["eid"],
                        threshold=threshold,
                    )
                ]
            except Exception:
                similar_failures += 1
                logger.debug("Vector query failed for %s", skill["eid"])
                continue

            for neighbor in neighbors:
                try:
                    session.run(
                        "MATCH (a:Skill) WHERE elementId(a) = $a_eid "
                        "MATCH (b:Skill) WHERE elementId(b) = $b_eid "
                        "MERGE (a)-[r:SIMILAR_TO]-(b) SET r.score = $score",
                        a_eid=skill["eid"],
                        b_eid=neighbor["eid"],
                        score=neighbor["score"],
                    )
                    similar_count += 1
                except Exception:
                    similar_failures += 1

        if similar_failures:
            logger.error("  %d SIMILAR_TO operations failed", similar_failures)
        logger.info("  Created %d SIMILAR_TO edges", similar_count)

    return {"embedded": embedded, "similar_to": similar_count}


# ---------------------------------------------------------------------------
# Step 5: Validate graph (imported from validate_graph.py)
# ---------------------------------------------------------------------------

def run_validation(driver: Any, database: str, check_embeddings: bool) -> dict:
    """Run graph validation checks. Returns results dict."""
    try:
        from scripts.validate_graph import validate_graph
        return validate_graph(driver, database, check_embeddings=check_embeddings)
    except ImportError:
        validate_mod = Path(__file__).parent / "validate_graph.py"
        if validate_mod.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("validate_graph", validate_mod)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod.validate_graph(driver, database, check_embeddings=check_embeddings)
        logger.warning("validate_graph.py not found; skipping validation")
        return {"error": "validate_graph.py not found"}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def collect_stats(driver: Any, database: str) -> dict[str, int]:
    queries = {
        "skills": "MATCH (s:Skill) RETURN count(s) AS c",
        "domains": "MATCH (d:Domain) RETURN count(d) AS c",
        "tags": "MATCH (t:Tag) RETURN count(t) AS c",
        "tools": "MATCH (t:Tool) RETURN count(t) AS c",
        "belongs_to": "MATCH ()-[r:BELONGS_TO]->() RETURN count(r) AS c",
        "tagged_with": "MATCH ()-[r:TAGGED_WITH]->() RETURN count(r) AS c",
        "uses_tool": "MATCH ()-[r:USES_TOOL]->() RETURN count(r) AS c",
        "same_plugin": "MATCH ()-[r:SAME_PLUGIN]-() RETURN count(r) AS c",
        "similar_to": "MATCH ()-[r:SIMILAR_TO]-() RETURN count(r) AS c",
        "bundles": "MATCH ()-[r:BUNDLES]->() RETURN count(r) AS c",
    }
    stats: dict[str, int] = {}
    with driver.session(database=database) as session:
        for key, cypher in queries.items():
            result = session.run(cypher)
            stats[key] = result.single()["c"]
    return stats


def print_report(stats: dict[str, int], validation: dict | None) -> None:
    print()
    print("=" * 50)
    print("  Knowledge Graph Build Report")
    print("=" * 50)
    print(f"  Skills synced:      {stats.get('skills', 0)}")
    print(f"  Domains created:    {stats.get('domains', 0)}")
    print(f"  Tags created:       {stats.get('tags', 0)}")
    print(f"  Tools created:      {stats.get('tools', 0)}")
    print(f"  BELONGS_TO edges:   {stats.get('belongs_to', 0)}")
    print(f"  TAGGED_WITH edges:  {stats.get('tagged_with', 0)}")
    print(f"  USES_TOOL edges:    {stats.get('uses_tool', 0)}")
    print(f"  SAME_PLUGIN edges:  {stats.get('same_plugin', 0)}")
    print(f"  SIMILAR_TO edges:   {stats.get('similar_to', 0)}")
    print(f"  BUNDLES edges:      {stats.get('bundles', 0)}")
    print()

    if validation and "error" not in validation:
        checks = validation.get("checks", [])
        passed = sum(1 for c in checks if c["passed"])
        total = len(checks)
        print("  Validation Results")
        print("  " + "-" * 40)
        for check in checks:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  [{status}] {check['name']}")
            if not check["passed"] and check.get("detail"):
                print(f"         {check['detail']}")
        print()
        print(f"  Result: {passed}/{total} checks passed")
    elif validation:
        print(f"  Validation skipped: {validation.get('error', 'unknown')}")

    print("=" * 50)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global _TLS_VERIFY

    parser = argparse.ArgumentParser(
        description="Build complete knowledge graph from Skill Catalog into Neo4j"
    )
    parser.add_argument(
        "--skip-sync", action="store_true",
        help="Skip triggering catalog sync (use existing catalog data)",
    )
    parser.add_argument(
        "--skip-embeddings", action="store_true",
        help="Skip vector embedding bootstrap (requires embedding endpoint)",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Skip graph validation checks",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and display skills but do not write to Neo4j",
    )
    parser.add_argument(
        "--no-tls-verify", action="store_true",
        help="Disable TLS certificate verification for catalog API (insecure)",
    )
    args = parser.parse_args()

    if args.no_tls_verify:
        _TLS_VERIFY = False
        logger.warning("TLS verification disabled (--no-tls-verify)")

    from shared.model_config import get_catalog_config, get_neo4j_config

    catalog_cfg = get_catalog_config()
    neo4j_cfg = get_neo4j_config()
    base_url = catalog_cfg["base_url"]
    database = neo4j_cfg.get("database", "neo4j")

    logger.info("Catalog API: %s", base_url)
    logger.info("Neo4j URI:   %s", neo4j_cfg["uri"])

    # Step 1: Trigger catalog sync
    if not args.skip_sync and not args.dry_run:
        trigger_catalog_sync(base_url)

    # Step 2: Fetch all skills
    logger.info("Step 2: Fetching all skills from catalog...")
    skills = fetch_all_skills(base_url)
    logger.info("Found %d skills in catalog", len(skills))

    if not skills:
        logger.error("No skills found. Check catalog API URL and status.")
        sys.exit(1)

    if args.dry_run:
        logger.info("Dry-run mode: would sync %d skills to Neo4j", len(skills))
        for s in skills[:5]:
            logger.info("  - %s (%s)",
                        s.get("display_name") or s.get("name", "?"),
                        s.get("namespace", "?"))
        if len(skills) > 5:
            logger.info("  ... and %d more", len(skills) - 5)
        return

    # Step 3: Sync to Neo4j
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )

    try:
        logger.info("Step 3: Syncing %d skills to Neo4j...", len(skills))
        synced, failed = sync_to_neo4j(skills, driver, database)
        logger.info("Synced: %d, Failed: %d", synced, failed)

        # Step 3b: SAME_PLUGIN post-process (single pass)
        logger.info("Step 3b: Creating SAME_PLUGIN edges (single pass)...")
        plugin_edges = create_same_plugin_edges(driver, database)
        logger.info("Created %d SAME_PLUGIN edges", plugin_edges)

        # Step 4: Embeddings
        embed_stats = {"embedded": 0, "similar_to": 0}
        if not args.skip_embeddings:
            logger.info("Step 4: Bootstrapping embeddings...")
            embed_stats = bootstrap_embeddings(driver, database)
        else:
            logger.info("Step 4: Skipped (--skip-embeddings)")

        # Step 5: Validate
        validation = None
        if not args.skip_validation:
            logger.info("Step 5: Validating graph...")
            validation = run_validation(driver, database, check_embeddings=not args.skip_embeddings)
        else:
            logger.info("Step 5: Skipped (--skip-validation)")

        # Step 6: Report
        stats = collect_stats(driver, database)
        stats.update(embed_stats)
        print_report(stats, validation)

    finally:
        driver.close()

    if validation and "error" not in validation:
        checks = validation.get("checks", [])
        if not all(c["passed"] for c in checks):
            sys.exit(1)


if __name__ == "__main__":
    main()
