"""Tests for payment_ops agent construction and mock tool validation."""

from __future__ import annotations

import json

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


class TestPaymentOpsAgent:
    def test_constructs(self):
        from agents.payment_ops.agent import root_agent

        assert isinstance(root_agent, Agent)

    def test_has_single_skill_toolset(self):
        from agents.payment_ops.agent import root_agent

        toolsets = [t for t in root_agent.tools if isinstance(t, SkillToolset)]
        assert len(toolsets) == 1

    def test_name_matches_config(self):
        from agents.payment_ops.agent import root_agent

        assert root_agent.name == "payment_ops"

    def test_domain_tools_registered(self):
        from agents.payment_ops.agent import root_agent

        names = _tool_names(root_agent)
        expected = {
            "get_exception_queue",
            "get_exception_detail",
            "get_payment_message",
            "get_counterparty_info",
            "check_sanctions_status",
            "get_repair_history",
            "get_fraud_score",
            "submit_repair",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"


class TestMockPaymentTools:
    """Validate that all mock tools return valid JSON and expected structure."""

    def test_get_exception_queue_returns_valid_json(self):
        from shared.payment_tools import get_exception_queue

        result = json.loads(get_exception_queue())
        assert "total" in result
        assert "exceptions" in result
        assert result["total"] == 4
        assert len(result["exceptions"]) == 4

    def test_get_exception_queue_filters_by_priority(self):
        from shared.payment_tools import get_exception_queue

        result = json.loads(get_exception_queue(priority="critical"))
        assert result["total"] == 1
        assert result["exceptions"][0]["priority"] == "critical"

    def test_get_exception_detail_found(self):
        from shared.payment_tools import get_exception_detail

        result = json.loads(get_exception_detail("EXC-2024-0847"))
        assert result["exception_id"] == "EXC-2024-0847"
        assert result["type"] == "missing_bic"
        assert result["payment_reference"] == "MT103-REF-20250513-A"

    def test_get_exception_detail_not_found(self):
        from shared.payment_tools import get_exception_detail

        result = json.loads(get_exception_detail("EXC-NONEXISTENT"))
        assert "error" in result

    def test_get_payment_message_found(self):
        from shared.payment_tools import get_payment_message

        result = get_payment_message("MT103-REF-20250513-A")
        assert "MT103" in result
        assert "ACME Corp" in result
        assert "MISSING BIC" in result

    def test_get_payment_message_not_found(self):
        from shared.payment_tools import get_payment_message

        result = get_payment_message("NONEXISTENT-REF")
        parsed = json.loads(result)
        assert "error" in parsed

    def test_get_counterparty_info_found(self):
        from shared.payment_tools import get_counterparty_info

        result = json.loads(get_counterparty_info("DEUTDEFF"))
        assert result["bic"] == "DEUTDEFF"
        assert result["bank_name"] == "Deutsche Bank AG"
        assert result["swift_member"] is True

    def test_get_counterparty_info_not_found(self):
        from shared.payment_tools import get_counterparty_info

        result = json.loads(get_counterparty_info("XXXXXX99"))
        assert "error" in result
        assert "suggestion" in result

    def test_check_sanctions_status_match(self):
        from shared.payment_tools import check_sanctions_status

        result = json.loads(check_sanctions_status("Ahmed Holdings LLC"))
        assert result["screening_result"] == "potential_match"
        assert result["match_score"] == 0.31
        assert result["match_type"] == "fuzzy_name"

    def test_check_sanctions_status_clear(self):
        from shared.payment_tools import check_sanctions_status

        result = json.loads(check_sanctions_status("Totally Innocent Corp"))
        assert result["screening_result"] == "clear"
        assert result["match_score"] == 0.0

    def test_get_repair_history_found(self):
        from shared.payment_tools import get_repair_history

        result = json.loads(get_repair_history("missing_bic"))
        assert result["exception_type"] == "missing_bic"
        assert result["auto_repair_rate"] == 0.97
        assert len(result["common_fixes"]) >= 2

    def test_get_fraud_score_found(self):
        from shared.payment_tools import get_fraud_score

        result = json.loads(get_fraud_score("MT103-REF-20250513-A"))
        assert result["fraud_score"] == 0.03
        assert result["risk_level"] == "low"
        assert len(result["contributing_factors"]) >= 3

    def test_submit_repair_success(self):
        from shared.payment_tools import submit_repair

        result = json.loads(submit_repair("EXC-2024-0847", "add_bic", "Adding DEUTDEFF"))
        assert result["status"] == "repair_submitted"
        assert result["action"] == "add_bic"
        assert "audit" in result
        assert result["audit"]["approval_status"] == "pending_human_review"

    def test_submit_repair_not_found(self):
        from shared.payment_tools import submit_repair

        result = json.loads(submit_repair("EXC-NONEXISTENT", "add_bic", "test"))
        assert "error" in result

    def test_data_consistency_across_tools(self):
        """Verify mock data is internally consistent: exception references match messages."""
        from shared.payment_tools import get_exception_detail, get_payment_message

        detail = json.loads(get_exception_detail("EXC-2024-0847"))
        ref = detail["payment_reference"]
        msg = get_payment_message(ref)
        assert "ACME Corp" in msg
        assert detail["beneficiary_name"] in msg
