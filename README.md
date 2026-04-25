# Skills Marketplace ADK Agents

Five ADK agents powering the Skills Marketplace. Each agent runs as an independent **A2A-compliant microservice** managed by [Kagenti](https://github.com/kagenti/kagenti). Built with [ADK SkillToolset](https://developers.googleblog.com/developers-guide-to-building-adk-agents-with-skills/) progressive disclosure across all four skill patterns.

## Architecture

```
smp-agents/
├── config.yaml                        # All non-secret configuration
├── .env.example                       # Secret templates (env vars)
├── shared/                            # Shared utilities (Python package)
│   ├── model_config.py                # YAML config loader + LiteLlm factory
│   ├── neo4j_tools.py                 # Graph query FunctionTools
│   ├── oci_tools.py                   # OCI registry FunctionTools
│   └── semantic_search_tools.py       # Embedding search FunctionTools
│
├── agents/
│   ├── skill_advisor/                 # Patterns 1 + 2
│   │   ├── agent.py                   # Inline output-format + file-based methodology
│   │   ├── server.py                  # A2A entrypoint (to_a2a)
│   │   ├── Dockerfile                 # Kagenti build
│   │   └── skills/skill-advisor/      # L2 SKILL.md + L3 references/
│   │
│   ├── bundle_validator/              # Pattern 2
│   │   ├── agent.py                   # File-based validation rules
│   │   ├── server.py
│   │   ├── Dockerfile
│   │   └── skills/bundle-validator/   # L2 + L3 validation-rules.md, dependency-patterns.md
│   │
│   ├── kg_qa/                         # Pattern 2
│   │   ├── agent.py                   # File-based Cypher query methodology
│   │   ├── server.py
│   │   ├── Dockerfile
│   │   └── skills/kg-qa/              # L2 + L3 graph-schema.md, cypher-patterns.md
│   │
│   ├── playground/                    # Patterns 2 + 3
│   │   ├── agent.py                   # File-based testing + external skill from session state
│   │   ├── server.py
│   │   ├── Dockerfile
│   │   └── skills/playground-runtime/ # L2 + L3 testing-guide.md
│   │
│   └── skill_builder/                 # Pattern 4 (Meta Skill Factory)
│       ├── agent.py                   # Inline models.Skill + models.Resources
│       ├── server.py                  # (no skills/ dir -- spec embedded in code)
│       └── Dockerfile
```

## ADK Skill Patterns Used

| Agent | Pattern(s) | Progressive Disclosure |
|-------|-----------|----------------------|
| Skill Advisor | 1 (inline output format) + 2 (file-based methodology) | L1: 2 skill names. L2: recommendation steps. L3: scoring weights |
| Bundle Validator | 2 (file-based) | L1: 1 skill name. L2: validation checklist. L3: rules + anti-patterns |
| KG Q&A | 2 (file-based) | L1: 1 skill name. L2: query methodology. L3: graph schema + Cypher templates |
| Playground | 2 (file-based) + 3 (external via session state) | L1: 1 skill name. L2: testing guide. External spec from marketplace UI |
| Skill Builder | 4 (meta skill factory) | L1: 1 skill name. L2: creation rules. L3: agentskills.io spec + example (embedded) |

## A2A Protocol

Each agent exposes the [A2A](https://google.github.io/A2A) protocol via ADK's `to_a2a()`:

- `GET /.well-known/agent-card.json` -- Agent card for Kagenti discovery
- `POST /` -- A2A JSON-RPC (message/send, message/stream, tasks)

Agent cards are auto-generated from the ADK Agent definition by `AgentCardBuilder`.

## Quick Start (Local)

```bash
# Clone and install
git clone <repo-url> && cd smp-agents
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # add NEO4J_PASSWORD

# Run any agent independently
PYTHONPATH=. uvicorn agents.skill_advisor.server:app --host 0.0.0.0 --port 8001
PYTHONPATH=. uvicorn agents.bundle_validator.server:app --host 0.0.0.0 --port 8002
PYTHONPATH=. uvicorn agents.kg_qa.server:app --host 0.0.0.0 --port 8003
PYTHONPATH=. uvicorn agents.playground.server:app --host 0.0.0.0 --port 8004
PYTHONPATH=. uvicorn agents.skill_builder.server:app --host 0.0.0.0 --port 8005

# Verify agent card
curl http://localhost:8005/.well-known/agent-card.json | jq .
```

## Kagenti Deployment

Each agent has its own Dockerfile. To deploy via Kagenti UI:

1. Push this repo to GitHub
2. In Kagenti UI: **Import New Agent** > **Build from Source**
3. Set repository URL, subfolder (e.g., `agents/skill_advisor`), protocol = **A2A**
4. Kagenti builds the image via Shipwright, creates Deployment + Service + HTTPRoute
5. Agent appears in the **Agent Catalog**, discoverable via `/.well-known/agent-card.json`

## Configuration

All non-secret config lives in `config.yaml` (model endpoints, Neo4j, OCI, per-agent ports).
Secrets use `${VAR_NAME}` syntax resolved from environment variables.

```bash
cp .env.example .env
# Edit .env with real NEO4J_PASSWORD
```
