"""A2A server entrypoint for the KG Q&A agent."""

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

_cfg = get_agent_config("kg_qa")
_a2a_cfg = _cfg.get("a2a", {})
_host = _cfg.get("host", "0.0.0.0")
_port = int(_cfg.get("port", 8003))

_agent_card = AgentCard(
    name="Knowledge Graph Q&A",
    description=_cfg["description"],
    url=f"http://{_host}:{_port}/",
    version=_a2a_cfg.get("version", "0.1.0"),
    default_input_modes=["text/plain"],
    default_output_modes=["application/json"],
    capabilities=AgentCapabilities(streaming=False, push_notifications=False),
    skills=[
        AgentSkill(
            id="graph-qa",
            name="Graph Question Answering",
            description=(
                "Translates natural-language questions into Cypher queries and returns grounded answers from Neo4j."
            ),
            tags=["qa", "graph", "cypher", "neo4j"],
        ),
        AgentSkill(
            id="skill-lookup",
            name="Skill Lookup",
            description="Finds skills by name or id and returns full graph properties.",
            tags=["lookup", "search"],
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
