#!/usr/bin/env python3
"""Import Microsoft skills into the OCI registry via skillctl.

Converts skills from github.com/microsoft/skills (SKILL.md-only format)
into skillctl-compatible format (skill.yaml SkillCard + SKILL.md), then
optionally packs and pushes them to an OCI registry.

Usage:
    # Dry-run: convert all skills, validate, but don't pack/push
    python scripts/import_ms_skills.py /path/to/microsoft/skills --dry-run

    # Convert and pack first 5 skills only
    python scripts/import_ms_skills.py /path/to/microsoft/skills --limit 5

    # Full import to GHCR
    python scripts/import_ms_skills.py /path/to/microsoft/skills \
        --registry ghcr.io/rrbanda/skillimage

    # Full import to OpenShift internal registry
    python scripts/import_ms_skills.py /path/to/microsoft/skills \
        --registry image-registry.openshift-image-registry.svc:5000/skill-catalog \
        --no-tls-verify
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(message)s",
)
log = logging.getLogger(__name__)

SKILLCARD_API_VERSION = "skillimage.io/v1alpha1"
SKILLCARD_KIND = "SkillCard"
DEFAULT_VERSION = "1.0.0"
DEFAULT_AUTHOR = "Microsoft"


def parse_frontmatter(content: str) -> dict[str, Any] | None:
    """Extract YAML frontmatter from a SKILL.md file."""
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1))
        return fm if isinstance(fm, dict) else None
    except yaml.YAMLError:
        return None


def derive_namespace(skill_path: Path, repo_root: Path) -> str:
    """Derive a skillctl namespace from the skill's location in the MS repo."""
    rel = skill_path.relative_to(repo_root)
    parts = rel.parts

    if "plugins" in parts:
        idx = parts.index("plugins")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "skills" in parts and "plugins" not in parts:
        return "core"
    return "microsoft"


def normalize_semver(version: Any) -> str:
    """Ensure version is strict semver (X.Y.Z)."""
    v = str(version).strip().lstrip("v")
    parts = v.split(".")
    if len(parts) == 1:
        return f"{parts[0]}.0.0"
    if len(parts) == 2:
        return f"{parts[0]}.{parts[1]}.0"
    return v


DOMAIN_RULES: list[tuple[list[str], str]] = [
    (["ai-agents", "ai-projects", "ai-openai", "openai", "speech", "vision",
      "imageanalysis", "document-intelligence", "ai-ml", "ai-inference",
      "ai-voicelive", "m365-agents", "copilot", "continual-learning",
      "anomalydetector", "contentsafety", "formrecognizer",
      "contentunderstanding", "language-conversations", "textanalytics",
      "transcription", "translation", "agent-framework", "agents-v2",
      "hosted-agents"], "ai-ml"),
    (["mgmt-", "resource-manager", "-aks-", "containerservice", "network",
      "compute", "appservice", "webpubsub", "signalr", "frontdoor", "cdn",
      "dns", "trafficmanager", "loadbalancer", "virtualnetwork",
      "containerapp", "appcontainers", "appplatform", "springcloud",
      "botservice", "cloud-solution-architect", "appconfiguration",
      "containerregistry", "web-pubsub"], "cloud-infra"),
    (["cosmos", "-sql-", "tables", "blob", "storage", "data-tables",
      "data-lake", "eventhub", "schemaregistry", "synapse", "datafactory",
      "monitor-query", "monitor-ingestion", "loganalytics",
      "postgres"], "data"),
    (["identity", "keyvault", "entra", "authentication-events",
      "attestation"], "identity"),
    (["servicebus", "eventgrid", "api-management", "apicenter",
      "apimanagement", "communication", "notification"], "integration"),
    (["security", "defender", "sentinel"], "security"),
    (["wiki", "docs", "changelog", "deep-wiki", "onboarding",
      "microsoft-docs", "llms-txt", "vitepress"], "documentation"),
    (["monitor", "insights", "container-registry", "applicationinsights",
      "webtest", "search-documents", "maps-search", "playwright", "kql",
      "github-issue", "mcp-builder"], "devops"),
    (["frontend", "react-flow", "zustand", "dark-ts", "fastapi", "pydantic",
      "ui-"], "development"),
]

