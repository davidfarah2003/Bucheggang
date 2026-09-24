#!/bin/sh
# Claude Code headersHelper for the hosted policy MCP server (docs/mcp-client.md).
# Prints the bearer header from the caller's environment; the token is never stored.
set -eu
: "${LEASH_MCP_TOKEN:?LEASH_MCP_TOKEN is not set in the environment that started Claude Code}"
printf '{"Authorization":"Bearer %s"}\n' "$LEASH_MCP_TOKEN"
