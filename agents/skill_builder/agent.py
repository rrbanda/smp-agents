"""Skill Builder Agent -- Pattern 4: Meta Skill Factory.

Uses an inline models.Skill with models.Resources to embed the agentskills.io
specification, a working example, and OCI publishing guide as L3 references.
The agent reads these via load_skill_resource to generate new skill specs.
"""

from google.adk import Agent
from google.adk.skills import models
from google.adk.tools.skill_toolset import SkillToolset

from shared.model_config import get_agent_model, get_agent_config
from shared.oci_tools import publish_skill_to_oci, validate_skill_yaml

_cfg = get_agent_config("skill_builder")

_SPEC_CONTENT = """\
# agentskills.io Specification Format

A skill is a Markdown file (`SKILL.md`) with YAML frontmatter. The structure is:

```markdown
---
name: my-skill-name
description: A brief description of what this skill does (max 1000 characters).
---

# Instructions

The body contains step-by-step instructions for how an LLM should behave
when this skill is loaded into its context.
```

## Frontmatter Fields

| Field | Required | Type | Constraints |
|-------|----------|------|-------------|
| name | Yes | string | Must be kebab-case (lowercase, hyphens only). Must match the directory name. |
| description | Yes | string | Max 1000 characters. Should be a single sentence. |

## Directory Structure

```
my-skill-name/
├── SKILL.md          # Required: the skill definition
├── references/       # Optional: L3 deep-dive resources
│   ├── guide.md
│   └── patterns.md
├── assets/           # Optional: static files
└── scripts/          # Optional: executable scripts
```

## Naming Conventions

- Skill names: `kebab-case` (e.g., `deploy-to-k8s`, `api-security-review`)
- Reference files: `kebab-case.md`
- Tags: lowercase, single words or hyphenated

## Instruction Body Best Practices

1. Use numbered steps for sequential workflows
2. Reference specific tools the skill expects to have access to
3. Define clear input/output formats
4. Specify error handling behavior
5. Include scope boundaries (what the skill does and does NOT do)
"""

_EXAMPLE_CONTENT = """\
# Example Skill: code-review

Below is a complete, valid skill specification for reference:

```markdown
---
name: code-review
description: Reviews code changes for quality, security, and adherence to team coding standards. Provides actionable feedback with severity ratings.
---

# Code Review Instructions

When asked to review code, follow this methodology:

## Step 1: Understand the Context
Ask for or identify:
- The programming language
- The purpose of the change (bug fix, feature, refactor)
- Any team-specific coding standards

## Step 2: Static Analysis
Check for:
- Syntax errors and typos
- Unused variables and imports
- Overly complex functions (cyclomatic complexity)
- Missing error handling

## Step 3: Security Review
Check for:
- SQL injection vulnerabilities
- Unvalidated user input
- Hardcoded secrets or credentials
- Insecure dependencies

## Step 4: Quality Assessment
Evaluate:
- Code readability and naming conventions
- Test coverage implications
- Documentation completeness
- Adherence to DRY and SOLID principles

## Step 5: Provide Feedback
For each finding:
- Severity: critical / major / minor / suggestion
- Location: file and line number
- Description: what the issue is
- Recommendation: how to fix it

Return findings as structured JSON:
```json
[{"severity": "major", "file": "app.py", "line": 42, "issue": "...", "fix": "..."}]
```
```
"""

_OCI_GUIDE_CONTENT = """\
# OCI Publishing Guide

## Overview

Skills are published to an OCI (Open Container Initiative) registry for
versioning and distribution. The registry stores each skill as an OCI artifact
with metadata annotations.

## Publishing Steps

1. **Validate**: Ensure the SKILL.md frontmatter is valid and the name is kebab-case
2. **Package**: Bundle the SKILL.md, references/, assets/, and scripts/ into a tarball
3. **Tag**: Use semantic versioning: `{registry}/{namespace}/skills/{skill-name}:{version}`
4. **Push**: Upload to the OCI registry using the configured endpoint
5. **Annotate**: Add OCI annotations for discoverability:
   - `org.agentskills.name`: Skill name
   - `org.agentskills.description`: Skill description
   - `org.agentskills.author`: Author identifier
   - `org.agentskills.version`: Semantic version

## Version Strategy

- `0.1.0`: Initial draft, not production-ready
- `1.0.0`: First stable release
- Patch: Bug fixes to instructions or references
- Minor: New references or expanded instructions
- Major: Breaking changes to skill behavior or output format

## Registry URL Format

```
{oci_registry_url}/{oci_namespace}/skills/{skill-name}:{version}
```
"""

# Pattern 4: Inline meta skill with embedded L3 resources
_skill_creator = models.Skill(
    frontmatter=models.Frontmatter(
        name="skill-creator",
        description=(
            "Creates new ADK-compatible skill definitions from requirements. "
            "Generates complete SKILL.md files following the agentskills.io "
            "specification. Supports multi-turn refinement and OCI publishing."
        ),
    ),
    instructions=(
        "When asked to create a new skill, generate a complete SKILL.md file.\n\n"
        "Read `references/skill-spec.md` for the format specification.\n"
        "Read `references/skill-example.md` for a working example.\n\n"
        "Follow these rules:\n"
        "1. Name must be kebab-case, max 64 characters\n"
        "2. Description must be under 1024 characters\n"
        "3. Instructions should be clear, step-by-step\n"
        "4. Reference files in references/ for detailed domain knowledge\n"
        "5. Keep SKILL.md under 500 lines, put details in references/\n"
        "6. Output the complete file content the user can save directly\n\n"
        "Workflow:\n"
        "1. Gather requirements from the user (purpose, tools, domain)\n"
        "2. Generate the specification\n"
        "3. Present for review, support multi-turn refinement\n"
        "4. On approval, validate via validate_skill_yaml\n"
        "5. Read `references/oci-publish-guide.md` then publish via publish_skill_to_oci\n"
    ),
    resources=models.Resources(
        references={
            "skill-spec.md": _SPEC_CONTENT,
            "skill-example.md": _EXAMPLE_CONTENT,
            "oci-publish-guide.md": _OCI_GUIDE_CONTENT,
        }
    ),
)

_skill_toolset = SkillToolset(skills=[_skill_creator])

root_agent = Agent(
    model=get_agent_model(),
    name=_cfg["name"],
    description=_cfg["description"],
    instruction=(
        "You are a Skill Builder agent for the Skills Marketplace.\n\n"
        "Your job is to generate new skill specifications from user descriptions "
        "following the agentskills.io specification. You are a meta-skill: "
        "a skill whose purpose is to create other skills.\n\n"
        "1. Load the skill-creator skill for your authoring methodology\n"
        "2. Use load_skill_resource to read the spec and example references\n"
        "3. Generate a complete specification (name, description, instructions)\n"
        "4. Present for review and support multi-turn refinement\n"
        "5. On approval, validate via validate_skill_yaml then publish via "
        "publish_skill_to_oci\n\n"
        "Always output complete, valid SKILL.md content the user can save directly."
    ),
    tools=[
        _skill_toolset,
        validate_skill_yaml,
        publish_skill_to_oci,
    ],
)
