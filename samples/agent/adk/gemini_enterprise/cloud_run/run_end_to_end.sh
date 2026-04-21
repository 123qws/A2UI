#!/usr/bin/env bash
set -euo pipefail

# End-to-end deploy + register flow for:
# samples/agent/adk/gemini_enterprise/cloud_run/README.md
#
# Usage:
#   1) Edit the USER INPUTS section below.
#   2) Run: ./run_end_to_end.sh

############################################
# USER INPUTS (edit these)
############################################
PROJECT_ID="123qws"
SERVICE_NAME="a2ui-demo"
MODEL_NAME="gemini-2.5-flash"   # gemini-2.5-flash or gemini-2.5-pro
LOCATION="global"               # Discovery Engine location (often global)
ENGINE_ID="a2ui-ge_1776736923776"      # Gemini Enterprise engine/app ID

AGENT_NAME="a2ui-demo"
AGENT_DISPLAY_NAME="A2UI Demo"
AGENT_DESCRIPTION="A2UI-enabled ADK deal assistant with HITL feedback"

############################################
# PRECHECKS
############################################
command -v gcloud >/dev/null || { echo "gcloud not found"; exit 1; }
command -v curl >/dev/null || { echo "curl not found"; exit 1; }

if [[ "$PROJECT_ID" == "YOUR_PROJECT_ID" ]]; then
  echo "Please set PROJECT_ID in USER INPUTS."
  exit 1
fi

if [[ "$ENGINE_ID" == "YOUR_ENGINE_ID" ]]; then
  echo "Please set ENGINE_ID in USER INPUTS."
  exit 1
fi

if [[ "$MODEL_NAME" != "gemini-2.5-pro" && "$MODEL_NAME" != "gemini-2.5-flash" ]]; then
  echo "MODEL_NAME must be gemini-2.5-pro or gemini-2.5-flash"
  exit 1
fi

############################################
# AUTH + PROJECT
############################################
# echo "==> Authenticating (you may be prompted)..."
# gcloud auth login
# gcloud auth application-default login

echo "==> Setting project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

echo "==> Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  discoveryengine.googleapis.com \
  aiplatform.googleapis.com

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
echo "PROJECT_NUMBER=$PROJECT_NUMBER"

############################################
# DEPLOY CLOUD RUN AGENT
############################################
echo "==> Deploying Cloud Run agent..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
chmod +x deploy.sh
./deploy.sh "$PROJECT_ID" "$SERVICE_NAME" "$MODEL_NAME"

REGION="us-central1" # deploy.sh currently uses this region
AGENT_URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
echo "AGENT_URL=$AGENT_URL"

############################################
# IAM: LET DISCOVERY ENGINE INVOKE CLOUD RUN
############################################
echo "==> Granting Cloud Run Invoker to Discovery Engine service agent..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

############################################
# REGISTER AGENT IN GEMINI ENTERPRISE
############################################
echo "==> Registering agent in Gemini Enterprise..."
LIST_URL="https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_NUMBER}/locations/${LOCATION}/collections/default_collection/engines/${ENGINE_ID}/assistants/default_assistant/agents"
REGISTER_URL="$LIST_URL"

EXISTING_AGENTS_JSON="$(curl -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "$LIST_URL")"

EXISTING_MATCH="$(
  AGENT_NAME="$AGENT_NAME" AGENT_DISPLAY_NAME="$AGENT_DISPLAY_NAME" python3 -c '
import json
import os
import sys

data = json.loads(sys.stdin.read() or "{}")
agents = data.get("agents", [])
target_name = os.environ["AGENT_NAME"]
target_display_name = os.environ["AGENT_DISPLAY_NAME"]

for agent in agents:
    if agent.get("name") == target_name or agent.get("displayName") == target_display_name:
        print(json.dumps(agent))
        break
' <<< "$EXISTING_AGENTS_JSON"
)"

if [[ -n "$EXISTING_MATCH" ]]; then
  echo "Agent already exists. Skipping registration."
  REGISTER_RESPONSE="$EXISTING_MATCH"
else
  REGISTER_RESPONSE="$(curl -sS -X POST \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    "$REGISTER_URL" \
    -d '{
      "name": "'"${AGENT_NAME}"'",
      "displayName": "'"${AGENT_DISPLAY_NAME}"'",
      "description": "'"${AGENT_DESCRIPTION}"'",
      "a2aAgentDefinition": {
        "jsonAgentCard": "{\"protocolVersion\": \"0.3.0\", \"name\": \"'"${AGENT_NAME}"'\", \"description\": \"'"${AGENT_DESCRIPTION}"'\", \"url\": \"'"${AGENT_URL}"'\", \"version\": \"1.0.0\", \"capabilities\": {\"streaming\": true, \"extensions\": [{\"uri\": \"https://a2ui.org/a2a-extension/a2ui/v0.8\", \"description\": \"Ability to render A2UI\", \"required\": false, \"params\": {\"supportedCatalogIds\": [\"https://a2ui.org/specification/v0_8/standard_catalog_definition.json\"]}}]}, \"skills\": [], \"defaultInputModes\": [\"text/plain\"], \"defaultOutputModes\": [\"text/plain\"]}"
      }
    }')"
fi

echo "==> Registration response:"
echo "$REGISTER_RESPONSE"

echo
echo "Done."
echo "Cloud Run service: $SERVICE_NAME"
echo "Region: $REGION"
echo "Agent URL: $AGENT_URL"
echo "Project number: $PROJECT_NUMBER"
echo "Engine ID: $ENGINE_ID"
echo
echo "Next:"
echo "1) Open Gemini Enterprise UI for engine '$ENGINE_ID'"
echo "2) Find '$AGENT_DISPLAY_NAME'"
echo "3) Click Preview and test prompts like:"
echo "   - Show deal status for Acme Retail Group"
echo "   - List all open deals"
echo
echo "Optional unregister (replace AGENT_ID):"
echo "curl -X DELETE -H \"Authorization: Bearer \$(gcloud auth print-access-token)\" -H \"Content-Type: application/json\" \"https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_NUMBER}/locations/${LOCATION}/collections/default_collection/engines/${ENGINE_ID}/assistants/default_assistant/agents/AGENT_ID\""
