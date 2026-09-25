#!/bin/sh
# Start the Wallet API and app for the demo with local purchases and the classifier on.
# Same defaults as scripts/mcp-stdio.sh so the agent's MCP server and the Wallet agree.
root="$(cd "$(dirname "$0")/.." && pwd)"
set -a
. "$root/.env"
set +a
export LEASH_POLICY_STORE="${LEASH_POLICY_STORE:-$root/data/policy}"
export LEASH_PORT="${LEASH_PORT:-8000}"
export LEASH_APP_ORIGIN="${LEASH_APP_ORIGIN:-http://127.0.0.1:$LEASH_PORT}"
export LEASH_PURCHASE_BUDGET_S="${LEASH_PURCHASE_BUDGET_S:-20}"
export LEASH_STEP_UP_WINDOW_S="${LEASH_STEP_UP_WINDOW_S:-300}"
export LEASH_LOCAL_CARD_ID="${LEASH_LOCAL_CARD_ID:-CA0001}"
export LEASH_ENABLE_MODELS="${LEASH_ENABLE_MODELS:-1}"
export LEASH_MODEL_MANIFEST="${LEASH_MODEL_MANIFEST:-$root/docs/eval/classifier/model-manifest.json}"
export LEASH_BEHAVIOUR_THRESHOLD="${LEASH_BEHAVIOUR_THRESHOLD:-0.498}"
uv_bin="$(command -v uv || echo "$HOME/.local/bin/uv")"
cd "$root"
exec "$uv_bin" run --group classifier python -m leash.api "$@"
