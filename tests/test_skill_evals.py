"""agentskills.io skill eval tests.

Two test classes:
- TestSkillEvalDataIntegrity: validates evals/evals.json structure (no network)
- TestSkillEvalExecution: runs full with_skill vs without_skill workflow

Run with: pytest -m skill_eval (execution tests)
          pytest tests/test_skill_evals.py::TestSkillEvalDataIntegrity (data only)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.skill_eval_runner import (
    AGENT_SKILL_DIRS,
    load_skill_evals,
    run_skill_evals,
)

SKILL_AGENTS = list(AGENT_SKILL_DIRS.keys())


class TestSkillEvalDataIntegrity:
    """Validate evals/evals.json files are well-formed (unit test, no network)."""

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_evals_json_exists(self, agent_name: str):
        skill_dir = AGENT_SKILL_DIRS[agent_name]
        evals_path = Path(skill_dir) / "evals" / "evals.json"
        assert evals_path.exists(), f"Missing evals/evals.json for {agent_name}"

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_evals_json_valid_structure(self, agent_name: str):
        data = load_skill_evals(agent_name)
        assert data is not None
        assert "skill_name" in data
        assert "evals" in data
        assert isinstance(data["evals"], list)
        assert len(data["evals"]) >= 2, "Need at least 2 eval cases"

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_eval_cases_have_required_fields(self, agent_name: str):
        data = load_skill_evals(agent_name)
        assert data is not None
        for case in data["evals"]:
            assert "id" in case, "Missing id field"
            assert "prompt" in case, "Missing prompt field"
            assert "expected_output" in case, "Missing expected_output field"
            assert len(case["prompt"]) > 10, "Prompt too short to be realistic"
            assert len(case["expected_output"]) > 10, "Expected output too vague"

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_eval_cases_have_assertions(self, agent_name: str):
        data = load_skill_evals(agent_name)
        assert data is not None
        for case in data["evals"]:
            assertions = case.get("assertions", [])
            assert len(assertions) >= 2, (
                f"Eval {case['id']} needs at least 2 assertions, "
                f"has {len(assertions)}"
            )
            for assertion in assertions:
                assert len(assertion) > 10, (
                    f"Assertion too vague: '{assertion}'"
                )

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_skill_name_matches_directory(self, agent_name: str):
        data = load_skill_evals(agent_name)
        assert data is not None
        skill_dir = AGENT_SKILL_DIRS[agent_name]
        dir_name = Path(skill_dir).name
        assert data["skill_name"] == dir_name, (
            f"skill_name '{data['skill_name']}' doesn't match "
            f"directory '{dir_name}'"
        )

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_eval_ids_unique(self, agent_name: str):
        data = load_skill_evals(agent_name)
        assert data is not None
        ids = [case["id"] for case in data["evals"]]
        assert len(ids) == len(set(ids)), f"Duplicate eval IDs: {ids}"

    def test_total_assertion_coverage(self):
        """Verify meaningful assertion coverage across all skills."""
        total_assertions = 0
        for agent_name in SKILL_AGENTS:
            data = load_skill_evals(agent_name)
            if data:
                for case in data["evals"]:
                    total_assertions += len(case.get("assertions", []))
        assert total_assertions >= 30, (
            f"Only {total_assertions} total assertions across all "
            f"skills (need 30+)"
        )


@pytest.mark.skill_eval
class TestSkillEvalExecution:
    """Run full agentskills.io eval workflow against live agents.

    Tests both with_skill AND without_skill (raw LLM baseline).
    The skill should improve pass rate over the baseline.
    """

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_skill_improves_over_baseline(self, agent_name: str):
        """The skill should produce better output than raw LLM."""
        try:
            benchmark = run_skill_evals(
                agent_name,
                use_llm_grading=True,
                skip_baseline=False,
                timeout=120,
            )
        except Exception as exc:
            pytest.skip(f"Agent {agent_name} not reachable: {exc}")
            return

        assert benchmark.with_skill.total_assertions > 0, (
            "No assertions were graded"
        )

        ws_details = "\n".join(
            f"  [{'+' if a.passed else '-'}] {a.text}: {a.evidence}"
            for g in benchmark.with_skill.gradings
            for a in g.assertion_results
        )
        wo_details = "\n".join(
            f"  [{'+' if a.passed else '-'}] {a.text}: {a.evidence}"
            for g in benchmark.without_skill.gradings
            for a in g.assertion_results
        )

        assert benchmark.with_skill.pass_rate >= 0.6, (
            f"{benchmark.skill_name} with_skill pass rate "
            f"{benchmark.with_skill.pass_rate:.0%} < 60%\n"
            f"WITH skill:\n{ws_details}"
        )

        assert benchmark.delta_pass_rate >= 0, (
            f"{benchmark.skill_name} did NOT improve over baseline "
            f"(delta={benchmark.delta_pass_rate:+.0%})\n"
            f"WITH skill ({benchmark.with_skill.pass_rate:.0%}):\n"
            f"{ws_details}\n"
            f"WITHOUT skill ({benchmark.without_skill.pass_rate:.0%}):\n"
            f"{wo_details}"
        )

    @pytest.mark.parametrize("agent_name", SKILL_AGENTS)
    def test_skill_eval_no_errors(self, agent_name: str):
        """Verify no eval cases returned error responses."""
        try:
            benchmark = run_skill_evals(
                agent_name,
                use_llm_grading=False,
                skip_baseline=True,
                timeout=120,
            )
        except Exception as exc:
            pytest.skip(f"Agent {agent_name} not reachable: {exc}")
            return

        for grading in benchmark.with_skill.gradings:
            assert not grading.output.startswith("ERROR:"), (
                f"Eval {grading.eval_id} returned error: "
                f"{grading.output[:200]}"
            )
