# Setup details

Start with the [local Wallet setup](../README.md#run-locally). Run the commands below from the checkout root. FastAPI serves the Wallet directly; there is no frontend build step.

## Simulator access

Simulator-backed confirmation and live runs require the challenge configuration. On a fresh checkout, create the ignored configuration file:

```sh
cp .env.example .env
```

Set the team key in that file. Keep it out of source control, terminal output and client configuration. Simulator credentials are handled by the runner settings module.

The Wallet, MCP server and runner must use the same checkout and `LEASH_POLICY_STORE`. `LEASH_APP_ORIGIN` must exactly match the Wallet origin, including its port.

## Optional risk models

The quick start explicitly disables model calls. Enabling them requires the `classifier` dependency group, a model manifest and the separately scoped OpenRouter credential. The demo launch scripts also configure local purchase budgets and can enable models by default. Inspect their settings before running them.

With `LEASH_ENABLE_MODELS=1`, `LEASH_MODEL_MANIFEST` names the model file and `LEASH_BEHAVIOUR_THRESHOLD` sets the CatBoost score at which a purchase gets an uncertain check. The demo scripts use the evaluation manifest with threshold 0.498. The reviewed operating point is the overlay `docs/eval/classifier/model-o4-1pct.json`, which pins the manifest by hash and carries its own cut, so name it in `LEASH_MODEL_MANIFEST` and leave the threshold unset. The provider adapter rejects a Jev probability that is not on the two-decimal grid and a distribution that drifts more than 0.015 from one; a bad response raises and no decision is substituted.

See the [classifier implementation and measurements](eval/classifier/), the [O4 operating point](eval/classifier/o4-operating-point.md) and [runner configuration](../src/leash/runner/settings.py). The optional `harness` dependency group belongs to the unfinished in-app provider adapter.

## Run the demo as recorded

The demo video runs the Wallet with local purchases and both risk models on. Two scripts set the same environment for the Wallet and the agent's MCP server (purchase budget 20 s, step-up window 5 min, demo card CA0001, models on with the behavioural threshold 0.498):

```sh
rm -rf data/policy data/state data/decisions data/stepups data/purchases data/mandate_edits data/locks data/intents
scripts/wallet.sh                       # Wallet on http://127.0.0.1:8000
```

Point the agent at `scripts/mcp-stdio.sh` (the repo's `opencode.json` already does). To watch the whole flow without an agent client, run `uv run --group classifier python scripts/flow_sim.py --manual` and act in the Wallet as the customer. Both need the classifier dependency group, the model manifest and the OpenRouter credential in `.env`.

To re-record the video: start the Wallet on a wiped `data/` as above, then `uv run --group classifier --with playwright python scripts/record_demo.py`. It writes `docs/demo/leash-user-flow.mp4` and the gif. Wipe `data/` before every take; the Wallet, the MCP server and the browser share it, and a stale account hides the new draft.

## Connect an agent

Leash supports MCP over stdio and streamable HTTP. The customer can approve a pending connection in the Wallet; the agent then uses the policy and purchase tools within its granted scopes.

<details>
<summary>Example stdio configuration for clients that use <code>mcpServers</code></summary>

Replace both absolute paths with your checkout location. These settings retain model-off operation.

```json
{
  "mcpServers": {
    "leash": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/absolute/path/to/Bucheggang",
        "python",
        "-m",
        "leash.policy.mcp_server"
      ],
      "env": {
        "LEASH_POLICY_STORE": "/absolute/path/to/Bucheggang/data/policy",
        "LEASH_APP_ORIGIN": "http://127.0.0.1:8000",
        "LEASH_ENABLE_MODELS": "0"
      }
    }
  }
}
```

</details>

| Tool group | Tools |
| :--- | :--- |
| Connection | `connect`, `begin_pairing`, `complete_pairing` |
| Policy | `get_policy_authoring_instructions`, `propose_task_policy`, `get_policy_status`, `wait_for_policy`, `get_policy_summary` |
| Local purchase | `buy`, `get_purchase_status`, `wait_for_purchase` |

Purchasing requires a confirmed mandate, the purchase scope, a recorded card identity and configured purchase/step-up budgets. A successful connection alone grants no spending permission. No MCP tool confirms a policy or answers a purchase question for the customer.

[Client setup and transports](mcp-client.md) · [Tool implementation](../src/leash/policy/mcp_server.py) · [Purchase input contract](contracts.md#purchase-input-and-idempotency)

## Verification

The public replay runs the real extractor, decision engine and in-memory state projection across five scenarios and 45 purchase attempts. It requires no simulator key or model calls.

```sh
uv run python scripts/replay.py --all \
  --policy SCEN0000=docs/eval/replay-policies/SCEN0000.json \
  --policy SCEN0001=docs/eval/replay-policies/SCEN0001.json \
  --policy SCEN0002=docs/samples/scen0002_draft.json \
  --policy SCEN0003=docs/eval/replay-policies/SCEN0003.json \
  --policy SCEN0004=docs/eval/replay-policies/SCEN0004.json \
  --output /tmp/leash-replay.csv
```

Choose a new output filename for a subsequent run. Existing reports are never overwritten.

| Recorded deterministic replay | Count |
| :--- | ---: |
| Inputs | 45 |
| Approve | 11 |
| Decline | 32 |
| Ask the customer | 2 |

These are decision counts. Against the reconciled expected decisions in `docs/eval/labels.csv`, the engine agrees on 43 of 45 attempts; the two disagreements and their causes are in [the labelled report](eval/report-labelled.md). Provider exercises, simulator runs and human Wallet verification have separate evidence records.

[Replay assumptions and commands](run-replay.md) · [Recorded exercises](eval/) · [Live verification checklist](live-demo-checklist.md)


## Policies and records

The customer approves an agent connection and its scopes. The agent receives revocable credentials, and ownership checks protect drafts and purchase records. A policy has a version and content hash that the backend checks at confirmation.

Rules cover spending, products, merchants, quantity, purchase counts and rolling budgets. Account-wide edits apply to later confirmations. Unknown facts follow the confirmed uncertainty setting; a customer question waits for an answer or its timeout.

The backend keeps decisions, evidence and state on disk. Local purchase keys support idempotency, and simulator calls have a separate recovery path. Local MCP purchases do not enter a simulator run or score.

The engine is separate from transport and persistence. Extracted facts retain provenance, and merchant text cannot edit the confirmed rules. Instruction-pattern detection and conflict handling cover the measured cases; they do not establish general prompt-injection immunity.
