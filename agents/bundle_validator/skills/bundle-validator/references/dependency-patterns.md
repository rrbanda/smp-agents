# Common Dependency Anti-Patterns

## Pattern: Deploy Without Build
**Symptom**: Bundle contains deployment skills (e.g., deploy-to-kubernetes, deploy-to-cloud-run) but lacks build/packaging skills (e.g., container-build, artifact-package).
**Rule**: If any skill name contains "deploy", check for skills containing "build" or "package".

## Pattern: Test Without Setup
**Symptom**: Bundle contains testing skills but lacks environment setup or fixture skills.
**Rule**: If any skill name contains "test" or "validate", check for skills containing "setup" or "configure".

## Pattern: Monitor Without Alert
**Symptom**: Bundle contains monitoring/observability skills but lacks alerting or notification skills.
**Rule**: If any skill name contains "monitor" or "observe", check for skills containing "alert" or "notify".

## Pattern: API Without Auth
**Symptom**: Bundle contains API integration skills but lacks authentication or credential management skills.
**Rule**: If any skill uses tools related to API calls, check for skills related to auth, credentials, or tokens.

## Pattern: Data Without Validation
**Symptom**: Bundle contains data processing skills but lacks input validation or schema checking skills.
**Rule**: If any skill name contains "process", "transform", or "etl", check for skills containing "validate" or "schema".
