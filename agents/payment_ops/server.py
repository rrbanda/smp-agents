"""A2A server entrypoint for the Payment Operations agent."""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

import litellm  # noqa: E402

litellm.disable_aiohttp_transport = True

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from a2a.types import AgentCapabilities, AgentCard, AgentSkill  # noqa: E402
from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from shared.health import health_routes  # noqa: E402
from shared.model_config import get_agent_config, validate_env  # noqa: E402

from .agent import root_agent  # noqa: E402

_missing = validate_env()
if _missing:
    logging.getLogger(__name__).warning("Missing env vars (may cause runtime errors): %s", _missing)

_cfg = get_agent_config("payment_ops")
_a2a_cfg = _cfg.get("a2a", {})
_host = _cfg.get("host", "0.0.0.0")
_port = int(_cfg.get("port", 8006))

_agent_card = AgentCard(
    name="Payment Operations",
    description=_cfg["description"],
    url=f"http://{_host}:{_port}/",
    version=_a2a_cfg.get("version", "0.1.0"),
    default_input_modes=["text/plain"],
    default_output_modes=["application/json"],
    capabilities=AgentCapabilities(streaming=False, push_notifications=False),
    skills=[
        AgentSkill(
            id="exception-diagnosis",
            name="Exception Diagnosis",
            description=(
                "Diagnoses payment exceptions by correlating data across "
                "payment gateway, settlement, sanctions, and fraud systems. "
                "Provides structured root-cause analysis with evidence."
            ),
            tags=["payments", "diagnosis", "swift", "exceptions"],
        ),
        AgentSkill(
            id="repair-recommendation",
            name="Repair Recommendation",
            description=(
                "Recommends repair actions based on historical patterns, "
                "compliance policy, and ML fraud scores. Supports human-in-the-loop "
                "approval before execution."
            ),
            tags=["payments", "repair", "compliance", "human-in-the-loop"],
        ),
    ],
)

app = to_a2a(
    root_agent,
    host=_host,
    port=_port,
    protocol="http",
    agent_card=_agent_card,
)
app.routes.extend(health_routes)
