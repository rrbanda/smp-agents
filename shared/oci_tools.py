"""OCI registry tools for publishing and retrieving skill artifacts.

All connection parameters come from config.yaml.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from shared.model_config import get_oci_config


def publish_skill_to_oci(
    skill_name: str,
    version: str,
    skill_content: str,
    author: str = "smp-agent",
) -> str:
    """Publish a skill specification to the OCI registry.

    Args:
        skill_name: Kebab-case skill name (e.g. 'deploy-to-k8s').
        version: Semantic version string (e.g. '1.0.0').
        skill_content: The full SKILL.md content as a string.
        author: Author identifier for OCI annotations.

    Returns:
        JSON with status and the OCI reference URL.
    """
    cfg = get_oci_config()
    ref = f"{cfg['registry_url']}/{cfg['namespace']}/skills/{skill_name}:{version}"

    result: dict[str, Any] = {
        "status": "published",
        "reference": ref,
        "skill_name": skill_name,
        "version": version,
        "author": author,
        "content_length": len(skill_content),
    }

    try:
        # oras is the standard CLI for OCI artifact operations
        cmd = [
            "oras", "push", ref,
            "--annotation", f"org.agentskills.name={skill_name}",
            "--annotation", f"org.agentskills.version={version}",
            "--annotation", f"org.agentskills.author={author}",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            result["status"] = "error"
            result["error"] = proc.stderr.strip()
    except FileNotFoundError:
        result["status"] = "error"
        result["error"] = "oras CLI not found; install from https://oras.land"
    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["error"] = "OCI push timed out after 30 seconds"

    return json.dumps(result)


def validate_skill_yaml(skill_content: str) -> str:
    """Validate a skill specification against the agentskills.io format.

    Args:
        skill_content: The full SKILL.md content as a string.

    Returns:
        JSON with validation status and any errors found.
    """
    import re

    errors: list[str] = []
    warnings: list[str] = []

    frontmatter_match = re.search(
        r"^---\s*\n(.*?)\n---", skill_content, re.DOTALL
    )
    if not frontmatter_match:
        errors.append("Missing YAML frontmatter (must start with ---)")
        return json.dumps({"valid": False, "errors": errors, "warnings": warnings})

    import yaml

    try:
        fm = yaml.safe_load(frontmatter_match.group(1))
    except yaml.YAMLError as e:
        errors.append(f"Invalid YAML in frontmatter: {e}")
        return json.dumps({"valid": False, "errors": errors, "warnings": warnings})

    if not isinstance(fm, dict):
        errors.append("Frontmatter must be a YAML mapping")
        return json.dumps({"valid": False, "errors": errors, "warnings": warnings})

    if "name" not in fm:
        errors.append("Missing required field: name")
    elif not re.match(r"^[a-z][a-z0-9-]*$", fm["name"]):
        errors.append(f"Name '{fm['name']}' is not valid kebab-case")

    if "description" not in fm:
        errors.append("Missing required field: description")
    elif len(fm["description"]) > 1000:
        errors.append(
            f"Description is {len(fm['description'])} chars (max 1000)"
        )

    body = skill_content[frontmatter_match.end():].strip()
    if not body:
        warnings.append("Skill body (instructions) is empty")

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    })


def list_oci_skills(tag_filter: str = "") -> str:
    """List skills available in the OCI registry, optionally filtered by tag.

    Args:
        tag_filter: Optional tag substring to filter results.

    Returns:
        JSON-encoded list of skill references from the registry.
    """
    cfg = get_oci_config()
    repo = f"{cfg['registry_url']}/{cfg['namespace']}/skills"

    try:
        cmd = ["oras", "repo", "tags", repo]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return json.dumps({"status": "error", "error": proc.stderr.strip()})

        tags = [t.strip() for t in proc.stdout.strip().split("\n") if t.strip()]
        if tag_filter:
            tags = [t for t in tags if tag_filter in t]

        return json.dumps({"status": "ok", "repository": repo, "tags": tags})
    except FileNotFoundError:
        return json.dumps({"status": "error", "error": "oras CLI not found"})
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "error": "OCI list timed out"})
