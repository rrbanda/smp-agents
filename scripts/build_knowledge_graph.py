#!/usr/bin/env python3
"""Build a complete knowledge graph from the Skill Catalog API into Neo4j.

Orchestrates the full pipeline:
  1. Trigger catalog sync (re-index from OCI registry)
  2. Fetch all skills from catalog API
  3. Fetch SKILL.md content for enriched metadata
  4. MERGE Skill/Domain/Tag/Tool nodes + relationships into Neo4j
  5. Bootstrap vector embeddings + SIMILAR_TO edges (optional)
  6. Validate the resulting graph

Usage:
    python scripts/build_knowledge_graph.py
    python scripts/build_knowledge_graph.py --skip-embeddings
    python scripts/build_knowledge_graph.py --skip-validation --dry-run
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
_TLS_CTX: ssl.SSLContext | None = None


def _get_tls_ctx() -> ssl.SSLContext:
    global _TLS_CTX
    if _TLS_CTX is None:
        _TLS_CTX = ssl.create_default_context()
        _TLS_CTX.check_hostname = False
        _TLS_CTX.verify_mode = ssl.CERT_NONE
    return _TLS_CTX


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
# Step 2+3: Fetch skills + content from catalog
# ---------------------------------------------------------------------------

def fetch_all_skills(base_url: str) -> list[dict]:
    all_skills: list[dict] = []
    page = 1
    per_page = 100
    while True:
        url = f"{base_url.rstrip('/')}/api/v1/skills?page={page}&per_page={per_page}"
        data = _http_get(url)
        skills = data.get("data", [])
        all_skills.extend(skills)
        pagination = data.get("pagination", {})
        total = pagination.get("total", 0)
        if len(all_skills) >= total or not skills:
            break
        page += 1
    return all_skills


def fetch_skill_content(base_url: str, repository: str, tag: str) -> str | None:
    """Fetch SKILL.md content using repository/tag path."""
    try:
        url = f"{base_url.rstrip('/')}/api/v1/skills/{repository}/{tag}/content"
        return _http_get(url, accept="text/markdown")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None


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


def build_skill_data(skill: dict, base_url: str, fetch_content: bool) -> dict:
    """Transform a catalog API skill dict into the shape needed for Neo4j upsert.

    In a single-repo setup (e.g. quay.io/rbrhssa/skills) every skill shares
    the same API ``name`` ("skills"), so the per-version content endpoint is
    ambiguous.  Metadata is taken from the list API fields instead; content
    fetch is only used for the SKILL.md prompt text when the display_name can
    serve as a unique key (via the tag).
    """
    tags = parse_tags(skill.get("tags_json", ""))
    bundle_skills = (
        skill.get("bundle_skills", "").split(",") if skill.get("bundle_skills") else []
    )

    sd: dict[str, Any] = {
        "name": skill.get("display_name", skill["name"]),
        "description": skill.get("description", ""),
        "namespace": skill.get("namespace", ""),
        "version": skill.get("version", ""),
        "status": skill.get("status", ""),
        "display_name": skill.get("display_name", skill["name"]),
        "authors": skill.get("authors", ""),
        "license": skill.get("license", ""),
        "compatibility": skill.get("compatibility", ""),
        "category": skill.get("compatibility", ""),
        "plugin": skill.get("plugin", ""),
        "lang": skill.get("lang", ""),
        "tools": skill.get("tools", []),
        "bundle": skill.get("bundle", False),
        "word_count": skill.get("word_count", 0),
        "digest": skill.get("digest", ""),
        "repository": skill.get("repository", ""),
        "tags": tags,
        "bundle_skills_list": bundle_skills,
    }

    if fetch_content and skill.get("tag"):
        repo = skill.get("repository", "")
        tag = skill.get("tag", "")
        if repo and tag:
            content = fetch_skill_content(base_url, repo, tag)
            if content:
                sd["prompt"] = content
                fm = parse_frontmatter(content)
                if fm.get("plugin") and not sd["plugin"]:
                    sd["plugin"] = fm["plugin"]
                if fm.get("lang") and not sd["lang"]:
                    sd["lang"] = fm["lang"]
                if fm.get("tools") and not sd["tools"]:
                    sd["tools"] = fm["tools"]
                if fm.get("category") and not sd["category"]:
                    sd["category"] = fm["category"]
                if fm.get("tags") and not tags:
                    sd["tags"] = fm["tags"]

    return sd


# ---------------------------------------------------------------------------
# Step 4: MERGE into Neo4j
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

    for tag in skill_data.get("tags", []):
        tx.run(
            """
            MERGE (t:Tag {name: $tag})
            WITH t
            MATCH (s:Skill {name: $skill_name})
            MERGE (s)-[:TAGGED_WITH]->(t)
            """,
            tag=tag,
            skill_name=name,
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

    for tool in skill_data.get("tools", []):
        if tool:
            tx.run(
                """
                MERGE (t:Tool {name: $tool})
                WITH t
                MATCH (s:Skill {name: $skill_name})
                MERGE (s)-[:USES_TOOL]->(t)
                """,
                tool=tool,
                skill_name=name,
            ).consume()

    plugin = skill_data.get("plugin", "")
    if plugin:
        tx.run(
            """
            MATCH (s:Skill {name: $skill_name})
            MATCH (other:Skill)
            WHERE other.plugin = $plugin AND other.name <> $skill_name
            MERGE (s)-[:SAME_PLUGIN]-(other)
            """,
            skill_name=name,
            plugin=plugin,
        ).consume()

    for bundled in skill_data.get("bundle_skills_list", []):
        if bundled:
            tx.run(
                """
                MERGE (b:Skill {name: $bundled})
                WITH b
                MATCH (s:Skill {name: $parent})
                MERGE (s)-[:BUNDLES]->(b)
                """,
                parent=name,
                bundled=bundled.strip(),
            ).consume()


def sync_to_neo4j(
    skills: list[dict], base_url: str, driver: Any, database: str
) -> tuple[int, int]:
    synced = 0
    failed = 0
    for i, skill in enumerate(skills, 1):
        if i % 50 == 0:
            logger.info("  [%d/%d] synced=%d failed=%d", i, len(skills), synced, failed)

        sd = build_skill_data(skill, base_url, fetch_content=False)
        try:
            with driver.session(database=database) as session:
                session.execute_write(upsert_skill, sd)
            synced += 1
        except Exception:
            logger.exception("Error syncing %s", skill.get("display_name", skill.get("name", "?")))
            failed += 1

    return synced, failed


# ---------------------------------------------------------------------------
# Step 5: Bootstrap embeddings (optional)
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
                continue

            for skill, embedding in zip(batch, embeddings, strict=True):
                session.run(
                    "MATCH (s:Skill) WHERE elementId(s) = $eid SET s.embedding = $embedding",
                    eid=skill["eid"],
                    embedding=embedding,
                )
            embedded += len(batch)

        logger.info("  Embedded %d skills", embedded)
        time.sleep(2)

        skills_emb = [
            dict(r)
            for r in session.run(
                "MATCH (s:Skill) WHERE s.embedding IS NOT NULL "
                "RETURN elementId(s) AS eid, s.embedding AS embedding"
            )
        ]
        similar_count = 0
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
                    pass

        logger.info("  Created %d SIMILAR_TO edges", similar_count)

    return {"embedded": embedded, "similar_to": similar_count}


# ---------------------------------------------------------------------------
# Step 6: Validate graph (imported from validate_graph.py)
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
# Step 7: Report
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
    args = parser.parse_args()

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
            logger.info("  - %s (%s)", s.get("display_name", s["name"]), s.get("namespace", "?"))
        if len(skills) > 5:
            logger.info("  ... and %d more", len(skills) - 5)
        return

    # Step 3+4: Sync to Neo4j (includes content fetch)
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )

    logger.info("Step 3-4: Syncing %d skills to Neo4j...", len(skills))
    synced, failed = sync_to_neo4j(skills, base_url, driver, database)
    logger.info("Synced: %d, Failed: %d", synced, failed)

    # Step 5: Embeddings
    embed_stats = {"embedded": 0, "similar_to": 0}
    if not args.skip_embeddings:
        logger.info("Step 5: Bootstrapping embeddings...")
        embed_stats = bootstrap_embeddings(driver, database)
    else:
        logger.info("Step 5: Skipped (--skip-embeddings)")

    # Step 6: Validate
    validation = None
    if not args.skip_validation:
        logger.info("Step 6: Validating graph...")
        validation = run_validation(driver, database, check_embeddings=not args.skip_embeddings)
    else:
        logger.info("Step 6: Skipped (--skip-validation)")

    # Step 7: Report
    stats = collect_stats(driver, database)
    stats.update(embed_stats)
    print_report(stats, validation)

    driver.close()

    if validation and "error" not in validation:
        checks = validation.get("checks", [])
        all_passed = all(c["passed"] for c in checks)
        if not all_passed:
            sys.exit(1)


if __name__ == "__main__":
    main()
