"""Shared fixtures for smp-agents test suite."""

from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest
import requests
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Marker registration
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests (no network)")
    config.addinivalue_line("markers", "integration: integration tests (need LLM/Neo4j)")
    config.addinivalue_line("markers", "e2e: end-to-end tests (need deployed agents)")
    config.addinivalue_line("markers", "eval: ADK agent eval tests")
    config.addinivalue_line("markers", "skill_eval: agentskills.io skill eval tests")


# ---------------------------------------------------------------------------
# Marker auto-application: tag every test file by its prefix
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(items):
    for item in items:
        path = str(item.fspath)
        if "test_integration_" in path:
            item.add_marker(pytest.mark.integration)
        elif "test_e2e_" in path:
            item.add_marker(pytest.mark.e2e)
        elif "test_agent_evals" in path:
            item.add_marker(pytest.mark.eval)
        elif "test_skill_evals" in path and "TestSkillEvalExecution" in item.nodeid:
            item.add_marker(pytest.mark.skill_eval)
        else:
            item.add_marker(pytest.mark.unit)


# ---------------------------------------------------------------------------
# Skip helpers for integration / e2e layers
# ---------------------------------------------------------------------------


def _neo4j_reachable() -> bool:
    try:
        import base64
        import urllib.request

        from shared.neo4j_tools import get_neo4j_config

        cfg = get_neo4j_config()
        http_url = cfg.get("http_url", "")
        if http_url:
            url = f"{http_url.rstrip('/')}/db/{cfg.get('database', 'neo4j')}/tx/commit"
        else:
            host = cfg["uri"].split("://")[-1].split(":")[0]
            url = f"http://{host}:7474/db/{cfg.get('database', 'neo4j')}/tx/commit"
        creds = base64.b64encode(f"{cfg['user']}:{cfg['password']}".encode()).decode()
        body = b'{"statements":[{"statement":"RETURN 1"}]}'
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {creds}",
            },
        )
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


def _embedding_reachable() -> bool:
    try:
        from shared.model_config import get_embedding_config

        cfg = get_embedding_config()
        r = requests.post(
            f"{cfg['api_base']}/embeddings",
            json={"model": cfg["id"], "input": "ping"},
            timeout=3,
        )
        return r.status_code == 200
    except Exception:
        return False


neo4j_available = pytest.mark.skipif(
    not _neo4j_reachable(),
    reason="Neo4j is not reachable (set NEO4J_URI / NEO4J_PASSWORD)",
)

llm_available = pytest.mark.skipif(
    not _embedding_reachable(),
    reason="Embedding / LLM endpoint is not reachable",
)


# ---------------------------------------------------------------------------
# Agent base URL helpers for E2E tests
# ---------------------------------------------------------------------------

_AGENT_PORTS = {
    "skill_advisor": 8001,
    "bundle_validator": 8002,
    "kg_qa": 8003,
    "playground": 8004,
    "skill_builder": 8005,
}

E2E_BASE = os.environ.get("E2E_BASE_URL", "http://localhost")


def agent_url(agent_name: str) -> str:
    port = _AGENT_PORTS[agent_name]
    return f"{E2E_BASE}:{port}"


def _agent_reachable(agent_name: str) -> bool:
    try:
        r = requests.get(f"{agent_url(agent_name)}/healthz", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


agents_deployed = pytest.mark.skipif(
    not _agent_reachable("skill_advisor"),
    reason="Deployed agents not reachable (set E2E_BASE_URL)",
)


# ---------------------------------------------------------------------------
# A2A JSON-RPC client fixture
# ---------------------------------------------------------------------------


class A2AClient:
    """Minimal A2A JSON-RPC client for E2E tests."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def send_task(self, message: str, *, timeout: int = 120) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tasks/send",
            "params": {
                "id": str(uuid.uuid4()),
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                },
            },
        }
        resp = requests.post(self.base_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


@pytest.fixture()
def a2a_client():
    """Factory fixture: call a2a_client(agent_name) to get an A2AClient."""

    def _factory(agent_name: str) -> A2AClient:
        return A2AClient(agent_url(agent_name))

    return _factory


# ---------------------------------------------------------------------------
# Starlette TestClient for health routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def health_test_client():
    """TestClient wrapping just the health routes."""
    from starlette.applications import Starlette

    from shared.health import health_routes

    app = Starlette(routes=health_routes)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Unit-test mock fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_neo4j_config():
    cfg = {
        "uri": "bolt://localhost:7687",
        "user": "neo4j",
        "password": "test-password",
        "database": "neo4j",
    }
    with patch("shared.neo4j_tools.get_neo4j_config", return_value=cfg):
        yield cfg


@pytest.fixture()
def mock_embedding_config():
    cfg = {
        "id": "nomic-embed-text-v1-5",
        "api_base": "http://localhost:9999",
    }
    with patch("shared.semantic_search_tools.get_embedding_config", return_value=cfg):
        yield cfg


@pytest.fixture()
def mock_oci_config():
    cfg = {
        "registry_url": "https://registry.example.com",
        "namespace": "test-ns",
    }
    with patch("shared.oci_tools.get_oci_config", return_value=cfg):
        yield cfg


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

VALID_SKILL_MD = """\
---
name: test-skill
description: A test skill for unit tests.
---

# Instructions

Follow these steps to do the thing.
"""

INVALID_SKILL_MD_NO_FRONTMATTER = """\
# No Frontmatter

Just some content without YAML frontmatter.
"""

INVALID_SKILL_MD_BAD_NAME = """\
---
name: BAD_NAME
description: Name is not kebab-case.
---

# Instructions
"""

LONG_DESC_SKILL_MD = """\
---
name: long-desc
description: {}
---

# Instructions
""".format("x" * 1025)
