#!/bin/sh
# Headers helper for a paired policy MCP agent.
set -eu
: "${LEASH_AGENT_TOKEN:?LEASH_AGENT_TOKEN is not set in the environment that started the MCP client}"
printf '{"Authorization":"Bearer %s"}\n' "$LEASH_AGENT_TOKEN"
