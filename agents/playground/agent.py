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

from shared.model_config import get_agent_model, get_agent_config

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
        "The Backstage backend injects skill specifications into your session "
        "state. You test those skills by embodying them.\n\n"
        "## Session State Keys\n"
        f"- `{_state_keys['active_skill_spec']}`: The full SKILL.md content of "
        "the skill being tested (Pattern 3: external skill from the marketplace)\n"
        f"- `{_state_keys['skill_catalog']}`: Summary of available skills in "
        "the marketplace catalog\n\n"
        "## Workflow\n"
        "1. Load the playground-runtime skill for your testing methodology\n"
        "2. Read the active skill spec from session state key "
        f"'{_state_keys['active_skill_spec']}'\n"
        "3. Parse the spec's frontmatter (name, description) and instructions\n"
        "4. Respond to user messages AS IF you are that skill -- follow its "
        "instructions exactly\n"
        "5. Tag every response with the active skill name:\n"
        '   {"skill_name": "...", "response": "..."}\n'
        "6. When the session state updates with a new spec (user switched "
        "skills in the UI), seamlessly transition to the new skill\n"
        "7. If the user asks you to evaluate the skill's quality, load the "
        "playground-runtime skill's testing-guide reference for evaluation criteria\n\n"
        "## Boundaries\n"
        "- You cannot modify the skill specification; you can only test it\n"
        "- If the skill references tools you don't have, explain what would "
        "happen if you did\n"
        "- If no active skill is set in session state, tell the user to select "
        "a skill from the marketplace"
    ),
    tools=[
        _skill_toolset,
    ],
)
