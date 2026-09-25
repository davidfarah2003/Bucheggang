#!/bin/sh
# Launch the Leash policy MCP server over stdio for an MCP client (OpenCode, Claude Desktop).
# Both variables are required by leash.policy.mcp_server; a client can override them in its env block.
export LEASH_POLICY_STORE="${LEASH_POLICY_STORE:-/Users/david/Projects/Bucheggang/data/policy}"
export LEASH_APP_ORIGIN="${LEASH_APP_ORIGIN:-http://127.0.0.1:8000}"
exec /Users/david/.local/bin/uv run --project /Users/david/Projects/Bucheggang python -m leash.policy.mcp_server "$@"