LANG_SUFFIXES = {"-py": "python", "-dotnet": "dotnet", "-ts": "typescript",
                 "-java": "java", "-rust": "rust"}

NS_TO_PLUGIN = {
    "azure-sdk-python": "azure-sdk-python",
    "azure-sdk-dotnet": "azure-sdk-dotnet",
    "azure-sdk-java": "azure-sdk-java",
    "azure-sdk-typescript": "azure-sdk-typescript",
    "azure-sdk-rust": "azure-sdk-rust",
    "azure-skills": "azure-skills",
    "deep-wiki": "deep-wiki",
}


def classify_domain(name: str, namespace: str) -> str:
    """Classify a skill into a domain using keyword rules."""
    name_lower = name.lower()
    for patterns, domain in DOMAIN_RULES:
        for p in patterns:
            if p in name_lower:
                return domain
    if namespace == "deep-wiki":
        return "documentation"
    if namespace == "azure-skills":
        return "cloud-infra"
    return "general"


def derive_lang(name: str) -> str | None:
    """Detect programming language from skill name suffix."""
    for suffix, lang in LANG_SUFFIXES.items():
        if name.endswith(suffix):
            return lang
    return None


def derive_tags(name: str, namespace: str) -> list[str]:
    """Derive tags from skill name suffix, namespace, and domain."""
    tags: list[str] = []
    lang = derive_lang(name)
    if lang:
        tags.append(lang)

    if "azure" in name.lower() or "azure" in namespace.lower():
        tags.append("azure")
    elif namespace == "core":
        tags.append("core")
    elif namespace == "deep-wiki":
        tags.append("documentation")

    domain = classify_domain(name, namespace)
    if domain not in tags:
        tags.append(domain)

    return tags


def discover_skills(repo_root: Path) -> list[Path]:
    """Walk the repo and find all directories containing SKILL.md."""
    skills: list[Path] = []
    for root, _dirs, files in os.walk(repo_root):
        if "SKILL.md" in files:
            skills.append(Path(root))
    return sorted(skills)


