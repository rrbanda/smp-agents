# Neo4j Skills Marketplace Graph Schema

Authoritative reference for the knowledge graph backing the Skills Marketplace.
Grounded in the [agentskills.io specification](https://agentskills.io/specification.md).

## Node Types

| Label | Description | Key Property | Other Properties |
|-------|-------------|--------------|------------------|
| Skill | An agent skill following agentskills.io spec | `name` or `id` (see below) | description, plugin, domain, category, version, author, license, tags, body/prompt, ociReference, complexity, technologies[], patterns[], embedding |
| Domain | Functional area (security, devops, api, etc.) | `name` | description |
| Tag | Label from skill frontmatter | `name` | - |
| Tool | Capability/API a skill can invoke | `name` | description |
| SkillBundle | Curated collection of skills | `name` | description, author |
| Agent | Deployed agent instance | `name` | description, status |
| Community | Auto-detected cluster (Louvain) | `communityId` | name, description, keyTechnologies[], coherenceScore, memberCount |

### Skill Key Convention

Two populations coexist in the graph:
- **Registry skills**: keyed by `id` (e.g., `docs-code-reviewer`), `name` is NULL
- **OCI-synced skills**: keyed by `name` (e.g., `active-directory-attacks`), `id` is NULL

Always match with: `WHERE s.name = $identifier OR s.id = $identifier`

## Relationship Types

### Deterministic (metadata-derived, no confidence score)

| Relationship | From | To | Description |
|-------------|------|-----|-------------|
| TAGGED_WITH | Skill | Tag | Skill has this tag in frontmatter |
| BELONGS_TO | Skill | Domain | Skill is categorized in this domain |
| USES_TOOL | Skill | Tool | Skill invokes this tool/API |
| SAME_PLUGIN | Skill | Skill | Both skills come from the same plugin/package |
| SAME_DOMAIN | Skill | Skill | Both skills share a domain classification |
| CROSS_LANGUAGE | Skill | Skill | Equivalent skill in a different programming language |
| USES_AUTH | Skill | - | Skill requires an auth mechanism |
| INCLUDES | SkillBundle | Skill | Bundle contains this skill |
| EXPOSES | Agent | Skill | Agent implements/exposes this skill |
| MEMBER_OF | Skill | Community | Skill belongs to this Louvain community |

### Semantic (LLM-classified, with confidence scores)

Each carries: `confidence` (0.0-1.0), `description` (why), `direction` (A_TO_B / B_TO_A / BIDIRECTIONAL)

| Relationship | Direction | Description |
|-------------|-----------|-------------|
| DEPENDS_ON | Directional | Skill A functionally requires Skill B |
| COMPLEMENTS | Directional | Skills work well together in a workflow |
| ALTERNATIVE_TO | Bidirectional | Interchangeable skills solving the same problem |
| EXTENDS | Directional | Skill A specializes/deepens Skill B |
| PRECEDES | Directional | Skill A should run before Skill B in a pipeline |

### Embedding-Derived

| Relationship | Direction | Properties | Description |
|-------------|-----------|------------|-------------|
| SIMILAR_TO | Bidirectional | `score` (float) | Cosine similarity above threshold from vector embeddings |

## Vector Index

- Name: `skill_embedding_idx`
- Property: `Skill.embedding`
- Dimensions: 768 (nomic-embed-text-v1-5)
- Similarity: COSINE
