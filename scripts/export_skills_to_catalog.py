#!/usr/bin/env python3
"""Export skills from Neo4j and push them to an OCI registry via skillctl.

Reads all Skill nodes from Neo4j (optionally filtered to those with prompts),
generates skill.yaml (SkillCard) + SKILL.md files per the skillimage spec,
then uses ``skillctl pack`` and ``skillctl push`` to publish them.

Finally triggers a catalog API re-sync so new skills appear immediately.

Prerequisites:
    - ``skillctl`` CLI installed (https://github.com/redhat-et/skillimage)
    - Registry auth configured (~/.docker/config.json or podman auth.json)
    - Neo4j accessible with skills populated

Usage:
    python scripts/export_skills_to_catalog.py \\
        --registry quay.io/rrbanda/skillimage \\
        --limit 100 \\
        [--with-prompt-only] \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

from shared.model_config import get_catalog_config, get_neo4j_config

_SKILLCARD_API_VERSION = "skillimage.io/v1alpha1"


def _query_skills(neo4j_cfg: dict, *, with_prompt_only: bool, limit: int) -> list[dict]:
    """Query skill nodes from Neo4j via HTTP API."""
    import base64

    http_url = neo4j_cfg.get("http_url", "")
    if http_url:
        url = f"{http_url.rstrip('/')}/db/{neo4j_cfg.get('database', 'neo4j')}/tx/commit"
    else:
        host = neo4j_cfg["uri"].split("://")[-1].split(":")[0]
        url = f"http://{host}:7474/db/{neo4j_cfg.get('database', 'neo4j')}/tx/commit"

    creds = base64.b64encode(f"{neo4j_cfg['user']}:{neo4j_cfg['password']}".encode()).decode()

    where = "WHERE s.prompt IS NOT NULL" if with_prompt_only else ""
    cypher = (
        f"MATCH (s:Skill) {where} "
        "RETURN s.name AS name, s.description AS description, "
        "coalesce(s.namespace, s.domain, '') AS namespace, "
        "coalesce(s.version, '1.0.0') AS version, "
        "coalesce(s.author, 'community') AS author, "
        "coalesce(s.license, 'MIT') AS license, "
        "coalesce(s.displayName, s.name) AS displayName, "
        "coalesce(s.tags, '[]') AS tags, "
        "coalesce(s.compatibility, '') AS compatibility, "
        "coalesce(s.category, '') AS category, "
        "coalesce(s.lifecycleState, 'draft') AS lifecycleState, "
        "s.prompt AS prompt "
        f"ORDER BY s.name LIMIT {limit}"
    )

    body = json.dumps({"statements": [{"statement": cypher}]}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {creds}"},
    )
    resp = urllib.request.urlopen(req, timeout=60)
    data = json.loads(resp.read().decode())

    if data.get("errors"):
        raise RuntimeError(f"Neo4j error: {data['errors']}")

    results = data.get("results", [{}])[0]
    columns = results.get("columns", [])
    rows = results.get("data", [])
    return [dict(zip(columns, row["row"], strict=False)) for row in rows]


def _parse_tags(tags_val) -> list[str]:
    if isinstance(tags_val, list):
        return tags_val
    if isinstance(tags_val, str):
        try:
            parsed = json.loads(tags_val)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return [t.strip() for t in tags_val.split(",") if t.strip()]
    return []


def _generate_skill_dir(skill: dict, base_dir: Path) -> Path | None:
    """Generate skill.yaml + SKILL.md in a temp directory."""
    name = skill.get("name", "")
    if not name:
        return None

    namespace = skill.get("namespace", "") or "general"
    skill_dir = base_dir / namespace / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    tags = _parse_tags(skill.get("tags", "[]"))

    skillcard = {
        "apiVersion": _SKILLCARD_API_VERSION,
        "kind": "SkillCard",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "version": skill.get("version", "1.0.0"),
            "description": skill.get("description", ""),
            "display-name": skill.get("displayName", name),
            "authors": [{"name": skill.get("author", "community")}],
            "license": skill.get("license", "MIT"),
        },
        "spec": {"prompt": "SKILL.md"},
    }
    if tags:
        skillcard["metadata"]["tags"] = tags
    if skill.get("compatibility"):
        skillcard["metadata"]["compatibility"] = skill["compatibility"]

    with open(skill_dir / "skill.yaml", "w") as f:
        yaml.dump(skillcard, f, default_flow_style=False, sort_keys=False)

    prompt = skill.get("prompt", "")
    if prompt and not prompt.startswith("---"):
        frontmatter = {
            "name": name,
            "description": skill.get("description", ""),
        }
        if skill.get("compatibility"):
            frontmatter["compatibility"] = skill["compatibility"]
        if skill.get("license"):
            frontmatter["license"] = skill["license"]

        md_content = "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\n" + prompt
    elif prompt:
        md_content = prompt
    else:
        frontmatter = {
            "name": name,
            "description": skill.get("description", ""),
        }
        md_content = "---\n" + yaml.dump(frontmatter, default_flow_style=False) + "---\n\n"
        md_content += f"# {skill.get('displayName', name)}\n\n"
        md_content += skill.get("description", "") + "\n"

    with open(skill_dir / "SKILL.md", "w") as f:
        f.write(md_content)

    return skill_dir


def _skillctl_pack(skill_dir: Path) -> bool:
    """Run skillctl pack on a skill directory."""
    result = subprocess.run(
        ["skillctl", "pack", str(skill_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("skillctl pack failed for %s: %s", skill_dir.name, result.stderr.strip())
        return False
    return True


def _skillctl_push(ref: str) -> bool:
    """Run skillctl push for a skill reference."""
    result = subprocess.run(
        ["skillctl", "push", ref],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning("skillctl push failed for %s: %s", ref, result.stderr.strip())
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Export Neo4j skills to OCI registry via skillctl")
    parser.add_argument("--registry", required=True, help="Target registry (e.g. quay.io/rrbanda/skillimage)")
    parser.add_argument("--limit", type=int, default=2000, help="Max skills to export")
    parser.add_argument("--with-prompt-only", action="store_true", help="Only export skills that have prompt content")
    parser.add_argument("--dry-run", action="store_true", help="Generate files but don't pack/push")
    parser.add_argument("--output-dir", help="Directory for generated skill files (default: temp dir)")
    args = parser.parse_args()

    if not args.dry_run and not shutil.which("skillctl"):
        logger.error(
            "skillctl not found. Install: curl -fsSL "
            "https://raw.githubusercontent.com/redhat-et/skillimage/main/install.sh | sh"
        )
        sys.exit(1)

    neo4j_cfg = get_neo4j_config()
    logger.info("Querying Neo4j for skills (with_prompt_only=%s, limit=%d)...", args.with_prompt_only, args.limit)

    skills = _query_skills(neo4j_cfg, with_prompt_only=args.with_prompt_only, limit=args.limit)
    logger.info("Found %d skills to export", len(skills))

    if not skills:
        logger.warning("No skills found.")
        return

    if args.output_dir:
        base_dir = Path(args.output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
    else:
        base_dir = Path(tempfile.mkdtemp(prefix="skill-export-"))

    logger.info("Generating skill files in %s", base_dir)

    packed = 0
    pushed = 0
    failed = 0

    for i, skill in enumerate(skills, 1):
        if i % 100 == 0:
            logger.info("[%d/%d] packed=%d pushed=%d failed=%d", i, len(skills), packed, pushed, failed)

        skill_dir = _generate_skill_dir(skill, base_dir)
        if not skill_dir:
            failed += 1
            continue

        if args.dry_run:
            packed += 1
            continue

        namespace = skill.get("namespace", "") or "general"
        name = skill["name"]
        version = skill.get("version", "1.0.0")
        lifecycle = skill.get("lifecycleState", "draft")

        if _skillctl_pack(skill_dir):
            packed += 1
            ref = f"{args.registry}/{namespace}/{name}:{version}-{lifecycle}"
            if _skillctl_push(ref):
                pushed += 1
            else:
                failed += 1
        else:
            failed += 1

    logger.info("Done. Generated: %d, Packed: %d, Pushed: %d, Failed: %d", len(skills), packed, pushed, failed)

    if not args.dry_run and pushed > 0:
        try:
            catalog_cfg = get_catalog_config()
            sync_url = f"{catalog_cfg['base_url'].rstrip('/')}/api/v1/sync"
            req = urllib.request.Request(sync_url, method="POST")
            urllib.request.urlopen(req, timeout=30)
            logger.info("Triggered catalog re-sync")
        except Exception:
            logger.warning("Failed to trigger catalog sync (non-fatal)")

    if not args.output_dir:
        logger.info("Temp files at: %s (clean up manually if needed)", base_dir)


if __name__ == "__main__":
    main()