def convert_skill(
    skill_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    """Convert a Microsoft skill directory to a skillctl SkillCard dict."""
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    if fm is None or "name" not in fm:
        return None

    name = fm["name"]
    namespace = derive_namespace(skill_dir, repo_root)
    meta = fm.get("metadata", {}) if isinstance(fm.get("metadata"), dict) else {}
    version = normalize_semver(meta.get("version", DEFAULT_VERSION))
    description = fm.get("description", "").strip()
    if not description:
        return None

    skill_card: dict[str, Any] = {
        "apiVersion": SKILLCARD_API_VERSION,
        "kind": SKILLCARD_KIND,
        "metadata": {
            "name": name,
            "namespace": namespace,
            "version": version,
            "description": description,
        },
        "spec": {
            "prompt": "SKILL.md",
        },
    }

    license_val = fm.get("license")
    if license_val:
        skill_card["metadata"]["license"] = str(license_val)

    tags = derive_tags(name, namespace)
    if tags:
        skill_card["metadata"]["tags"] = tags

    domain = classify_domain(name, namespace)
    skill_card["metadata"]["namespace"] = domain

    lang = derive_lang(name)
    if lang:
        skill_card["metadata"]["lang"] = lang

    plugin = NS_TO_PLUGIN.get(namespace)
    if plugin:
        skill_card["metadata"]["plugin"] = plugin

    compatibility = fm.get("compatibility")
    if compatibility:
        skill_card["metadata"]["compatibility"] = str(compatibility)

    author_name = meta.get("author", DEFAULT_AUTHOR)
    skill_card["metadata"]["authors"] = [{"name": str(author_name)}]

    return skill_card


def write_staging(
    skill_dir: Path,
    repo_root: Path,
    staging_root: Path,
    skill_card: dict[str, Any],
) -> Path:
    """Write the converted skill to the staging directory."""
    namespace = skill_card["metadata"]["namespace"]
    name = skill_card["metadata"]["name"]
    out_dir = staging_root / namespace / name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write skill.yaml
    with open(out_dir / "skill.yaml", "w") as f:
        yaml.dump(skill_card, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Copy SKILL.md
    shutil.copy2(skill_dir / "SKILL.md", out_dir / "SKILL.md")

    # Copy references/ or reference/ if present
    for ref_dir_name in ("references", "reference"):
        src = skill_dir / ref_dir_name
        if src.is_dir():
            dst = out_dir / ref_dir_name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Copy scripts/ if present
    scripts_src = skill_dir / "scripts"
    if scripts_src.is_dir():
        scripts_dst = out_dir / "scripts"
        if scripts_dst.exists():
            shutil.rmtree(scripts_dst)
        shutil.copytree(scripts_src, scripts_dst)

    return out_dir


def run_skillctl_pack(skill_staging_dir: Path) -> bool:
    """Pack a skill directory into a local OCI image using skillctl."""
    try:
        result = subprocess.run(
            ["skillctl", "pack", str(skill_staging_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.error("  pack failed: %s", result.stderr.strip())
            return False
        log.info("  packed: %s", result.stdout.strip())
        return True
    except FileNotFoundError:
        log.error("  skillctl not found; install from https://github.com/redhat-et/skillimage")
        return False
    except subprocess.TimeoutExpired:
        log.error("  pack timed out")
        return False


def run_skillctl_tag(
    namespace: str,
    name: str,
    version: str,
    registry: str,
) -> bool:
    """Tag a local skill image with the remote registry reference.

    Registry can be a full repo like 'quay.io/rbrhssa/skills' (single-repo mode,
    tag = <name>-<version>-draft) or a registry prefix like 'quay.io/rbrhssa'
    (multi-repo mode, repo = <namespace>/<name>, tag = <version>-draft).
    """
    local_ref = f"{namespace}/{name}:{version}-draft"
    remote_ref = _build_remote_ref(registry, namespace, name, version)

    try:
        result = subprocess.run(
            ["skillctl", "tag", local_ref, remote_ref],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            log.error("  tag failed: %s", result.stderr.strip())
            return False
        log.debug("  tagged %s -> %s", local_ref, remote_ref)
        return True
    except FileNotFoundError:
        log.error("  skillctl not found")
        return False
    except subprocess.TimeoutExpired:
        log.error("  tag timed out")
        return False


def _build_remote_ref(
    registry: str, namespace: str, name: str, version: str
) -> str:
    """Build the remote OCI reference.

    If registry has >=3 path segments (e.g. quay.io/org/repo), treat it as a
    single-repo target where each skill becomes a unique tag.  Otherwise use
    the multi-repo layout.
    """
    parts = registry.rstrip("/").split("/")
    if len(parts) >= 3:
        return f"{registry}:{name}-{version}-draft"
    return f"{registry}/{namespace}/{name}:{version}-draft"


def run_skillctl_push(
    namespace: str,
    name: str,
    version: str,
    registry: str,
    tls_verify: bool,
) -> bool:
    """Tag the local image, then push to the remote OCI registry."""
    remote_ref = _build_remote_ref(registry, namespace, name, version)

    if not run_skillctl_tag(namespace, name, version, registry):
        return False

    cmd = ["skillctl", "push", remote_ref]
    if not tls_verify:
        cmd.append("--tls-verify=false")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error("  push failed for %s: %s", remote_ref, result.stderr.strip())
            return False
        log.info("  pushed: %s", remote_ref)
        return True
    except FileNotFoundError:
        log.error("  skillctl not found")
        return False
    except subprocess.TimeoutExpired:
        log.error("  push timed out for %s", remote_ref)
        return False


def trigger_catalog_sync(catalog_url: str) -> None:
    """Trigger the Skill Catalog API to resync from the registry."""
    try:
        url = f"{catalog_url.rstrip('/')}/api/v1/sync"
        req = urllib.request.Request(url, method="POST")
        resp = urllib.request.urlopen(req, timeout=15)
        body = json.loads(resp.read().decode("utf-8"))
        log.info("Catalog sync triggered: %s", body)
    except Exception as e:
        log.warning("Could not trigger catalog sync: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Microsoft skills into the OCI registry via skillctl.",
    )
    parser.add_argument(
        "repo_path",
        type=Path,
        help="Path to cloned microsoft/skills repository",
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=Path("/tmp/ms-skills-staging"),
        help="Staging directory for converted skills (default: /tmp/ms-skills-staging)",
    )
    parser.add_argument(
        "--registry",
        type=str,
        default="",
        help="OCI registry URL (e.g. ghcr.io/rrbanda/skillimage). Required for push.",
    )
    parser.add_argument(
        "--catalog-url",
        type=str,
        default="https://skillctl-catalog-skill-catalog.apps.ocp.v7hjl.sandbox2288.opentlc.com",
        help="Skill Catalog API URL for triggering sync after push",
    )
    parser.add_argument(
        "--no-tls-verify",
        action="store_true",
        help="Skip TLS verification for the OCI registry (for internal registries)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Convert and validate only; do not pack or push",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only the first N skills (0 = all)",
    )
    parser.add_argument(
        "--pack-only",
        action="store_true",
        help="Pack skills locally but do not push to remote registry",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    repo_root = args.repo_path.resolve()
    if not (repo_root / ".github").is_dir():
        log.error("Not a valid microsoft/skills repo: %s", repo_root)
        sys.exit(1)

    staging = args.staging_dir.resolve()
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    log.info("Discovering skills in %s ...", repo_root)
    skill_dirs = discover_skills(repo_root)
    log.info("Found %d skills", len(skill_dirs))

    if args.limit > 0:
        skill_dirs = skill_dirs[: args.limit]
        log.info("Limited to %d skills", len(skill_dirs))

    converted = 0
    packed = 0
    pushed = 0
    errors: list[str] = []

    for skill_dir in skill_dirs:
        rel_path = skill_dir.relative_to(repo_root)
        log.info("Processing %s", rel_path)

        skill_card = convert_skill(skill_dir, repo_root)
        if skill_card is None:
            errors.append(f"{rel_path}: conversion failed (no name or description)")
            continue

        out_dir = write_staging(skill_dir, repo_root, staging, skill_card)
        converted += 1
        name = skill_card["metadata"]["name"]
        namespace = skill_card["metadata"]["namespace"]
        version = skill_card["metadata"]["version"]

        log.debug("  -> %s/%s v%s  staged at %s", namespace, name, version, out_dir)

        if args.dry_run:
            continue

        if run_skillctl_pack(out_dir):
            packed += 1
        else:
            errors.append(f"{namespace}/{name}: pack failed")
            continue

        if args.pack_only or not args.registry:
            continue

        if run_skillctl_push(namespace, name, version, args.registry, not args.no_tls_verify):
            pushed += 1
        else:
            errors.append(f"{namespace}/{name}: push failed")

    log.info("")
    log.info("=== Summary ===")
    log.info("Discovered:  %d skills", len(skill_dirs))
    log.info("Converted:   %d", converted)
    log.info("Packed:      %d", packed)
    log.info("Pushed:      %d", pushed)
    log.info("Errors:      %d", len(errors))
    if errors:
        log.info("")
        log.info("Errors:")
        for e in errors:
            log.info("  - %s", e)

    if pushed > 0 and args.catalog_url:
        log.info("")
        trigger_catalog_sync(args.catalog_url)

    log.info("")
    log.info("Staging directory: %s", staging)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
