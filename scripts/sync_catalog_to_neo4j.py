#!/usr/bin/env python3
"""Sync skills from the Skill Catalog API into Neo4j (non-destructive).

Fetches all skills from the catalog REST API, optionally pulls SKILL.md
content, and MERGEs them into Neo4j as Skill nodes with associated
Tag, Domain, and relationship edges.

NEVER deletes existing nodes -- only creates or updates.

Usage:
    python scripts/sync_catalog_to_neo4j.py [--with-content] [--batch-size 50]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

from neo4j import GraphDatabase

from shared.model_config import get_catalog_config, get_neo4j_config

_TIMEOUT = 30


def _catalog_get(base_url: str, path: str, *, accept: str = "application/json"):
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(url, headers={"Accept": accept})
    resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
    body = resp.read().decode("utf-8")
    if "json" in resp.headers.get("Content-Type", ""):
        return json.loads(body)
    return body


def _fetch_all_skills(base_url: str) -> list[dict]:
    """Paginate through all skills from the catalog API."""
    all_skills: list[dict] = []
    page = 1
    per_page = 100

    while True:
        data = _catalog_get(base_url, f"/api/v1/skills?page={page}&per_page={per_page}")
        skills = data.get("data", [])
        all_skills.extend(skills)

        pagination = data.get("pagination", {})
        total = pagination.get("total", 0)
        if len(all_skills) >= total or not skills:
            break
        page += 1

    return all_skills


def _fetch_skill_content(base_url: str, namespace: str, name: str, version: str) -> str | None:
    """Fetch SKILL.md content for a specific skill version."""
    try:
        return _catalog_get(
            base_url,
            f"/api/v1/skills/{namespace}/{name}/versions/{version}/content",
            accept="text/markdown",
        )
    except (urllib.error.HTTPError, urllib.error.URLError):
        logger.warning("Failed to fetch content for %s/%s:%s", namespace, name, version)
        return None


def _parse_frontmatter(skill_md: str) -> dict:
    """Extract YAML frontmatter from SKILL.md."""
    if not skill_md.startswith("---"):
        return {}
    end = skill_md.find("---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(skill_md[3:end]) or {}
    except yaml.YAMLError:
        return {}


def _parse_tags(tags_json: str) -> list[str]:
    """Parse tags from JSON string or return empty list."""
    if not tags_json:
        return []
    try:
        tags = json.loads(tags_json)
        return tags if isinstance(tags, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _upsert_skill(tx, skill_data: dict):
    """MERGE a Skill node and associated Tag, Domain, Tool relationships."""
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

    for bundled_skill in skill_data.get("bundle_skills_list", []):
        if bundled_skill:
            tx.run(
                """
                MERGE (b:Skill {name: $bundled})
                WITH b
                MATCH (s:Skill {name: $parent})
                MERGE (s)-[:BUNDLES]->(b)
                """,
                parent=name,
                bundled=bundled_skill.strip(),
            ).consume()


def main():
    parser = argparse.ArgumentParser(description="Sync Skill Catalog API into Neo4j")
    parser.add_argument("--with-content", action="store_true", help="Also fetch SKILL.md content for each skill")
    parser.add_argument("--batch-size", type=int, default=50, help="Neo4j transaction batch size")
    args = parser.parse_args()

    catalog_cfg = get_catalog_config()
    neo4j_cfg = get_neo4j_config()
    base_url = catalog_cfg["base_url"]

    logger.info("Catalog API: %s", base_url)
    logger.info("Fetching all skills from catalog...")

    skills = _fetch_all_skills(base_url)
    logger.info("Found %d skills in catalog", len(skills))

    if not skills:
        logger.warning("No skills found. Check catalog API URL and status.")
        return

    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )

    synced = 0
    failed = 0

    for i, skill in enumerate(skills, 1):
        if i % 50 == 0:
            logger.info("[%d/%d] synced=%d failed=%d", i, len(skills), synced, failed)

        tags = _parse_tags(skill.get("tags_json", ""))
        bundle_skills = skill.get("bundle_skills", "").split(",") if skill.get("bundle_skills") else []

        skill_data = {
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

        if args.with_content and skill.get("version"):
            content = _fetch_skill_content(base_url, skill.get("namespace", ""), skill["name"], skill["version"])
            if content:
                skill_data["prompt"] = content
                fm = _parse_frontmatter(content)
                if fm.get("plugin"):
                    skill_data["plugin"] = fm["plugin"]
                if fm.get("lang"):
                    skill_data["lang"] = fm["lang"]
                if fm.get("tools"):
                    skill_data["tools"] = fm["tools"]
                if fm.get("category"):
                    skill_data["category"] = fm["category"]
                if fm.get("tags") and not tags:
                    skill_data["tags"] = fm["tags"]

        try:
            with driver.session(database=neo4j_cfg.get("database", "neo4j")) as session:
                session.execute_write(_upsert_skill, skill_data)
            synced += 1
        except Exception:
            logger.exception("Error syncing %s", skill["name"])
            failed += 1

    driver.close()
    logger.info("Done. Synced: %d, Failed: %d, Total: %d", synced, failed, len(skills))


if __name__ == "__main__":
    main()
