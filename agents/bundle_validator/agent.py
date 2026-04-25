"""Bundle Validator Agent -- validates skill bundles for completeness and quality."""

import pathlib

from google.adk import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from shared.model_config import get_agent_model, get_agent_config
from shared.neo4j_tools import (
    query_skill_graph,
    find_skill,
    get_skill_dependencies,
    get_skill_similarity,
    get_skill_alternatives,
    get_complementary_skills,
)

_cfg = get_agent_config("bundle_validator")
_skills_dir = pathlib.Path(__file__).parent / "skills"

_validator_skill = load_skill_from_dir(_skills_dir / "bundle-validator")
_skill_toolset = SkillToolset(skills=[_validator_skill])

root_agent = Agent(
    model=get_agent_model(),
    name=_cfg["name"],
    description=_cfg["description"],
    instruction=(
        "You are a Bundle Validator for the Skills Marketplace.\n\n"
        "Your job is to analyze a curated set of skills and flag quality issues.\n\n"
        "1. Load the bundle-validator skill for your validation methodology\n"
        "2. Read the bundle skill list from session state '_bundle_skills'\n"
        "3. Use find_skill to verify each skill exists in the graph\n"
        "4. Use get_skill_dependencies to check for missing transitive DEPENDS_ON chains\n"
        "5. Use get_skill_alternatives to detect redundant ALTERNATIVE_TO pairs\n"
        "6. Use get_complementary_skills to suggest missing workflow partners\n"
        "7. Use query_skill_graph for custom Cypher when needed\n"
        "8. Categorize each finding as error, warning, or info\n\n"
        "Return all findings as a structured JSON array."
    ),
    tools=[
        _skill_toolset,
        query_skill_graph,
        find_skill,
        get_skill_dependencies,
        get_skill_similarity,
        get_skill_alternatives,
        get_complementary_skills,
    ],
)
