# Run the Wallet locally

Run these commands from the repository root with Python 3.13 and `uv` installed:

```sh
uv sync
cp .env.example .env
```

The challenge `TEAM_API_KEY` stays in the ignored `.env` and is read only by `leash.runner.settings`. Start the Wallet API with the shared policy store and its exact browser origin:

```sh
export LEASH_POLICY_STORE="$PWD/data/policy"
export LEASH_APP_ORIGIN="http://127.0.0.1:8000"
export LEASH_PORT=8000
uv run python -m leash.api
```

Open `http://127.0.0.1:8000/app/`. Register an account with a unique username and password, then use that account in the Wallet. The demo stores password hashes, sessions, pairings and agent-token digests under `LEASH_POLICY_STORE/identity/`. It is a local demo account, not a Viseca banking login. Do not expose the Wallet API beyond loopback for this demo.

Pair a shopping agent in the Wallet before it authors a policy. The agent starts pairing through MCP and gives the customer the link `/app/?pair=<pairing_code>`. The Wallet displays the agent label and scopes for approval. The private pairing verifier stays with the agent. After approval, the agent receives a scoped token; the browser never receives it.

The policy MCP server and Wallet API must use the same `LEASH_POLICY_STORE`. Open the draft link supplied by the paired agent at `/app/?draft_id=<draft_id>` to review it. The API reads simulator URL and key from `.env` only when confirmation calls the live API. The browser never receives that key. The API listens only on `127.0.0.1`.
