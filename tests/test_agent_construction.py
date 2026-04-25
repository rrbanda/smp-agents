"""Tests for agent construction -- verifies all 5 agents import and wire correctly."""

from __future__ import annotations

from google.adk import Agent
from google.adk.tools.skill_toolset import SkillToolset


def _tool_names(agent: Agent) -> set[str]:
    """Extract callable tool function names registered directly on an agent."""
    names: set[str] = set()
    for t in agent.tools:
        if isinstance(t, SkillToolset):
            continue
        if callable(t) and hasattr(t, "__name__"):
            names.add(t.__name__)
    return names


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

    def test_domain_tools_registered(self):
        from agents.skill_advisor.agent import root_agent

        names = _tool_names(root_agent)
        expected = {
            "search_skill_catalog",
            "semantic_search_skills",
            "query_skill_graph",
            "get_skill_dependencies",
            "get_complementary_skills",
            "get_skill_alternatives",
            "get_skill_similarity",
            "explore_skill_neighborhood",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"


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

    def test_domain_tools_registered(self):
        from agents.bundle_validator.agent import root_agent

        names = _tool_names(root_agent)
        expected = {
            "get_skill_detail",
            "get_skill_versions",
            "query_skill_graph",
            "find_skill",
            "get_skill_dependencies",
            "get_skill_similarity",
            "get_skill_alternatives",
            "get_complementary_skills",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"


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

    def test_domain_tools_registered(self):
        from agents.kg_qa.agent import root_agent

        names = _tool_names(root_agent)
        expected = {
            "query_skill_graph",
            "find_skill",
            "explore_skill_neighborhood",
            "get_skill_dependencies",
            "semantic_search_skills",
            "get_skill_similarity",
            "get_graph_context",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"


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

    def test_domain_tools_registered(self):
        from agents.playground.agent import root_agent

        names = _tool_names(root_agent)
        expected = {
            "search_skill_catalog",
            "get_skill_content",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"


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

    def test_domain_tools_registered(self):
        from agents.skill_builder.agent import root_agent

        names = _tool_names(root_agent)
        expected = {
            "validate_skill_yaml",
            "publish_skill_to_oci",
            "trigger_catalog_sync",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"
