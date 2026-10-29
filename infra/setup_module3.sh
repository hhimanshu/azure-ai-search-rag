#!/usr/bin/env bash
# Adds what Module 3 needs on top of infra/deploy.sh: the gpt-5-mini chat
# deployment, a Microsoft Foundry project, the project's connection to your
# Search service, and the roles that let the Foundry project's agent query the index
# without a key. It then adds the two settings to .env.
#
# Safe to run again: it skips anything that already exists.
#
# Usage: ./infra/setup_module3.sh   (after ./infra/deploy.sh and Module 2)
# Requires: az CLI, logged in, and the .env that deploy.sh wrote.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
[[ -e "$ENV_FILE" ]] || { echo "STOP: $ENV_FILE not found. Run ./infra/deploy.sh first." >&2; exit 1; }

env_value() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }

RESOURCE_GROUP="$(env_value AZURE_RESOURCE_GROUP)"
SUBSCRIPTION_ID="$(env_value AZURE_SUBSCRIPTION_ID)"
SEARCH_ENDPOINT="$(env_value AZURE_SEARCH_ENDPOINT)"
SEARCH_NAME="${SEARCH_ENDPOINT#https://}"; SEARCH_NAME="${SEARCH_NAME%%.*}"
AISERVICES_ENDPOINT="$(env_value AZURE_AI_SERVICES_ENDPOINT)"
AISERVICES_NAME="${AISERVICES_ENDPOINT#https://}"; AISERVICES_NAME="${AISERVICES_NAME%%.*}"
LOCATION="$(env_value AZURE_LOCATION)"; LOCATION="${LOCATION:-eastus}"
CHAT_DEPLOYMENT="${AZURE_OPENAI_CHAT_DEPLOYMENT:-gpt-5-mini}"
PROJECT_NAME="${AZURE_AI_PROJECT_NAME:-rag-course-project}"
CONNECTION_NAME="rag-search"  # must match SEARCH_CONNECTION in module-3/helpers.py

AISERVICES_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$AISERVICES_NAME"
SEARCH_ID="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_NAME"

echo "== Chat deployment: $CHAT_DEPLOYMENT =="
if [[ -z "$(az cognitiveservices account deployment list -g "$RESOURCE_GROUP" -n "$AISERVICES_NAME" --query "[?name=='$CHAT_DEPLOYMENT'].name" -o tsv)" ]]; then
  az cognitiveservices account deployment create \
    --name "$AISERVICES_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --deployment-name "$CHAT_DEPLOYMENT" \
    --model-name "$CHAT_DEPLOYMENT" \
    --model-version "2025-08-07" \
    --model-format OpenAI \
    --sku-capacity 200 \
    --sku-name GlobalStandard \
    --output none
else
  echo "already deployed"
fi

echo "== Foundry project: $PROJECT_NAME =="
if ! az cognitiveservices account project show -g "$RESOURCE_GROUP" -n "$AISERVICES_NAME" --project-name "$PROJECT_NAME" --output none 2>/dev/null; then
  az cognitiveservices account project create \
    --name "$AISERVICES_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --project-name "$PROJECT_NAME" \
    --location "$LOCATION" \
    --assign-identity \
    --output none
else
  echo "already exists"
fi

echo "== Project connection to Search: $CONNECTION_NAME (Entra ID, no key) =="
CONNECTION_BODY="$(mktemp)"
cat > "$CONNECTION_BODY" <<EOF
{"properties":{"category":"CognitiveSearch","target":"$SEARCH_ENDPOINT","authType":"AAD","isSharedToAll":true,"metadata":{"ApiType":"Azure","ResourceId":"$SEARCH_ID","location":"$LOCATION"}}}
EOF
az rest --method put \
  --url "https://management.azure.com$AISERVICES_ID/projects/$PROJECT_NAME/connections/$CONNECTION_NAME?api-version=2025-06-01" \
  --body "@$CONNECTION_BODY" --output none
rm -f "$CONNECTION_BODY"

echo "== Roles: the Foundry project's identity reads the index, you create agents =="
PROJECT_PRINCIPAL_ID="$(az cognitiveservices account project show -g "$RESOURCE_GROUP" -n "$AISERVICES_NAME" --project-name "$PROJECT_NAME" --query identity.principalId -o tsv)"
# Both roles are needed, scoped to this one Search service. Checked on 2026-10-29: with
# Search Index Data Reader alone, the agent call fails with "Access denied ... managed
# identity access to the search service". Microsoft Learn, "Connect an Azure AI Search
# index to Foundry agents", lists these two roles for keyless access.
for ROLE in "Search Index Data Contributor" "Search Service Contributor"; do
  az role assignment create --assignee-object-id "$PROJECT_PRINCIPAL_ID" --assignee-principal-type ServicePrincipal \
    --role "$ROLE" --scope "$SEARCH_ID" --output none
done
USER_ID="$(az ad signed-in-user show --query id -o tsv)"
az role assignment create --assignee "$USER_ID" --role "Azure AI Developer" --scope "$AISERVICES_ID" --output none

echo "== .env =="
PROJECT_ENDPOINT="https://$AISERVICES_NAME.services.ai.azure.com/api/projects/$PROJECT_NAME"
for LINE in "AZURE_OPENAI_CHAT_DEPLOYMENT=$CHAT_DEPLOYMENT" "AZURE_AI_PROJECT_ENDPOINT=$PROJECT_ENDPOINT"; do
  KEY="${LINE%%=*}"
  if [[ -z "$(env_value "$KEY")" ]]; then
    printf '%s\n' "$LINE" >> "$ENV_FILE"
    echo "added $KEY"
  else
    echo "$KEY already set"
  fi
done

echo
echo "Done. Role assignments can take a few minutes to take effect."
