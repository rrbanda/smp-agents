---
name: bundle-validator
description: Validates a curated skill bundle for missing dependencies, redundant skills, capability gaps, and tool coverage. Returns categorized findings as error, warning, or info.
---

# Bundle Validator Instructions

When asked to validate a bundle, follow this checklist:

## Step 1: Load the Bundle
Read the bundle skill list from session state key `_bundle_skills`. Each entry contains the skill name and metadata.

## Step 2: Load Validation Rules
Use `load_skill_resource` to read `references/validation-rules.md` for severity definitions and rule details.

## Step 3: Check Dependencies
For each skill in the bundle:
1. Use `get_skill_dependencies` to retrieve its transitive dependency tree
2. Check if every dependency is present in the bundle
3. Missing dependencies are **error** severity

## Step 4: Check Redundancy
For each pair of skills in the bundle:
1. Use `get_skill_similarity` to check SIMILAR_TO scores
2. Pairs with similarity > 0.85 are **warning** severity (potentially redundant)

## Step 5: Check Tool Coverage
Use `query_skill_graph` to find all USES_TOOL relationships for bundle skills. Flag any tools that are required but not provided by any skill in the bundle as **warning**.

## Step 6: Check Common Patterns
Use `load_skill_resource` to read `references/dependency-patterns.md` for known anti-patterns. Check the bundle against each pattern.

## Step 7: Return Findings
Return all findings as a JSON array:
```json
[{"severity": "error|warning|info", "title": "...", "detail": "...", "affected_skills": ["..."]}]
```
