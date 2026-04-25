"""E2E tests for A2A Agent Card endpoints.

Require agents deployed and reachable. Skipped automatically if not.
"""

from __future__ import annotations

import pytest
import requests

from tests.conftest import agent_url, agents_deployed

_AGENT_NAMES = ["skill_advisor", "bundle_validator", "kg_qa", "playground", "skill_builder"]

_REQUIRED_CARD_FIELDS = {"name", "description", "skills", "version", "capabilities"}
_REQUIRED_SKILL_FIELDS = {"id", "name", "description", "tags"}


@agents_deployed
class TestAgentCards:
    @pytest.mark.parametrize("agent_name", _AGENT_NAMES)
    def test_agent_card_returns_200(self, agent_name):
        resp = requests.get(f"{agent_url(agent_name)}/.well-known/agent-card.json", timeout=10)
        assert resp.status_code == 200

    @pytest.mark.parametrize("agent_name", _AGENT_NAMES)
    def test_agent_card_has_required_fields(self, agent_name):
        resp = requests.get(f"{agent_url(agent_name)}/.well-known/agent-card.json", timeout=10)
        card = resp.json()
        for field in _REQUIRED_CARD_FIELDS:
            assert field in card, f"Missing field '{field}' in {agent_name} card"

    @pytest.mark.parametrize("agent_name", _AGENT_NAMES)
    def test_agent_card_skills_have_required_fields(self, agent_name):
        resp = requests.get(f"{agent_url(agent_name)}/.well-known/agent-card.json", timeout=10)
        card = resp.json()
        assert isinstance(card["skills"], list)
        assert len(card["skills"]) > 0
        for skill in card["skills"]:
            for field in _REQUIRED_SKILL_FIELDS:
                assert field in skill, f"Skill missing '{field}' in {agent_name}"

    @pytest.mark.parametrize("agent_name", _AGENT_NAMES)
    def test_agent_card_input_output_modes(self, agent_name):
        resp = requests.get(f"{agent_url(agent_name)}/.well-known/agent-card.json", timeout=10)
        card = resp.json()
        assert "defaultInputModes" in card, f"{agent_name} missing defaultInputModes"
        assert "defaultOutputModes" in card, f"{agent_name} missing defaultOutputModes"
