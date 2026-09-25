#!/bin/sh
# Launch the Leash policy MCP server over stdio for an MCP client (OpenCode, Claude Desktop).
# Resolves the repo from this file's location, so a project-level opencode.json can call it by
# relative path. LEASH_POLICY_STORE and LEASH_APP_ORIGIN are required by the server; a client
# env block overrides the defaults below.
root="$(cd "$(dirname "$0")/.." && pwd)"
export LEASH_POLICY_STORE="${LEASH_POLICY_STORE:-$root/data/policy}"
export LEASH_APP_ORIGIN="${LEASH_APP_ORIGIN:-http://127.0.0.1:8000}"
uv_bin="$(command -v uv || echo "$HOME/.local/bin/uv")"
exec "$uv_bin" run --project "$root" python -m leash.policy.mcp_server "$@"
