#!/usr/bin/env python3
"""Sync skills from OCI registry into Neo4j (non-destructive).

Pulls every skill imagestream from the OCI registry, extracts
SKILL.md + skill.yaml, and MERGEs them into Neo4j as Skill nodes
with associated Tag, Domain, and Tool nodes.

NEVER deletes existing nodes -- only creates or updates.
"""

from __future__ import annotations

import gzip
import io
import logging
import os
import sys
import tarfile
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

from neo4j import GraphDatabase

from shared.model_config import get_neo4j_config, get_oci_config


def _get_oc_token() -> str:
    token = os.environ.get("OC_TOKEN")
    if not token:
        import subprocess

        result = subprocess.run(["oc", "whoami", "-t"], capture_output=True, text=True)
        token = result.stdout.strip()
    return token


def _list_imagestreams(oc_token: str, namespace: str) -> list[str]:
    """List all imagestream names in the given namespace via oc."""
    import subprocess

    result = subprocess.run(
        ["oc", "get", "imagestream", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"],
        capture_output=True,
        text=True,
    )
    names = result.stdout.strip().split()
    return [n for n in names if n.startswith("skill-")]


def _pull_skill_artifact(
    registry_url: str, namespace: str, skill_name: str, tag: str, oc_token: str, max_retries: int = 3
) -> dict | None:
    """Pull and extract SKILL.md + skill.yaml from an OCI skill artifact."""
    import time as _time

    session = requests.Session()
    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
    if os.path.isfile(ca_bundle):
        session.verify = ca_bundle
    else:
        session.verify = True
    headers = {"Authorization": f"Bearer {oc_token}"}

    for attempt in range(max_retries):
        try:
            manifest_url = f"{registry_url}/v2/{namespace}/{skill_name}/manifests/{tag}"
            resp = session.get(
                manifest_url,
                headers={
                    **headers,
                    "Accept": (
                        "application/vnd.oci.image.manifest.v1+json,"
                        " application/vnd.docker.distribution.manifest.v2+json"
                    ),
                },
                timeout=15,
            )
            if resp.status_code != 200:
                return None

            manifest = resp.json()
            layers = manifest.get("layers", [])
            if not layers:
                return None

            layer_digest = layers[0]["digest"]
            blob_url = f"{registry_url}/v2/{namespace}/{skill_name}/blobs/{layer_digest}"
            blob_resp = session.get(blob_url, headers=headers, timeout=30, allow_redirects=True)
            if blob_resp.status_code != 200 or len(blob_resp.content) == 0:
                return None

            result = {}
            with tarfile.open(fileobj=io.BytesIO(blob_resp.content), mode="r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith("SKILL.md"):
                        f = tf.extractfile(member)
                        if f:
                            result["skill_md"] = f.read().decode("utf-8", errors="replace")
                    elif member.name.endswith("skill.yaml"):
                        f = tf.extractfile(member)
                        if f:
                            result["skill_yaml"] = yaml.safe_load(f.read())
            return result if result else None
        except (requests.ConnectionError, requests.Timeout, tarfile.TarError, gzip.BadGzipFile):
            if attempt < max_retries - 1:
                _time.sleep(2**attempt)
                continue
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


def _upsert_skill(tx, skill_data: dict):
    """MERGE a Skill node and associated relationships (non-destructive)."""
    name = skill_data.get("name")
    if not name:
        return

    tx.run(
        """
        MERGE (s:Skill {name: $name})
        SET s.description = $description,
            s.domain = $domain,
            s.version = $version,
            s.author = $author,
            s.license = $license,
            s.ociReference = $ociRef,
            s.source = $source,
            s.displayName = $displayName,
            s.syncedFromOCI = true
        """,
        name=name,
        description=skill_data.get("description", ""),
        domain=skill_data.get("namespace", skill_data.get("domain", "")),
        version=skill_data.get("version", "1.0.0"),
        author=skill_data.get("author", ""),
        license=skill_data.get("license", ""),
        ociRef=skill_data.get("oci_ref", ""),
        source=skill_data.get("source", ""),
        displayName=skill_data.get("display_name", name),
    )

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
        )

    domain = skill_data.get("namespace", skill_data.get("domain", ""))
    if domain:
        tx.run(
            """
            MERGE (d:Domain {name: $domain})
            WITH d
            MATCH (s:Skill {name: $skill_name})
            MERGE (s)-[:BELONGS_TO]->(d)
            """,
            domain=domain,
            skill_name=name,
        )

    for tool in skill_data.get("allowed_tools", []):
        tx.run(
            """
            MERGE (t:Tool {name: $tool})
            WITH t
            MATCH (s:Skill {name: $skill_name})
            MERGE (s)-[:USES_TOOL]->(t)
            """,
            tool=tool.strip(),
            skill_name=name,
        )


def main():
    oci_cfg = get_oci_config()
    neo4j_cfg = get_neo4j_config()
    registry_url = oci_cfg["registry_url"]
    namespace = oci_cfg["namespace"]

    oc_token = _get_oc_token()
    logger.info("Registry: %s/%s", registry_url, namespace)

    imagestreams = _list_imagestreams(oc_token, namespace)
    logger.info("Found %d skill imagestreams", len(imagestreams))

    driver = GraphDatabase.driver(
        neo4j_cfg["uri"],
        auth=(neo4j_cfg["user"], neo4j_cfg["password"]),
    )

    synced = 0
    failed = 0

    for i, is_name in enumerate(imagestreams, 1):
        if i % 100 == 0:
            logger.info("[%d/%d] synced=%d failed=%d", i, len(imagestreams), synced, failed)

        try:
            artifact = _pull_skill_artifact(registry_url, namespace, is_name, "1.0.0", oc_token)
        except Exception:
            logger.exception("Error pulling artifact %s", is_name)
            failed += 1
            continue
        if not artifact:
            failed += 1
            continue

        skill_yaml = artifact.get("skill_yaml", {})
        metadata = skill_yaml.get("metadata", {}) if skill_yaml else {}
        frontmatter = _parse_frontmatter(artifact.get("skill_md", ""))

        skill_name = metadata.get("name") or frontmatter.get("name") or is_name.removeprefix("skill-")
        description = metadata.get("description") or frontmatter.get("description", "")
        tags = metadata.get("tags", []) or frontmatter.get("tags", [])
        allowed_tools_str = metadata.get("allowed-tools", "")
        allowed_tools = allowed_tools_str.split() if isinstance(allowed_tools_str, str) else []
        provenance = skill_yaml.get("provenance", {}) if skill_yaml else {}

        skill_data = {
            "name": skill_name,
            "description": description,
            "namespace": metadata.get("namespace", ""),
            "version": metadata.get("version", "1.0.0"),
            "display_name": metadata.get("display-name", skill_name),
            "license": metadata.get("license", ""),
            "author": (metadata.get("authors", [{}])[0].get("name", "") if metadata.get("authors") else ""),
            "tags": tags,
            "allowed_tools": allowed_tools,
            "source": provenance.get("source", ""),
            "oci_ref": f"{registry_url}/{namespace}/{is_name}:1.0.0",
        }

        try:
            with driver.session(database=neo4j_cfg.get("database", "neo4j")) as session:
                session.execute_write(_upsert_skill, skill_data)
            synced += 1
        except Exception:
            logger.exception("Error syncing %s", skill_name)
            failed += 1

    driver.close()
    logger.info("Done. Synced: %d, Failed: %d, Total: %d", synced, failed, len(imagestreams))


if __name__ == "__main__":
    main()
