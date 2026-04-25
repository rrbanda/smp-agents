#!/usr/bin/env bash
set -euo pipefail

# Deploy all 5 SMP agents to Kagenti on OpenShift.
# Prereqs: oc login, git repo pushed to GitHub

KEYCLOAK_URL="${KEYCLOAK_URL:-https://keycloak-keycloak.apps.ocp.v7hjl.sandbox2288.opentlc.com}"
KAGENTI_API="${KAGENTI_API:-https://kagenti-api-kagenti-system.apps.ocp.v7hjl.sandbox2288.opentlc.com}"
KEYCLOAK_USER="${KEYCLOAK_USER:-temp-admin}"
KEYCLOAK_PASSWORD="${KEYCLOAK_PASSWORD:-4454edeff4ee4470bdf29deb612e30c1}"
NAMESPACE="${NAMESPACE:-smp-agents}"
GIT_REPO="${GIT_REPO:-https://github.com/rrbanda/smp-agents.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
BUILD_STRATEGY="${BUILD_STRATEGY:-buildah}"

echo "=== Authenticating to Keycloak ==="
TOKEN=$(curl -s -X POST \
  "${KEYCLOAK_URL}/realms/kagenti/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=kagenti" \
  -d "username=${KEYCLOAK_USER}" \
  -d "password=${KEYCLOAK_PASSWORD}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "  Token obtained"

echo "=== Creating namespace: ${NAMESPACE} ==="
oc new-project "${NAMESPACE}" --display-name="SMP Agents" 2>/dev/null || echo "  Namespace already exists"

declare -A AGENTS
AGENTS[skill-advisor]="Dockerfile.skill-advisor"
AGENTS[bundle-validator]="Dockerfile.bundle-validator"
AGENTS[kg-qa]="Dockerfile.kg-qa"
AGENTS[playground]="Dockerfile.playground"
AGENTS[skill-builder]="Dockerfile.skill-builder"

for AGENT_NAME in "${!AGENTS[@]}"; do
    DOCKERFILE="${AGENTS[$AGENT_NAME]}"
    echo ""
    echo "=== Deploying: ${AGENT_NAME} ==="

    PAYLOAD=$(cat <<EOJSON
{
    "name": "${AGENT_NAME}",
    "namespace": "${NAMESPACE}",
    "source": {
        "git": {
            "url": "${GIT_REPO}",
            "revision": "${GIT_BRANCH}"
        }
    },
    "build": {
        "strategy": "${BUILD_STRATEGY}",
        "dockerfile": "${DOCKERFILE}"
    },
    "env": [
        {"name": "LLAMASTACK_API_KEY", "value": "not-needed"},
        {"name": "NEO4J_PASSWORD", "value": "skillsmarketplace"}
    ],
    "port": 8000,
    "protocol": "a2a"
}
EOJSON
)

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
        "${KAGENTI_API}/api/v1/agents" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d "${PAYLOAD}")

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
        echo "  SUCCESS (${HTTP_CODE})"
    else
        echo "  FAILED (${HTTP_CODE}): ${BODY}"
    fi
done

echo ""
echo "=== Verifying agent cards ==="
sleep 5

for AGENT_NAME in "${!AGENTS[@]}"; do
    AGENT_URL="https://${AGENT_NAME}-${NAMESPACE}.apps.ocp.v7hjl.sandbox2288.opentlc.com"
    echo -n "  ${AGENT_NAME}: "
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${AGENT_URL}/.well-known/agent-card.json" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "LIVE"
    else
        echo "NOT YET (${HTTP_CODE}) - may still be building"
    fi
done

echo ""
echo "Done. Check build status with: oc get builds -n ${NAMESPACE}"
