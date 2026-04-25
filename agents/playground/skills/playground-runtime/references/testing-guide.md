# Skill Testing Guide

## What to Test

When testing a skill in the playground, evaluate these aspects:

### 1. Instruction Clarity
- Are the skill's instructions clear enough for an LLM to follow?
- Are there ambiguous steps or missing context?
- Does the skill handle edge cases?

### 2. Scope Boundaries
- Does the skill clearly define what is in-scope vs out-of-scope?
- Does it gracefully decline requests outside its scope?

### 3. Output Format
- Does the skill produce output in the expected format?
- Is the output parseable by downstream systems?

### 4. Tool Usage
- Does the skill reference tools correctly?
- Are tool inputs well-specified?

### 5. Multi-Turn Coherence
- Does the skill maintain context across multiple turns?
- Does it handle follow-up questions logically?

## Testing Prompts

Try these generic prompts adapted to the active skill:
1. "What can you help me with?" (tests scope description)
2. "Do something that's clearly outside your scope" (tests boundary enforcement)
3. "Help me with [core use case]" (tests primary functionality)
4. "Follow up on the previous answer" (tests context retention)
5. "Give me the output in JSON/YAML/markdown" (tests output flexibility)
