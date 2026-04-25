"""ADK agent evaluation tests.

Uses Google ADK's AgentEvaluator to validate agent quality:
- Tool trajectory: agents call the right tools in the right order
- Response quality: agent responses match reference responses (ROUGE-1)

Requires live LLM and Neo4j. Run with: pytest -m eval
"""

from __future__ import annotations

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator


@pytest.mark.eval
@pytest.mark.asyncio
async def test_skill_advisor_eval():
    """Evaluate Skill Advisor tool trajectory and response quality."""
    await AgentEvaluator.evaluate(
        agent_module="agents.skill_advisor",
        eval_dataset_file_path_or_dir="agents/skill_advisor/evals/",
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_bundle_validator_eval():
    """Evaluate Bundle Validator tool trajectory and response quality."""
    await AgentEvaluator.evaluate(
        agent_module="agents.bundle_validator",
        eval_dataset_file_path_or_dir="agents/bundle_validator/evals/",
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_kg_qa_eval():
    """Evaluate KG Q&A tool trajectory and response quality."""
    await AgentEvaluator.evaluate(
        agent_module="agents.kg_qa",
        eval_dataset_file_path_or_dir="agents/kg_qa/evals/",
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_playground_eval():
    """Evaluate Playground response quality (no external tools expected)."""
    await AgentEvaluator.evaluate(
        agent_module="agents.playground",
        eval_dataset_file_path_or_dir="agents/playground/evals/",
    )


@pytest.mark.eval
@pytest.mark.asyncio
async def test_skill_builder_eval():
    """Evaluate Skill Builder tool trajectory and response quality."""
    await AgentEvaluator.evaluate(
        agent_module="agents.skill_builder",
        eval_dataset_file_path_or_dir="agents/skill_builder/evals/",
    )
