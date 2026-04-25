"""A2A server entrypoint for the Bundle Validator agent."""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

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

_cfg = get_agent_config("bundle_validator")
_a2a_cfg = _cfg.get("a2a", {})
_host = _cfg.get("host", "0.0.0.0")
_port = int(_cfg.get("port", 8002))

_agent_card = AgentCard(
    name="Bundle Validator",
    description=_cfg["description"],
    url=f"http://{_host}:{_port}/",
    version=_a2a_cfg.get("version", "0.1.0"),
    defaultInputModes=["application/json"],
    defaultOutputModes=["application/json"],
    capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
    skills=[
        AgentSkill(
            id="bundle-validation",
            name="Bundle Validation",
            description=(
                "Validates a skill bundle for missing dependencies, redundant alternatives, and completeness gaps."
            ),
            tags=["validation", "dependencies", "quality"],
        ),
        AgentSkill(
            id="dependency-audit",
            name="Dependency Audit",
            description="Checks transitive DEPENDS_ON chains and flags missing skills.",
            tags=["audit", "dependencies"],
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
