# Validation Rules

## Severity Definitions

| Severity | Meaning | Action Required |
|----------|---------|-----------------|
| error | Bundle will not function correctly | Must fix before deploying |
| warning | Bundle may have issues or inefficiencies | Should review before deploying |
| info | Observation or suggestion for improvement | Optional to address |

## Rules

### R1: Missing Dependency (error)
A skill in the bundle has a DEPENDS_ON relationship to a skill NOT in the bundle.
- Check all transitive dependencies, not just direct ones
- Report each missing dependency individually

### R2: Redundant Skills (warning)
Two or more skills in the bundle have ALTERNATIVE_TO relationships or SIMILAR_TO score > 0.85.
- Check for ALTERNATIVE_TO edges first (explicit redundancy)
- Check SIMILAR_TO score as a fallback
- Report which skills overlap and suggest keeping only one
- Consider whether the overlap is partial (different tools) or full

### R3: Missing Tool Provider (warning)
A skill declares USES_TOOL but no skill in the bundle provides that tool.
- Only flag tools that are not built-in platform tools

### R6: Missing Complement (info)
A skill has strong COMPLEMENTS edges to skills not in the bundle.
- Suggest adding complementary skills that improve the workflow

### R4: Single-Domain Bundle (info)
All skills belong to the same domain. This is not an error but may indicate the bundle could benefit from cross-domain skills.

### R5: Large Bundle (info)
Bundles with more than 20 skills may be difficult to manage. Suggest splitting into focused sub-bundles.
