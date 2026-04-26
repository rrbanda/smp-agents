#!/usr/bin/env python3
"""Run agentskills.io skill evals against live agents.

Implements the full agentskills.io eval workflow:
1. WITH skill: send prompts to agents (which have SKILL.md loaded)
2. WITHOUT skill: send same prompts to raw LLM (no skill instructions)
3. Grade assertions against both outputs
4. Compute delta proving the skill adds value
5. Save grading.json + timing.json + benchmark.json

Usage:
    # Full eval (with_skill + without_skill baseline)
    python scripts/run_skill_evals.py

    # Specific agent
    python scripts/run_skill_evals.py --agent skill_advisor

    # Skip baseline (faster, just test with_skill)
    python scripts/run_skill_evals.py --skip-baseline

    # Save results in agentskills.io workspace structure
    python scripts/run_skill_evals.py --output-dir ./skill-advisor-workspace
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.skill_eval_runner import (
    AGENT_SKILL_DIRS,
    BenchmarkResult,
    run_skill_evals,
    save_results,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _print_results(benchmark: BenchmarkResult) -> None:
    """Print eval results in a readable format."""
    delta_pct = benchmark.delta_pass_rate * 100
    skill_ok = benchmark.with_skill.pass_rate >= 0.8
    adds_value = benchmark.delta_pass_rate > 0

    status = "PASS" if (skill_ok and adds_value) else "FAIL"
    print(f"\n{'=' * 65}")
    print(f"  Skill: {benchmark.skill_name}  [{status}]")
    print(f"{'=' * 65}")

    ws = benchmark.with_skill
    wo = benchmark.without_skill
    print(
        f"  WITH skill:    {ws.passed_assertions}/{ws.total_assertions} "
        f"assertions ({ws.pass_rate:.0%}) | {ws.mean_duration_ms:.0f}ms avg"
    )
    if wo.total_assertions > 0:
        print(
            f"  WITHOUT skill: {wo.passed_assertions}/{wo.total_assertions} "
            f"assertions ({wo.pass_rate:.0%}) | {wo.mean_duration_ms:.0f}ms avg"
        )
        print(f"  DELTA:         {delta_pct:+.0f}% pass rate | {benchmark.delta_duration_ms:+.0f}ms time")
    else:
        print("  WITHOUT skill: (skipped)")
    print()

    for i, grading in enumerate(ws.gradings):
        icon = "PASS" if grading.pass_rate >= 0.8 else "FAIL"
        print(f"  [{icon}] Eval {grading.eval_id}: {grading.prompt[:65]}...")
        print(f"        with_skill: {grading.passed}/{grading.total} assertions")

        if i < len(wo.gradings):
            wog = wo.gradings[i]
            print(f"        without:    {wog.passed}/{wog.total} assertions")

        for ar in grading.assertion_results:
            mark = "+" if ar.passed else "-"
            print(f"        [{mark}] {ar.text}")
            if ar.evidence:
                print(f"             {ar.evidence[:80]}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run agentskills.io skill evals (with vs without skill)")
    parser.add_argument(
        "--agent",
        choices=list(AGENT_SKILL_DIRS.keys()),
        help="Run evals for a specific agent (default: all)",
    )
    parser.add_argument("--base-url", help="Override A2A base URL")
    parser.add_argument(
        "--no-llm-grading",
        action="store_true",
        help="Use heuristic grading instead of LLM-as-judge",
    )
    parser.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Skip without_skill baseline (faster, less rigorous)",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for agentskills.io workspace output",
    )
    parser.add_argument(
        "--iteration",
        type=int,
        default=1,
        help="Iteration number for workspace structure (default: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Request timeout in seconds (default: 120)",
    )
    args = parser.parse_args()

    agents = [args.agent] if args.agent else list(AGENT_SKILL_DIRS.keys())
    all_passed = True

    for agent_name in agents:
        logger.info("Running skill evals for %s...", agent_name)
        try:
            benchmark = run_skill_evals(
                agent_name,
                base_url=args.base_url,
                use_llm_grading=not args.no_llm_grading,
                skip_baseline=args.skip_baseline,
                timeout=args.timeout,
            )
            _print_results(benchmark)

            if args.output_dir:
                out = Path(args.output_dir) / agent_name
                save_results(benchmark, out, iteration=args.iteration)

            if benchmark.with_skill.pass_rate < 0.8:
                all_passed = False
            if not args.skip_baseline and benchmark.delta_pass_rate <= 0:
                logger.warning(
                    "  %s: skill did NOT improve over baseline (delta=%.0f%%)",
                    agent_name,
                    benchmark.delta_pass_rate * 100,
                )

        except FileNotFoundError as exc:
            logger.warning("Skipping %s: %s", agent_name, exc)
        except Exception as exc:
            logger.error("Failed running evals for %s: %s", agent_name, exc)
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
