"""Playground Agent -- Patterns 2 + 3 (dynamic external).

Uses a Pattern 2 file-based skill for the testing methodology, and treats
skills injected via session state as Pattern 3 external skills. The Backstage
UI sends the active skill specification via session state PATCH, and the
agent's instructions tell it to read and follow that spec.
"""

import pathlib

from google.adk import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from shared.catalog_tools import get_skill_content, search_skill_catalog
from shared.model_config import get_agent_config, get_agent_model

_cfg = get_agent_config("playground")
_state_keys = _cfg["state_keys"]
_skills_dir = pathlib.Path(__file__).parent / "skills"

# Pattern 2: File-based skill for testing methodology
_runtime_skill = load_skill_from_dir(_skills_dir / "playground-runtime")
_skill_toolset = SkillToolset(skills=[_runtime_skill])

root_agent = Agent(
    model=get_agent_model(),
    name=_cfg["name"],
    description=_cfg["description"],
    instruction=(
        "You are a Skills Playground agent for testing skills interactively.\n\n"
        "## How It Works\n"
        "You can load skills from the Skill Catalog API or from session state "
        "injected by the Backstage UI.\n\n"
        "## Loading Skills\n"
        "- Use search_skill_catalog to browse available skills by name, "
        "namespace, tags, or status\n"
        "- Use get_skill_content to fetch the full SKILL.md for any skill "
        "by namespace, name, and version\n"
        "- Session state can also provide skills:\n"
        f"  - `{_state_keys['active_skill_spec']}`: SKILL.md content injected "
        "by the Backstage UI\n"
        f"  - `{_state_keys['skill_catalog']}`: Summary of available skills\n\n"
        "## Workflow\n"
        "1. Load the playground-runtime skill for your testing methodology\n"
        "2. If the user names a skill, use search_skill_catalog to find it, "
        "then get_skill_content to fetch its SKILL.md\n"
        "3. If session state has an active spec, use that instead\n"
        "4. Parse the spec's frontmatter (name, description) and instructions\n"
        "5. Respond to user messages AS IF you are that skill -- follow its "
        "instructions exactly\n"
        "6. Tag every response with the active skill name:\n"
        '   {"skill_name": "...", "response": "..."}\n'
        "7. When the user asks to switch skills, fetch the new spec via "
        "get_skill_content\n"
        "8. If the user asks you to evaluate the skill's quality, load the "
        "playground-runtime skill's testing-guide reference for evaluation criteria\n\n"
        "## Boundaries\n"
        "- You cannot modify the skill specification; you can only test it\n"
        "- If the skill references tools you don't have, explain what would "
        "happen if you did\n"
        "- If no active skill is set, use search_skill_catalog to help the "
        "user browse and select one"
    ),
    tools=[
        _skill_toolset,
        search_skill_catalog,
        get_skill_content,
    ],
)
