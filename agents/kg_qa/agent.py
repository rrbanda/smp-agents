"""Knowledge Graph Q&A Agent -- answers questions grounded in Neo4j graph data."""

import pathlib

from google.adk import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from shared.model_config import get_agent_config, get_agent_model
from shared.neo4j_tools import (
    explore_skill_neighborhood,
    find_skill,
    get_skill_dependencies,
    query_skill_graph,
)

_cfg = get_agent_config("kg_qa")
_skills_dir = pathlib.Path(__file__).parent / "skills"

_kg_skill = load_skill_from_dir(_skills_dir / "kg-qa")
_skill_toolset = SkillToolset(
    skills=[_kg_skill],
    additional_tools=[
        query_skill_graph,
        find_skill,
        explore_skill_neighborhood,
        get_skill_dependencies,
    ],
)

root_agent = Agent(
    model=get_agent_model(),
    name=_cfg["name"],
    description=_cfg["description"],
    instruction=(
        "You are a Knowledge Graph Q&A agent for the Skills Marketplace.\n\n"
        "Your job is to answer natural-language questions about the skill ecosystem "
        "grounded in real Neo4j graph data. Never hallucinate counts or names.\n\n"
        "1. Load the kg-qa skill for your query methodology\n"
        "2. Use load_skill_resource to read the graph schema and Cypher patterns\n"
        "3. Translate the user's question into a Cypher query\n"
        "4. Execute via query_skill_graph for custom Cypher\n"
        "5. Use find_skill for quick skill lookups\n"
        "6. Use explore_skill_neighborhood for one-hop graph exploration\n"
        "7. Use get_skill_dependencies for dependency chain analysis\n"
        "8. Compose a grounded answer citing actual data\n"
        "9. Return node names in 'highlighted_nodes' so the UI can highlight them\n\n"
        "Remember: Skills may be keyed by either `name` or `id`. Always use:\n"
        "  WHERE s.name = $identifier OR s.id = $identifier\n\n"
        "Always include the Cypher query used in your response."
    ),
    tools=[_skill_toolset],
)
