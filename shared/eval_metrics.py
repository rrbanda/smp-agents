"""Custom ADK evaluation metrics for smp-agents.

Provides a tool_coverage metric that verifies agents use at least one
domain-specific tool (not just SkillToolset framework tools).
"""

from __future__ import annotations

import statistics

from google.adk.evaluation.conversation_scenarios import ConversationScenario
from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import EvalMetric, EvalStatus
from google.adk.evaluation.evaluator import EvaluationResult, PerInvocationResult

DOMAIN_TOOLS = frozenset(
    {
        "semantic_search_skills",
        "query_skill_graph",
        "find_skill",
        "get_skill_dependencies",
        "get_complementary_skills",
        "get_skill_alternatives",
        "explore_skill_neighborhood",
        "get_skill_similarity",
        "validate_skill_yaml",
        "publish_skill_to_oci",
    }
)


def tool_coverage(
    eval_metric: EvalMetric,
    actual_invocations: list[Invocation],
    expected_invocations: list[Invocation] | None,
    conversation_scenario: ConversationScenario | None,
) -> EvaluationResult:
    """Check that the agent invoked at least one domain-specific tool.

    Scores 1.0 if any tool call in the invocation matches a known domain tool,
    0.0 otherwise. Useful for catching regressions where agents stop using
    graph/search tools and rely only on SkillToolset framework tools.
    """
    per_invocation_results: list[PerInvocationResult] = []

    for invocation in actual_invocations:
        tool_names: set[str] = set()
        idata = invocation.intermediate_data
        if isinstance(idata, IntermediateData) and idata.tool_uses:
            for tool_use in idata.tool_uses:
                if tool_use.name is not None:
                    tool_names.add(tool_use.name)

        used_domain_tool = bool(tool_names & DOMAIN_TOOLS)
        score = 1.0 if used_domain_tool else 0.0
        eval_status = EvalStatus.PASSED if used_domain_tool else EvalStatus.FAILED

        per_invocation_results.append(
            PerInvocationResult(
                actual_invocation=invocation,
                score=score,
                eval_status=eval_status,
            )
        )

    if not per_invocation_results:
        return EvaluationResult(
            overall_score=0.0,
            overall_eval_status=EvalStatus.NOT_EVALUATED,
        )

    scores = [r.score for r in per_invocation_results if r.score is not None]
    average_score = statistics.mean(scores) if scores else 0.0
    threshold = 0.8
    if eval_metric.criterion is not None and eval_metric.criterion.threshold is not None:
        threshold = eval_metric.criterion.threshold
    overall_status = EvalStatus.PASSED if average_score >= threshold else EvalStatus.FAILED

    return EvaluationResult(
        overall_score=average_score,
        overall_eval_status=overall_status,
        per_invocation_results=per_invocation_results,
    )
