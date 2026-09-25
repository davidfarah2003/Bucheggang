#!/bin/sh
# Launch the Leash policy MCP server over stdio for an MCP client (OpenCode, Claude Desktop).
# Resolves the repo from this file's location, so a project-level opencode.json can call it by
# relative path. LEASH_POLICY_STORE and LEASH_APP_ORIGIN are required by the server; a client
# env block overrides the defaults below.
root="$(cd "$(dirname "$0")/.." && pwd)"
export LEASH_POLICY_STORE="${LEASH_POLICY_STORE:-$root/data/policy}"
export LEASH_APP_ORIGIN="${LEASH_APP_ORIGIN:-http://127.0.0.1:8000}"
# Local purchases: the Wallet judges the agent's cart under the confirmed mandate.
export LEASH_PURCHASE_BUDGET_S="${LEASH_PURCHASE_BUDGET_S:-20}"
export LEASH_STEP_UP_WINDOW_S="${LEASH_STEP_UP_WINDOW_S:-300}"
export LEASH_LOCAL_CARD_ID="${LEASH_LOCAL_CARD_ID:-CA0001}"
# Classifier on: behavioural model plus the Jev history questions; a failure raises, nothing substitutes.
export LEASH_ENABLE_MODELS="${LEASH_ENABLE_MODELS:-1}"
export LEASH_MODEL_MANIFEST="${LEASH_MODEL_MANIFEST:-$root/docs/eval/classifier/model-manifest.json}"
export LEASH_BEHAVIOUR_THRESHOLD="${LEASH_BEHAVIOUR_THRESHOLD:-0.498}"
uv_bin="$(command -v uv || echo "$HOME/.local/bin/uv")"
exec "$uv_bin" run --project "$root" --group classifier python -m leash.policy.mcp_server "$@"
