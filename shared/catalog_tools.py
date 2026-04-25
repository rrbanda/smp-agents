"""Skill Catalog API tools for browsing, searching, and fetching skills.

Wraps the Skill Image Server REST API (skillctl-catalog) as ADK-compatible
tool functions that agents can call directly.

All connection parameters come from config.yaml ``catalog.base_url``.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from shared.model_config import get_catalog_config

logger = logging.getLogger(__name__)

_TIMEOUT = 15


def _catalog_url() -> str:
    return get_catalog_config()["base_url"].rstrip("/")


def _http_get(url: str, *, accept: str = "application/json") -> Any:
    """Perform an HTTP GET against the catalog API."""
    req = urllib.request.Request(url, headers={"Accept": accept})
    try:
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        content_type = resp.headers.get("Content-Type", "")
        body = resp.read().decode("utf-8")
        if "json" in content_type:
            return json.loads(body)
        return body
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:500] if exc.fp else ""
        raise RuntimeError(f"Catalog API error {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Catalog API unreachable: {exc.reason}") from exc


def _http_post(url: str) -> Any:
    """Perform an HTTP POST against the catalog API."""
    req = urllib.request.Request(url, method="POST", headers={"Accept": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:500] if exc.fp else ""
        raise RuntimeError(f"Catalog API error {exc.code}: {error_body}") from exc


def search_skill_catalog(
    query: str = "",
    status: str = "",
    namespace: str = "",
    tags: str = "",
    compatibility: str = "",
    page: int = 1,
    per_page: int = 20,
) -> str:
    """Search the Skill Catalog for skills with optional filters.

    Args:
        query: Free-text search across name, display name, and description.
        status: Filter by lifecycle status (draft, testing, published, deprecated).
        namespace: Filter by namespace (e.g. devops, security, business).
        tags: Comma-separated tag filter (e.g. 'review,documents').
        compatibility: Filter by model compatibility (e.g. 'claude-3.5-sonnet').
        page: Page number (default 1).
        per_page: Results per page (default 20, max 100).

    Returns:
        JSON string with paginated skill results and metadata.
    """
    params: dict[str, str | int] = {"page": page, "per_page": min(per_page, 100)}
    if query:
        params["q"] = query
    if status:
        params["status"] = status
    if namespace:
        params["namespace"] = namespace
    if tags:
        params["tags"] = tags
    if compatibility:
        params["compatibility"] = compatibility

    qs = urllib.parse.urlencode(params)
    url = f"{_catalog_url()}/api/v1/skills?{qs}"
    result = _http_get(url)
    return json.dumps(result, default=str)


def get_skill_detail(namespace: str, name: str) -> str:
    """Get detailed metadata for a specific skill (latest version).

    Args:
        namespace: Skill namespace (e.g. 'business', 'devops').
        name: Skill name in kebab-case (e.g. 'document-reviewer').

    Returns:
        JSON string with full skill metadata including version, status,
        license, compatibility, tags, bundle info, and OCI digest.
    """
    url = f"{_catalog_url()}/api/v1/skills/{namespace}/{name}"
    result = _http_get(url)
    return json.dumps(result, default=str)


def get_skill_versions(namespace: str, name: str) -> str:
    """Get all versions of a skill with their lifecycle status.

    Args:
        namespace: Skill namespace (e.g. 'business', 'devops').
        name: Skill name in kebab-case (e.g. 'document-reviewer').

    Returns:
        JSON string listing all versions with status and metadata.
    """
    url = f"{_catalog_url()}/api/v1/skills/{namespace}/{name}/versions"
    result = _http_get(url)
    return json.dumps(result, default=str)


def get_skill_content(namespace: str, name: str, version: str) -> str:
    """Fetch the raw SKILL.md content for a specific skill version.

    Args:
        namespace: Skill namespace (e.g. 'business', 'devops').
        name: Skill name in kebab-case (e.g. 'document-reviewer').
        version: Semantic version string (e.g. '1.0.0').

    Returns:
        The raw SKILL.md markdown content as a string.
    """
    url = f"{_catalog_url()}/api/v1/skills/{namespace}/{name}/versions/{version}/content"
    return _http_get(url, accept="text/markdown")


def trigger_catalog_sync() -> str:
    """Trigger the catalog to re-sync from its backing OCI registry.

    Call this after publishing a new skill to the OCI registry so it
    appears in the catalog immediately.

    Returns:
        JSON string with sync status.
    """
    url = f"{_catalog_url()}/api/v1/sync"
    result = _http_post(url)
    return json.dumps(result, default=str)
