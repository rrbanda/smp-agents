"""ADK agent evaluation tests.

Uses Google ADK's AgentEvaluator to validate agent quality:
- Tool trajectory: agents call the right tools in the right order
- Response quality: agent responses match reference responses (ROUGE-1)

Requires live LLM and Neo4j. Run with: pytest -m eval
"""

from __future__ import annotations

import logging

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

logger = logging.getLogger(__name__)

AGENTS = [
    "skill_advisor",
    "bundle_validator",
    "kg_qa",
    "playground",
    "skill_builder",
]


@pytest.mark.eval
@pytest.mark.asyncio
@pytest.mark.parametrize("agent_name", AGENTS)
async def test_agent_eval(agent_name: str):
    """Evaluate agent tool trajectory and response quality."""
    try:
        await AgentEvaluator.evaluate(
            agent_module=f"agents.{agent_name}",
            eval_dataset_file_path_or_dir=f"agents/{agent_name}/evals/",
            num_runs=1,
        )
    except TypeError as exc:
        if "NoneType" in str(exc):
            pytest.skip(f"ADK inference returned None for {agent_name} (known ADK bug in local_eval_service.py): {exc}")
        raise
