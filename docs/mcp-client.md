# Connect a shopping agent to the policy MCP server

The policy MCP server is the only interface a shopping agent gets. It shares one draft directory with the Wallet API, so a draft the agent proposes is the draft the customer sees at `/app/?draft=<draft_id>`. The tools and their shapes are in `docs/contracts.md`, section "MCP tools".

It runs over stdio by default. For a client on another machine it can also serve streamable HTTP behind a shared bearer token (plan 01, Decisions, 2026-09-24 23:35).

## Start it over stdio

From the repository root, with the same `LEASH_POLICY_STORE` the Wallet API uses (`docs/run-wallet.md`):

```sh
export LEASH_POLICY_STORE="$PWD/data/policy"
uv run python -m leash.policy.mcp_server
```

The server reads and writes only that directory. It holds no simulator key and makes no network call.

For an MCP-compatible agent that takes a JSON server list (Claude Code, OpenCode, Codex and most others use this shape):

```json
{
  "mcpServers": {
    "leash-policy": {
      "command": "uv",
      "args": ["run", "--project", "/absolute/path/to/Bucheggang", "python", "-m", "leash.policy.mcp_server"],
      "env": { "LEASH_POLICY_STORE": "/absolute/path/to/Bucheggang/data/policy" }
    }
  }
}
```

Use absolute paths. If the store path differs from the Wallet's, the customer will not find the draft.

## Start it over streamable HTTP

```sh
export LEASH_POLICY_STORE="$PWD/data/policy"
export LEASH_MCP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run python -m leash.policy.mcp_server --transport streamable-http --port 8791
```

The endpoint is `http://127.0.0.1:8791/mcp`. `--host` defaults to `127.0.0.1`. Every HTTP request must carry `Authorization: Bearer <LEASH_MCP_TOKEN>`; any other request gets `401`. Startup raises if `LEASH_MCP_TOKEN` is unset or `--port` is missing. The token lives only in the environment of the shell that starts the server and of the shell that starts the client. Hand it to a teammate out of band, never in a file, a commit or a channel message.

### Demo day: David's machine behind cloudflared

The hosted demo runs on David's machine only, for the length of the demo, through a Cloudflare quick tunnel. There is no cloud deployment, no OAuth and no per-user account; the one shared token is the whole access control.

```sh
cloudflared tunnel --url http://127.0.0.1:8791 --http-host-header 127.0.0.1:8791
```

cloudflared prints a `https://<name>.trycloudflare.com` URL. The client URL is that host plus `/mcp`. Keep `--http-host-header`: the MCP library's DNS rebinding check answers `421` to a request whose `Host` is the tunnel name, and `200` once cloudflared rewrites it to `127.0.0.1:8791`. Stop the tunnel and the server after the demo, and use a fresh token each time.

Cloudflare documents that quick tunnels do not support Server-Sent Events. Checked on 2026-09-24 against this server through a quick tunnel with the `mcp` 2.2 `streamable_http_client`: the `initialize` POST, the `GET /mcp` event stream, `list_tools` and four tool calls all returned `200`, and a request without the header returned `401`. If a client's `GET /mcp` stream ever stalls through the tunnel, start the server with JSON responses instead of the event stream: the `mcp` library accepts `json_response=True` on `run(transport="streamable-http", ...)`.

### Claude Code as the client

`claude mcp add --header "Authorization: Bearer ..."` writes the header value into `~/.claude.json`, so do not use it here. Register the server with a `headersHelper` instead. Claude Code runs the helper on every connection and merges its JSON output into the request headers. `scripts/leash_mcp_headers.sh` prints the header from `LEASH_MCP_TOKEN` in the environment that started Claude Code and stores nothing:

```sh
claude mcp add-json leash-policy \
  '{"type":"http","url":"https://TUNNEL-HOST/mcp","headersHelper":"/absolute/path/to/Bucheggang/scripts/leash_mcp_headers.sh"}'
claude
```

Run `claude` from the same shell that generated `LEASH_MCP_TOKEN` and started the server, so the token is never typed. A teammate on another machine gets it out of band and reads it with a silent prompt, which keeps it out of shell history:

```sh
read -rs LEASH_MCP_TOKEN && export LEASH_MCP_TOKEN
claude
```

Never write `export LEASH_MCP_TOKEN=<value>` on a command line; the shell history file keeps it.

The single quotes keep the shell from expanding anything, and the stored entry holds only the URL and the helper path. The default local scope runs the helper only after you trust the project folder, so answer the trust dialog once. `claude mcp get leash-policy` then shows it connected, and `/mcp` lists six tools. If `LEASH_MCP_TOKEN` is unset, the helper exits non-zero with a message naming the variable, and the connection fails.

In a checked-out copy of this repository, a project `.mcp.json` can instead carry `"headers": {"Authorization": "Bearer ${LEASH_MCP_TOKEN}"}`. Claude Code expands `${VAR}` in `headers` of `.mcp.json` at connection time and stores only the reference. This variant was not tried.

## Tools the agent sees

| Tool | What it does |
| --- | --- |
| `get_policy_authoring_instructions` | field vocabulary, rule format and the proposal shape for one cardholder instruction |
| `propose_task_policy` | validates the agent's proposal and stores an immutable draft; returns the `draft_id`. An invalid proposal returns the `InvalidDraft` reason |
| `get_policy_status` | read-only: `pending`, `confirmed` with the `mandate_id` and `confirmed_at`, or `rejected` with the reason. Unknown draft is an error |
| `get_policy_summary` | read-only: the plain-English sentences, examples, open questions with any answers, and the uncertainty setting of the current version. No rule fields, no hash |
| `buy` | declared with the contract input schema; returns the error `purchases arrive through the simulator in demo mode; see plan 01 step 12` |
| `get_purchase_status` | declared with the contract input schema; parked with `buy`, same error |

The resource `policy://authoring-guide` is the same guide without the per-instruction wrapper. No tool confirms, resolves, tightens or revokes.

## The flow an agent runs

1. Call `get_policy_authoring_instructions` with the customer's sentence.
2. Draft the proposal with your own model and call `propose_task_policy`. Keep the `draft_id`.
3. Give the customer the Wallet link `/app/?draft=<draft_id>` and wait.
4. Poll `get_policy_status` until it is `confirmed`. Use the `mandate_id` it returns; you never see the rules again.
5. A `rejected` status means the customer wants a different policy: start again from step 1 with what they said.

A recorded session of this flow, with a live simulator mandate, is `docs/samples/mcp-transcript-scen0002.md`.
