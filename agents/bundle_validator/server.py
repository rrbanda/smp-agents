"""A2A server entrypoint for the Bundle Validator agent."""

from dotenv import load_dotenv

load_dotenv()

from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from .agent import root_agent  # noqa: E402
from shared.model_config import get_agent_config  # noqa: E402

_cfg = get_agent_config("bundle_validator")

app = to_a2a(
    root_agent,
    host=_cfg.get("host", "0.0.0.0"),
    port=int(_cfg.get("port", 8002)),
    protocol="http",
)
