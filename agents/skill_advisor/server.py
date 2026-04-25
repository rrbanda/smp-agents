"""A2A server entrypoint for the Skill Advisor agent."""

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

_cfg = get_agent_config("skill_advisor")
_a2a_cfg = _cfg.get("a2a", {})
_host = _cfg.get("host", "0.0.0.0")
_port = int(_cfg.get("port", 8001))

_agent_card = AgentCard(
    name="Skill Advisor",
    description=_cfg["description"],
    url=f"http://{_host}:{_port}/",
    version=_a2a_cfg.get("version", "0.1.0"),
    defaultInputModes=["text/plain"],
    defaultOutputModes=["application/json"],
    capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
    skills=[
        AgentSkill(
            id="skill-recommendation",
            name="Skill Recommendation",
            description=(
                "Recommends complementary skills using graph relationships"
                " (COMPLEMENTS, DEPENDS_ON, SIMILAR_TO) and semantic search."
            ),
            tags=["recommendation", "graph", "semantic-search"],
        ),
        AgentSkill(
            id="bundle-analysis",
            name="Bundle Gap Analysis",
            description="Analyzes an existing skill bundle to identify missing dependencies and complementary skills.",
            tags=["analysis", "dependencies"],
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
