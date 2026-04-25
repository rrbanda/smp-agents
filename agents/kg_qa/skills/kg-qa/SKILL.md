---
name: kg-qa
description: Answers natural-language questions about the skill ecosystem by translating them into Cypher queries against the Neo4j knowledge graph. Returns grounded answers with node references for graph highlighting.
compatibility: Requires Neo4j graph database with Cypher query support.
metadata:
  author: skills-marketplace
  version: "1.0"
  tags: knowledge-graph, cypher, question-answering
---

# Knowledge Graph Q&A Instructions

When asked a question about skills, tools, domains, or agents, follow this methodology:

## Step 1: Understand the Schema
Use `load_skill_resource` to read `references/graph-schema.md`. Understand the available node types, relationship types, and properties before writing any query.

## Step 2: Identify Query Intent
Classify the user's question into one of these categories:
- **Count**: "How many skills are in domain X?"
- **List**: "Which skills depend on tool Y?"
- **Relationship**: "What is the relationship between skill A and skill B?"
- **Path**: "How is skill A connected to skill B?"
- **Similarity**: "What skills are similar to X?"

## Step 3: Write the Cypher Query
Use `load_skill_resource` to read `references/cypher-patterns.md` for reusable query templates. Adapt the template to the user's specific question.

## Step 4: Execute and Validate
Run the query via `query_skill_graph`. If the query returns no results, consider:
- Checking for typos in skill/tool names
- Broadening the query (e.g., partial name match)
- Trying an alternative query pattern

## Step 5: Compose the Answer
- State the answer directly, citing actual data
- Never hallucinate counts, names, or relationships
- If the data doesn't contain the answer, say so explicitly

## Step 6: Return Structured Output
```json
{"answer": "...", "highlighted_nodes": ["node-a", "node-b"], "cypher_used": "MATCH..."}
```

The `highlighted_nodes` array lets the UI highlight relevant nodes on the graph visualization.
