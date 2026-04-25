---
name: skill-advisor
description: Recommends complementary skills from the catalog based on user requirements, current cart contents, semantic similarity, and knowledge graph relationships. Returns ranked suggestions with explanations.
---

# Skill Advisor Instructions

When asked to recommend skills, follow this methodology:

## Step 1: Understand the Request
Parse the user's plain-English description of what they need. Identify key capabilities, domains, and tools mentioned.

## Step 2: Check the Cart
Read the current cart contents from session state key `_cart_skills`. Note which skills are already selected to avoid duplicate recommendations.

## Step 3: Search Semantically
Use `semantic_search_skills` with the user's description to find skills that match by meaning, not just keywords. Request the top results based on the configured `search_top_k`.

## Step 4: Explore Relationships
Use `query_skill_graph` to find:
- Skills connected via SIMILAR_TO edges to the semantic matches
- Skills connected via DEPENDS_ON edges (dependencies the user might need)
- Skills in the same BELONGS_TO domain

## Step 5: Rank and Filter
Read `references/recommendation-strategy.md` for the scoring methodology using `load_skill_resource`.
- Remove skills already in the cart
- Score each candidate using the strategy
- Sort by descending score

## Step 6: Explain and Return
For each recommendation, explain WHY it was selected referencing:
- The user's original requirement
- Specific graph relationships (e.g., "depends on X which is in your cart")
- Semantic similarity to the query

Return results as a JSON array:
```json
[{"skill_name": "...", "score": 0.92, "reason": "...", "category": "..."}]
```
