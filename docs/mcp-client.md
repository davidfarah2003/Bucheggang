# Connect a shopping agent to the policy MCP server

The policy MCP server shares its draft directory with the Wallet API. The customer pairs each agent in the Wallet before it can read or propose policies. The account ID and token records are server-side. The browser never sees the agent token. Tool shapes and authentication rules are in `docs/contracts.md`, sections "Identity source" and "MCP tools".

The local demo supports MCP stdio and streamable HTTP. Both transports use the same `LEASH_POLICY_STORE` as the Wallet. The challenge key is not used by the MCP server.

## Start it over stdio

Set the same `LEASH_POLICY_STORE` that the Wallet API uses:

```sh
export LEASH_POLICY_STORE="$PWD/data/policy"
uv run python -m leash.policy.mcp_server
```

The agent calls `begin_pairing`, gives the customer the returned Wallet link, and keeps the returned verifier private. After the customer approves the labelled agent in the Wallet, the agent calls `complete_pairing` with the code and verifier. The MCP process keeps the resulting token in memory and authenticates later tools with it. Restarting the process requires pairing again, unless a valid `LEASH_AGENT_TOKEN` is provided at startup.

An MCP client JSON server list can use this command:

```json
{
  "mcpServers": {
    "leash-policy": {
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/Bucheggang", "python", "-m", "leash.policy.mcp_server"],
      "env": {
        "LEASH_POLICY_STORE": "/absolute/path/to/Bucheggang/data/policy"
      }
    }
  }
}
```

Use absolute paths. If the store path differs from the Wallet's, the customer will not find the draft.

## Start it over streamable HTTP

```sh
export LEASH_POLICY_STORE="$PWD/data/policy"
uv run python -m leash.policy.mcp_server --transport streamable-http --port 8791
```

The endpoint is `http://127.0.0.1:8791/mcp`. Unpaired clients can call only `begin_pairing` and `complete_pairing`. The first returns a pairing code and a private verifier. The agent sends the Wallet link containing the code to the customer and keeps the verifier. After Wallet approval, the agent completes pairing and receives a revocable token once. Later tool requests carry `Authorization: Bearer <agent token>`. Missing, invalid and revoked tokens all produce the same unauthorized tool error.

The code is an identifier used in the Wallet link, not sufficient to complete pairing. The verifier and token must not appear in URLs, logs, browser storage, checked-in files or MCP configuration literals. The server stores only their digests.

### Claude Code as the client

Register the HTTP endpoint without a header helper for the initial pairing. This lets the agent call the two pairing tools:

```sh
claude mcp add-json leash-policy \
  '{"type":"http","url":"http://127.0.0.1:8791/mcp"}'
```

After pairing, provide the token to the client process through its secret environment, then register the helper-backed endpoint. The helper reads `LEASH_AGENT_TOKEN` and emits the Authorization header without storing it:

```sh
claude mcp remove leash-policy
claude mcp add-json leash-policy \
  '{"type":"http","url":"http://127.0.0.1:8791/mcp","headersHelper":"/absolute/path/to/Bucheggang/scripts/leash_mcp_headers.sh"}'
```

Start Claude Code from the same shell that has `LEASH_AGENT_TOKEN` set. A silent prompt avoids shell history:

```sh
read -rs LEASH_AGENT_TOKEN && export LEASH_AGENT_TOKEN
claude
```

Never put a token in a command argument, config literal, repository file or channel message. Revoking the agent in the Wallet invalidates its token.

## Demo host

The customer Wallet remains on loopback. If the MCP endpoint is hosted remotely, expose only the MCP process over TLS and keep the Wallet API inaccessible through the tunnel. Pairing codes and verifiers are short-lived, and the token is returned only to the paired agent. Stop the tunnel and server after the demo.

## Tools the agent sees

| Tool | What it does |
| --- | --- |
| `begin_pairing` | Starts a five-minute Wallet pairing and returns a code plus a private verifier |
| `complete_pairing` | Returns one scoped, revocable token after the customer approves |
| `get_policy_authoring_instructions` | Returns the field vocabulary, rule format and proposal shape for one cardholder instruction |
| `propose_task_policy` | Validates and stores an immutable customer-owned draft |
| `get_policy_status` | Reads the state of a draft owned by the paired account |
| `get_policy_summary` | Reads the customer-facing sentences for a draft owned by the paired account |
| `buy` | Parked. Purchases arrive through the simulator in demo mode |
| `get_purchase_status` | Parked with `buy` |

The resource `policy://authoring-guide` requires a paired agent with `policy:read`. No tool confirms, resolves, tightens or revokes a policy.

## The flow an agent runs

1. Call `begin_pairing` and retain both returned values. Send the customer only the Wallet link containing the pairing code.
2. The customer logs in, reviews the displayed agent label and scopes, then approves in the Wallet.
3. Call `complete_pairing` with the code and private verifier. Securely provide the returned token to the MCP client for later requests.
4. Call `get_policy_authoring_instructions` with the customer's sentence.
5. Draft the proposal and call `propose_task_policy`. The customer-owned draft appears in the Wallet list and opens at `/app/?draft_id=<draft_id>`.
6. Poll `get_policy_status` until the customer confirms or rejects it. Use the `mandate_id` only after confirmation. Then search and authorize a purchase. External search or browsing before confirmation is outside backend control; only authorization is governed. No agent purchase API is active; demo purchase authorizations still arrive from the simulator. Examples are agent-authored claims and are not evaluated by this backend. For an exact product request, match the requested model and size from known facts; if the final all-in total is unknown, surface it as an open question rather than treating an estimate as a fact.
