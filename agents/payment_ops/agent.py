"""Payment Operations Agent -- Exception Repair at the Operational Seam.

Uses a Pattern 2 file-based skill (exception-repair) with L3 references
for SWIFT message formats, repair procedures, and ISO 20022 error codes.
All payment tools are mock implementations returning realistic hardcoded
data; swap function bodies for real APIs without changing signatures.
"""

import pathlib

from google.adk import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from shared.model_config import get_agent_config, get_agent_model
from shared.payment_tools import (
    check_sanctions_status,
    get_counterparty_info,
    get_exception_detail,
    get_exception_queue,
    get_fraud_score,
    get_payment_message,
    get_repair_history,
    submit_repair,
)

_cfg = get_agent_config("payment_ops")
_skills_dir = pathlib.Path(__file__).parent / "skills"

_repair_skill = load_skill_from_dir(_skills_dir / "exception-repair")
_skill_toolset = SkillToolset(skills=[_repair_skill])

root_agent = Agent(
    model=get_agent_model(),
    name=_cfg["name"],
    description=_cfg["description"],
    instruction=(
        "You are a Payment Operations agent that diagnoses and repairs "
        "payment exceptions across SWIFT, settlement, and compliance systems.\n\n"
        "You operate in ASSIST mode: you investigate, diagnose, and recommend — "
        "but a human operator approves every repair action before execution.\n\n"
        "Workflow:\n"
        "1. Load the exception-repair skill for your diagnostic methodology\n"
        "2. Use get_exception_queue to review pending exceptions\n"
        "3. Use get_exception_detail to pull full context for a specific exception\n"
        "4. Use get_payment_message to retrieve the original SWIFT MT103\n"
        "5. Cross-reference with get_counterparty_info, check_sanctions_status, "
        "and get_fraud_score as appropriate for the exception type\n"
        "6. Use get_repair_history to check how this exception type has been "
        "resolved historically and what the auto-repair success rate is\n"
        "7. Use load_skill_resource to read references/swift-message-formats.md, "
        "references/repair-procedures.md, or references/iso20022-error-codes.md "
        "when you need field-level or procedure details\n"
        "8. Present a structured diagnosis with evidence, confidence level, "
        "and a specific repair recommendation\n"
        "9. Wait for human approval before calling submit_repair\n\n"
        "Rules:\n"
        "- Always show your work: state which tools you called and what you found\n"
        "- Never auto-repair amount mismatches (policy CP-PAY-007)\n"
        "- Never release sanctions holds without explicitly noting that "
        "compliance officer sign-off is required (policy CP-BSA-012)\n"
        "- Include the fraud risk score in every diagnosis\n"
        "- When recommending a repair, cite the historical success rate\n"
        "- Present output in clear structured format with diagnosis, evidence, "
        "and recommended action"
    ),
    tools=[
        _skill_toolset,
        get_exception_queue,
        get_exception_detail,
        get_payment_message,
        get_counterparty_info,
        check_sanctions_status,
        get_repair_history,
        get_fraud_score,
        submit_repair,
    ],
)
