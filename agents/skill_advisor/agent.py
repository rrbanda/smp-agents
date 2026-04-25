"""Skill Advisor Agent -- Patterns 1 + 2.

Combines a Pattern 1 inline skill (output format) with a Pattern 2 file-based
skill (recommendation methodology with L3 references). Demonstrates both
patterns in a single SkillToolset.
"""

import pathlib

from google.adk import Agent
from google.adk.skills import models
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from shared.model_config import get_agent_model, get_agent_config
from shared.neo4j_tools import (
    query_skill_graph,
    get_skill_dependencies,
    get_complementary_skills,
    get_skill_alternatives,
    explore_skill_neighborhood,
)
from shared.semantic_search_tools import semantic_search_skills

_cfg = get_agent_config("skill_advisor")
_skills_dir = pathlib.Path(__file__).parent / "skills"

# Pattern 1: Inline skill -- stable output format, rarely changes
_output_format_skill = models.Skill(
    frontmatter=models.Frontmatter(
        name="advisor-output-format",
        description=(
            "JSON output format for skill recommendation cards. "
            "Defines the schema the UI expects for rendering results."
        ),
    ),
    instructions=(
        "When returning skill recommendations, use this JSON array format:\n\n"
        "```json\n"
        "[\n"
        "  {\n"
        '    "skill_name": "deploy-to-k8s",\n'
        '    "score": 0.92,\n'
        '    "reason": "Complements your CI/CD skills with deployment capability",\n'
        '    "category": "DevOps",\n'
        '    "relationship": "COMPLEMENTS build-container"\n'
        "  }\n"
        "]\n"
        "```\n\n"
        "Fields:\n"
        "- skill_name: The skill's kebab-case identifier\n"
        "- score: Composite score from 0.0 to 1.0, rounded to 2 decimals\n"
        "- reason: One sentence explaining why this skill is recommended\n"
        "- category: The skill's domain/category\n"
        "- relationship: Graph edge type (DEPENDS_ON, COMPLEMENTS, ALTERNATIVE_TO, "
        "EXTENDS, SIMILAR_TO, SAME_PLUGIN)\n\n"
        "Maximum 10 recommendations per response. Minimum score threshold: 0.3."
    ),
)

# Pattern 2: File-based skill -- has L3 reference for scoring strategy
_advisor_skill = load_skill_from_dir(_skills_dir / "skill-advisor")

_skill_toolset = SkillToolset(skills=[_output_format_skill, _advisor_skill])

root_agent = Agent(
    model=get_agent_model(),
    name=_cfg["name"],
    description=_cfg["description"],
    instruction=(
        "You are a Skill Advisor for the Skills Marketplace.\n\n"
        "Your job is to recommend complementary skills based on what the user "
        "describes and what is already in their bundle cart.\n\n"
        "1. Load the skill-advisor skill for your recommendation methodology\n"
        "2. Use semantic_search_skills to find relevant skills by meaning\n"
        "3. Use get_complementary_skills to find workflow partners (COMPLEMENTS)\n"
        "4. Use get_skill_dependencies to check dependency chains (DEPENDS_ON)\n"
        "5. Use get_skill_alternatives to find interchangeable options\n"
        "6. Use explore_skill_neighborhood for broader graph context\n"
        "7. Filter out skills already in the cart (from session state '_cart_skills')\n"
        "8. Load the advisor-output-format skill for the response schema\n"
        "9. Return ranked recommendations in the specified JSON format"
    ),
    tools=[
        _skill_toolset,
        semantic_search_skills,
        query_skill_graph,
        get_skill_dependencies,
        get_complementary_skills,
        get_skill_alternatives,
        explore_skill_neighborhood,
    ],
)
