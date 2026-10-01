#!/usr/bin/env bash
# Provisions everything Module 2 needs (Search + Storage + AI Services with
# the embedding deployment for integrated vectorization and OCR), assigns
# yourself the Entra ID roles the notebooks rely on instead of keys, and
# prints a ready-to-paste .env block.
#
# Not provisioned here: a Microsoft Foundry hub/project (Module 3 only,
# not an M2 dependency) and the chat model deployments (also M3). Add those
# when you reach 03_grounded_and_eval.ipynb.
#
# Usage: ./infra/deploy.sh
# Requires: az CLI, logged in (`az login`), Owner or Contributor + User
# Access Administrator on the target subscription (needed for the role
# assignments below).
set -euo pipefail

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rag-course-rg}"
LOCATION="${AZURE_LOCATION:-eastus}"  # eastus2 hit InsufficientResourcesAvailable for Search Basic during setup — eastus had capacity
SEARCH_NAME="${AZURE_SEARCH_NAME:-rag-course-search-$RANDOM}"
STORAGE_NAME="${AZURE_STORAGE_NAME:-ragcoursestor$RANDOM}"
CONTAINER_NAME="${AZURE_STORAGE_CONTAINER_NAME:-docs}"
AISERVICES_NAME="${AZURE_AISERVICES_NAME:-rag-course-aiservices-$RANDOM}"
EMBEDDING_DEPLOYMENT="${AZURE_OPENAI_EMBEDDING_DEPLOYMENT:-text-embedding-3-small}"
INDEX_NAME="${AZURE_SEARCH_INDEX_NAME:-state-driver-manuals}"

echo "== Resource group: $RESOURCE_GROUP ($LOCATION) =="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

echo "== Storage account + '$CONTAINER_NAME' container =="
az storage account create \
  --name "$STORAGE_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --output none

az storage container create \
  --name "$CONTAINER_NAME" \
  --account-name "$STORAGE_NAME" \
  --auth-mode login \
  --output none

echo "== Azure AI Search (Basic — required for the semantic ranker in M2 C3) =="
az search service create \
  --name "$SEARCH_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --sku Basic \
  --location "$LOCATION" \
  --output none

echo "== Azure AI Services (multi-service — OCR skill + OpenAI embedding deployment) =="
az cognitiveservices account create \
  --name "$AISERVICES_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --kind AIServices \
  --sku S0 \
  --location "$LOCATION" \
  --custom-domain "$AISERVICES_NAME" \
  --output none

echo "== Deploying $EMBEDDING_DEPLOYMENT (used by M2 C2 integrated vectorization) =="
az cognitiveservices account deployment create \
  --name "$AISERVICES_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --deployment-name "$EMBEDDING_DEPLOYMENT" \
  --model-name "$EMBEDDING_DEPLOYMENT" \
  --model-version "1" \
  --model-format OpenAI \
  --sku-capacity 30 \
  --sku-name Standard \
  --output none

echo "== Role assignments (so the notebooks run on Entra ID, not keys) =="
SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
USER_ID="$(az ad signed-in-user show --query id -o tsv)"
SEARCH_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_NAME"
AISERVICES_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$AISERVICES_NAME"

for ROLE in "Search Service Contributor" "Search Index Data Contributor"; do
  az role assignment create --assignee "$USER_ID" --role "$ROLE" --scope "$SEARCH_SCOPE" --output none
done
az role assignment create --assignee "$USER_ID" --role "Cognitive Services OpenAI User" --scope "$AISERVICES_SCOPE" --output none
# You (not just the search service identity) need write access too —
# 00_setup.ipynb uploads the PDFs to Blob under your own Entra ID identity.
STORAGE_SCOPE_FOR_USER="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_NAME"
az role assignment create --assignee "$USER_ID" --role "Storage Blob Data Contributor" --scope "$STORAGE_SCOPE_FOR_USER" --output none

# The indexer's blob data source connects with a managed identity, not the
# storage account key — give the *search service's* system identity access
# to the storage account, not your own.
az search service update --name "$SEARCH_NAME" --resource-group "$RESOURCE_GROUP" --identity-type SystemAssigned --output none
SEARCH_PRINCIPAL_ID="$(az search service show --name "$SEARCH_NAME" --resource-group "$RESOURCE_GROUP" --query identity.principalId -o tsv)"
STORAGE_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_NAME"
az role assignment create --assignee "$SEARCH_PRINCIPAL_ID" --role "Storage Blob Data Reader" --scope "$STORAGE_SCOPE" --output none
# Same identity needs to call the embedding deployment at query time
# (vectorizer) and index time (embedding skill) without a key.
az role assignment create --assignee "$SEARCH_PRINCIPAL_ID" --role "Cognitive Services OpenAI User" --scope "$AISERVICES_SCOPE" --output none

SEARCH_ENDPOINT="https://$SEARCH_NAME.search.windows.net"
STORAGE_ACCOUNT_URL="https://$STORAGE_NAME.blob.core.windows.net"
AISERVICES_ENDPOINT="$(az cognitiveservices account show --name "$AISERVICES_NAME" --resource-group "$RESOURCE_GROUP" --query properties.endpoint -o tsv)"
AISERVICES_KEY="$(az cognitiveservices account keys list --name "$AISERVICES_NAME" --resource-group "$RESOURCE_GROUP" --query key1 -o tsv)"

cat <<EOF

== Done. Paste this into .env (see .env.example) ==

AZURE_SEARCH_ENDPOINT=$SEARCH_ENDPOINT
AZURE_SEARCH_INDEX_NAME=$INDEX_NAME
AZURE_STORAGE_ACCOUNT_URL=$STORAGE_ACCOUNT_URL
AZURE_STORAGE_CONTAINER_NAME=$CONTAINER_NAME
AZURE_OPENAI_ENDPOINT=$AISERVICES_ENDPOINT
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=$EMBEDDING_DEPLOYMENT
AZURE_OPENAI_EMBEDDING_MODEL=$EMBEDDING_DEPLOYMENT
AZURE_AI_SERVICES_ENDPOINT=$AISERVICES_ENDPOINT
AZURE_AI_SERVICES_KEY=$AISERVICES_KEY
AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION_ID
AZURE_RESOURCE_GROUP=$RESOURCE_GROUP
AZURE_LOCATION=$LOCATION

Cost check: Basic Search runs ~\$75/mo prorated. Tear down with:
  az group delete --name $RESOURCE_GROUP --yes --no-wait
EOF
