# Recommendation Strategy

## Scoring Weights

Each candidate skill receives a composite score from 0.0 to 1.0:

| Signal | Weight | Description |
|--------|--------|-------------|
| Semantic similarity | 0.40 | Cosine similarity between query embedding and skill embedding |
| Graph proximity | 0.25 | Shortest path distance to any skill already in the cart |
| Dependency relevance | 0.20 | Whether the candidate is a transitive dependency of a cart skill |
| Domain coverage | 0.15 | Whether the candidate fills an unrepresented domain |

## Ranking Rules

1. Skills that are direct DEPENDS_ON targets of cart skills get a 0.15 bonus
2. Skills with COMPLEMENTS edges to cart skills get a 0.10 bonus
3. Skills with ALTERNATIVE_TO edges to a cart skill are flagged as "alternative" but still included with a note
4. Skills with SIMILAR_TO score > 0.85 to a cart skill are flagged as "potentially redundant"
5. Maximum 10 recommendations per request
6. Minimum score threshold: 0.3 (below this, do not recommend)

## Output Format

Each recommendation must include:
- `skill_name`: The skill's identifier
- `score`: Composite score rounded to 2 decimal places
- `reason`: One sentence explaining the recommendation
- `category`: The skill's domain/category
- `relationship`: Graph edge type connecting to the cart (DEPENDS_ON, COMPLEMENTS, ALTERNATIVE_TO, EXTENDS, SIMILAR_TO, SAME_PLUGIN)
