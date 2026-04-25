"""E2E tests for A2A task execution on deployed agents.

Sends JSON-RPC tasks/send to each deployed agent and validates responses.
Require agents deployed and reachable. Skipped automatically if not.
"""

from __future__ import annotations

import pytest

from tests.conftest import A2AClient, agent_url, agents_deployed

_AGENT_PROMPTS = {
    "skill_advisor": "recommend skills for CI/CD",
    "bundle_validator": "validate this bundle: code-review, api-security-review",
    "kg_qa": "how many skills are in the graph?",
    "playground": "hello",
    "skill_builder": "create a skill for Docker security",
}


@agents_deployed
class TestA2ATaskExecution:
    @pytest.mark.parametrize("agent_name", list(_AGENT_PROMPTS.keys()))
    def test_tasks_send_completes(self, agent_name):
        client = A2AClient(agent_url(agent_name))
        prompt = _AGENT_PROMPTS[agent_name]
        result = client.send_task(prompt, timeout=120)

        assert "result" in result, f"No result in response from {agent_name}"
        task = result["result"]
        assert "status" in task, f"No status in task from {agent_name}"

    @pytest.mark.parametrize("agent_name", list(_AGENT_PROMPTS.keys()))
    def test_tasks_send_has_artifacts(self, agent_name):
        client = A2AClient(agent_url(agent_name))
        prompt = _AGENT_PROMPTS[agent_name]
        result = client.send_task(prompt, timeout=120)

        task = result.get("result", {})
        artifacts = task.get("artifacts", [])
        assert len(artifacts) > 0, f"No artifacts returned by {agent_name}"
        for artifact in artifacts:
            assert "parts" in artifact, f"Artifact missing 'parts' in {agent_name}"
            assert len(artifact["parts"]) > 0
