"""E2E tests for health check endpoints on deployed agents.

Require agents deployed and reachable. Skipped automatically if not.
"""

from __future__ import annotations

import pytest
import requests

from tests.conftest import agent_url, agents_deployed

_AGENT_NAMES = ["skill_advisor", "bundle_validator", "kg_qa", "playground", "skill_builder"]


@agents_deployed
class TestHealthEndpoints:
    @pytest.mark.parametrize("agent_name", _AGENT_NAMES)
    def test_healthz_returns_ok(self, agent_name):
        resp = requests.get(f"{agent_url(agent_name)}/healthz", timeout=10)
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @pytest.mark.parametrize("agent_name", _AGENT_NAMES)
    def test_readyz_returns_ready(self, agent_name):
        resp = requests.get(f"{agent_url(agent_name)}/readyz", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["checks"]["neo4j"] == "ok"
