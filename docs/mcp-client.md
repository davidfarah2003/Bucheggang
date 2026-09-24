# Connect a shopping agent to the policy MCP server

The policy MCP server is the only interface a shopping agent gets. It runs over stdio and shares one draft directory with the Wallet API, so a draft the agent proposes is the draft the customer sees at `/app/?draft=<draft_id>`. The tools and their shapes are in `docs/contracts.md`, section "MCP tools".

## Start it

From the repository root, with the same `LEASH_POLICY_STORE` the Wallet API uses (`docs/run-wallet.md`):

```sh
export LEASH_POLICY_STORE="$PWD/data/policy"
uv run python -m leash.policy.mcp_server
```

The server reads and writes only that directory. It holds no simulator key and makes no network call.

## Client configuration

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

## Tools the agent sees

| Tool | What it does |
| --- | --- |
| `get_policy_authoring_instructions` | field vocabulary, rule format and the proposal shape for one cardholder instruction |
| `propose_task_policy` | validates the agent's proposal and stores an immutable draft; returns the `draft_id` |
| `get_policy_status` | `pending`, `confirmed` with the `mandate_id`, or `rejected` |
| `get_policy_summary` | the plain sentences, examples and open questions of the stored draft |
| `buy`, `get_purchase_status` | declared in the contract, parked until after the submission (plan 01 step 12) |

The resource `policy://authoring-guide` is the same guide without the per-instruction wrapper.

## The flow an agent runs

1. Call `get_policy_authoring_instructions` with the customer's sentence.
2. Draft the proposal with your own model and call `propose_task_policy`. Keep the `draft_id`.
3. Give the customer the Wallet link `/app/?draft=<draft_id>` and wait.
4. Poll `get_policy_status` until it is `confirmed`. Use the `mandate_id` it returns; you never see the rules again.
5. A `rejected` status means the customer wants a different policy: start again from step 1 with what they said.

A recorded session is in `docs/samples/mcp-transcript-scen0002.md` once plan 01 step 11 is done.
