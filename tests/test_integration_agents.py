"""Integration tests for agents via ADK Runner (no A2A, no deployment).

Require live LLM and Neo4j. Skipped automatically if unreachable.
"""

from __future__ import annotations

import pytest
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from tests.conftest import llm_available, neo4j_available


async def _run_agent(agent, user_message: str) -> str:
    """Send a single message to an agent via ADK Runner and return the text response."""
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name="test", session_service=session_service)
    session = await session_service.create_session(app_name="test", user_id="test-user")

    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_message)],
    )
    responses = []
    async for event in runner.run_async(
        user_id="test-user",
        session_id=session.id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    responses.append(part.text)
    return "\n".join(responses)


@neo4j_available
@llm_available
class TestSkillAdvisor:
    @pytest.mark.asyncio
    async def test_responds_to_recommendation_request(self):
        from agents.skill_advisor.agent import root_agent

        result = await _run_agent(root_agent, "recommend skills for Kubernetes")
        assert len(result) > 0


@neo4j_available
@llm_available
class TestBundleValidator:
    @pytest.mark.asyncio
    async def test_responds_to_validation_request(self):
        from agents.bundle_validator.agent import root_agent

        result = await _run_agent(root_agent, "validate this bundle: code-review, api-security-review")
        assert len(result) > 0


@neo4j_available
@llm_available
class TestKgQa:
    @pytest.mark.asyncio
    async def test_responds_to_graph_question(self):
        from agents.kg_qa.agent import root_agent

        result = await _run_agent(root_agent, "how many skills are in the graph?")
        assert len(result) > 0


@neo4j_available
@llm_available
class TestPlayground:
    @pytest.mark.asyncio
    async def test_asks_to_select_skill(self):
        from agents.playground.agent import root_agent

        result = await _run_agent(root_agent, "hello")
        assert len(result) > 0


@neo4j_available
@llm_available
class TestSkillBuilder:
    @pytest.mark.asyncio
    async def test_responds_to_creation_request(self):
        from agents.skill_builder.agent import root_agent

        result = await _run_agent(root_agent, "create a skill for reviewing Dockerfiles")
        assert len(result) > 0
