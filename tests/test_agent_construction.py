"""Tests for agent construction -- verifies all 5 agents import and wire correctly."""

from __future__ import annotations

from google.adk import Agent
from google.adk.tools.skill_toolset import SkillToolset


class TestSkillAdvisorAgent:
    def test_constructs(self):
        from agents.skill_advisor.agent import root_agent

        assert isinstance(root_agent, Agent)

    def test_has_single_skill_toolset(self):
        from agents.skill_advisor.agent import root_agent

        toolsets = [t for t in root_agent.tools if isinstance(t, SkillToolset)]
        assert len(toolsets) == 1

    def test_name_matches_config(self):
        from agents.skill_advisor.agent import root_agent

        assert root_agent.name == "skill_advisor"


class TestBundleValidatorAgent:
    def test_constructs(self):
        from agents.bundle_validator.agent import root_agent

        assert isinstance(root_agent, Agent)

    def test_has_single_skill_toolset(self):
        from agents.bundle_validator.agent import root_agent

        toolsets = [t for t in root_agent.tools if isinstance(t, SkillToolset)]
        assert len(toolsets) == 1

    def test_name_matches_config(self):
        from agents.bundle_validator.agent import root_agent

        assert root_agent.name == "bundle_validator"


class TestKgQaAgent:
    def test_constructs(self):
        from agents.kg_qa.agent import root_agent

        assert isinstance(root_agent, Agent)

    def test_has_single_skill_toolset(self):
        from agents.kg_qa.agent import root_agent

        toolsets = [t for t in root_agent.tools if isinstance(t, SkillToolset)]
        assert len(toolsets) == 1

    def test_name_matches_config(self):
        from agents.kg_qa.agent import root_agent

        assert root_agent.name == "kg_qa"


class TestPlaygroundAgent:
    def test_constructs(self):
        from agents.playground.agent import root_agent

        assert isinstance(root_agent, Agent)

    def test_has_single_skill_toolset(self):
        from agents.playground.agent import root_agent

        toolsets = [t for t in root_agent.tools if isinstance(t, SkillToolset)]
        assert len(toolsets) == 1

    def test_name_matches_config(self):
        from agents.playground.agent import root_agent

        assert root_agent.name == "playground"


class TestSkillBuilderAgent:
    def test_constructs(self):
        from agents.skill_builder.agent import root_agent

        assert isinstance(root_agent, Agent)

    def test_has_single_skill_toolset(self):
        from agents.skill_builder.agent import root_agent

        toolsets = [t for t in root_agent.tools if isinstance(t, SkillToolset)]
        assert len(toolsets) == 1

    def test_name_matches_config(self):
        from agents.skill_builder.agent import root_agent

        assert root_agent.name == "skill_builder"
