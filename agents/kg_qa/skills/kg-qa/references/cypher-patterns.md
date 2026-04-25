# Reusable Cypher Query Patterns

All patterns use `coalesce(s.name, s.id)` to handle both key conventions.

## Skill Lookup

```cypher
MATCH (s:Skill) WHERE s.name = $identifier OR s.id = $identifier
RETURN s{.*} AS skill
```

## Count skills in a domain

```cypher
MATCH (s:Skill)-[:BELONGS_TO]->(d:Domain {name: $domain_name})
RETURN count(s) AS skill_count, d.name AS domain
```

## List skills by domain (via BELONGS_TO or domain property)

```cypher
MATCH (s:Skill)
WHERE s.domain = $domain_name
   OR EXISTS { (s)-[:BELONGS_TO]->(:Domain {name: $domain_name}) }
RETURN coalesce(s.name, s.id) AS skill, s.description AS description
ORDER BY skill
```

## Skills by plugin

```cypher
MATCH (s:Skill {plugin: $plugin_name})
RETURN coalesce(s.name, s.id) AS skill, s.description AS description
ORDER BY skill
```

## List all domains with skill counts

```cypher
MATCH (s:Skill)
WHERE s.domain IS NOT NULL AND s.domain <> ''
RETURN s.domain AS domain, count(s) AS skill_count
ORDER BY skill_count DESC
```

## Find skills that use a specific tool

```cypher
MATCH (s:Skill)-[:USES_TOOL]->(t:Tool {name: $tool_name})
RETURN coalesce(s.name, s.id) AS skill, s.description AS description
```

## Find skills by tag

```cypher
MATCH (s:Skill)-[:TAGGED_WITH]->(t:Tag {name: $tag_name})
RETURN coalesce(s.name, s.id) AS skill, s.description AS description
```

## Dependencies (DEPENDS_ON chain)

```cypher
MATCH (s:Skill) WHERE s.name = $identifier OR s.id = $identifier
MATCH path = (s)-[:DEPENDS_ON*1..5]->(dep:Skill)
RETURN coalesce(dep.name, dep.id) AS dependency,
       dep.description AS description,
       length(path) AS depth
ORDER BY depth
```

## Complementary skills

```cypher
MATCH (s:Skill) WHERE s.name = $identifier OR s.id = $identifier
MATCH (s)-[r:COMPLEMENTS]-(other:Skill)
WHERE coalesce(r.confidence, 1.0) >= 0.6
RETURN coalesce(other.name, other.id) AS skill,
       other.description AS description,
       r.confidence AS confidence,
       r.description AS reason
ORDER BY r.confidence DESC
```

## Find alternatives

```cypher
MATCH (s:Skill) WHERE s.name = $identifier OR s.id = $identifier
MATCH (s)-[r:ALTERNATIVE_TO]-(alt:Skill)
RETURN coalesce(alt.name, alt.id) AS alternative,
       alt.description AS description,
       r.confidence AS confidence
ORDER BY r.confidence DESC
```

## Skills in same plugin (siblings)

```cypher
MATCH (s:Skill) WHERE s.name = $identifier OR s.id = $identifier
MATCH (s)-[:SAME_PLUGIN]-(sibling:Skill)
RETURN coalesce(sibling.name, sibling.id) AS skill,
       sibling.description AS description
```

## Cross-language equivalents

```cypher
MATCH (s:Skill) WHERE s.name = $identifier OR s.id = $identifier
MATCH (s)-[:CROSS_LANGUAGE]-(equiv:Skill)
RETURN coalesce(equiv.name, equiv.id) AS skill,
       equiv.plugin AS plugin, equiv.lang AS language
```

## Semantic vector search (requires populated embeddings)

```cypher
CALL db.index.vector.queryNodes('skill_embedding_idx', $top_k, $embedding)
YIELD node, score
RETURN coalesce(node.name, node.id) AS skill,
       node.description AS description,
       node.plugin AS plugin,
       score
ORDER BY score DESC
```

## Vector search with graph expansion

```cypher
CALL db.index.vector.queryNodes('skill_embedding_idx', $top_k, $embedding)
YIELD node, score
WITH node, score
OPTIONAL MATCH (node)-[:COMPLEMENTS|DEPENDS_ON|SAME_PLUGIN]-(neighbor:Skill)
WITH node, score, collect(DISTINCT neighbor) AS neighbors
UNWIND ([node] + neighbors) AS skill
WITH DISTINCT skill, max(score) AS best_score
RETURN coalesce(skill.name, skill.id) AS skill_name,
       skill.description AS description,
       best_score AS score
ORDER BY score DESC LIMIT $limit
```

## Find skills in a bundle

```cypher
MATCH (b:SkillBundle {name: $bundle_name})-[:INCLUDES]->(s:Skill)
RETURN coalesce(s.name, s.id) AS skill, s.domain AS domain
```

## Bundle dependency gap analysis

```cypher
MATCH (b:SkillBundle {name: $bundle_name})-[:INCLUDES]->(s:Skill)
OPTIONAL MATCH (s)-[:DEPENDS_ON]->(dep:Skill)
WHERE NOT (b)-[:INCLUDES]->(dep)
RETURN coalesce(s.name, s.id) AS skill,
       coalesce(dep.name, dep.id) AS missing_dependency
```

## Bundle redundancy check (alternatives in same bundle)

```cypher
MATCH (b:SkillBundle {name: $bundle_name})-[:INCLUDES]->(s1:Skill)
MATCH (b)-[:INCLUDES]->(s2:Skill)
WHERE s1 <> s2 AND (s1)-[:ALTERNATIVE_TO]-(s2) AND id(s1) < id(s2)
RETURN coalesce(s1.name, s1.id) AS skill_a,
       coalesce(s2.name, s2.id) AS skill_b,
       'ALTERNATIVE_TO' AS issue
```

## Full neighborhood exploration

```cypher
MATCH (s:Skill) WHERE s.name = $identifier OR s.id = $identifier
MATCH (s)-[r]-(neighbor)
RETURN coalesce(neighbor.name, neighbor.id) AS neighbor,
       labels(neighbor)[0] AS label,
       type(r) AS relationship,
       CASE WHEN startNode(r) = s THEN 'outgoing' ELSE 'incoming' END AS direction,
       r.confidence AS confidence
ORDER BY type(r)
```

## Graph statistics

```cypher
MATCH (s:Skill) WITH count(s) AS total_skills
MATCH ()-[r]->() WITH total_skills, count(r) AS total_edges
RETURN total_skills, total_edges
```
