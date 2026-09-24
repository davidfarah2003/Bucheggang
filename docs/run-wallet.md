# Run the Wallet locally

Run these commands from the repository root with Python 3.13 and `uv` installed:

```sh
uv sync
cp .env.example .env
```

Add the challenge `TEAM_API_KEY` to `.env`. Keep that file local. Start the Wallet API with the policy store directory exported:

```sh
export LEASH_POLICY_STORE="$PWD/data/policy"
uv run python -m leash.api
```

Open `http://127.0.0.1:8000/app/`. The Wallet uses a local demo username. After an MCP-compatible shopping agent creates a draft in the same `LEASH_POLICY_STORE`, open `http://127.0.0.1:8000/app/?draft=<draft_id>` to review it. Configure the agent's policy MCP process with that same `LEASH_POLICY_STORE` value.

The API reads the simulator URL and key from `.env` when confirmation calls the live API. The browser never receives the key. The API listens only on `127.0.0.1` by default.
