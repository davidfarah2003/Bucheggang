<picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/readme/hero.png">
  <img src="docs/assets/readme/hero.gif" width="1280" alt="Leash">
</picture>

# Leash

Purchase controls for AI shopping agents.

Leash gives your agent a spending policy that you review in the Wallet. You decide what it may buy, which merchants it may use and how much it may spend. Each submitted purchase is checked against those rules and earlier account activity. Decisions include the checks and reasons behind them.

Built for the [Viseca challenge](viseca-2026/challenge.md). This prototype records purchase authorizations; it doesn't place orders or process payments.

[Watch the demo](docs/demo/leash-user-flow.mp4) · [How it works](#how-it-works) · [Architecture](#architecture) · [Classifier](#the-classifier) · [Run locally](#run-locally)

## How it works

1. Connect an MCP-compatible shopping agent. Approve its connection and access scopes in the Wallet.
2. Review the agent's proposed spending policy. Confirm the budget, product requirements and other limits before it can request purchases.
3. The agent submits a cart and final amount. Leash evaluates the request against the confirmed policy, spending state and purchase history.
4. Check the result in the Wallet. Requests needing your review wait for your answer and decline if the response window expires.

<img src="docs/assets/readme/wallet.png" width="1440" alt="The Wallet's shopping request, policy review and account-wide spending-limit screens.">

<sub>Local demo screens with an unconfirmed example policy.</sub>

Demo music: "Wallpaper" by Kevin MacLeod (incompetech.com), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). [Music credits](docs/demo/music/README.md). Re-record the video with `scripts/record_demo.py`.
The Wallet also lets you revoke an agent's access and edit account-wide spending rules. Those rule changes apply to later policy confirmations. An agent's connection alone grants no spending permission.

## Architecture

An external shopping agent calls Leash through MCP. The FastAPI backend serves the Wallet and handles policy confirmation and purchase requests. The decision engine evaluates structured inputs separately from transport and storage.

<img src="docs/assets/readme/architecture.png" width="1280" alt="The shopping agent and customer Wallet send requests to the Leash backend. The backend calls the decision engine and stores policies, evidence and state.">

Merchant descriptions are extracted into typed facts with source references. Merchant text cannot change the confirmed policy. Decisions and their evidence are saved alongside policy versions and spending state, so the Wallet can show what was checked.

[Technical contracts](docs/contracts.md) · [Agent connection and tools](docs/setup.md#connect-an-agent)

## The classifier

### From purchase to decision

The engine checks the confirmed rules first, including amount, merchant and product restrictions. A failed rule means decline. History checks use activity from before the purchase; optional behavioural and Jev assessments add information about unusual activity. Model output cannot override a failed rule.

<picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/readme/classifier.png">
  <img src="docs/assets/readme/classifier.gif" width="1280" alt="Animated example: a purchase meets its confirmed rules, history flags a new device, and the request moves to customer review.">
</picture>

| Decision | What happens |
| :--- | :--- |
| `approve` | The request is allowed under the confirmed policy. |
| `decline` | A check failed, or the policy requires declining the uncertainty. |
| `step_up` | The Wallet asks the customer to review the request. |

The confirmed policy determines how uncertain facts are handled. Conflicting facts cannot produce an automatic approval.

### Reasons you can inspect

The Wallet shows the decision reason and the checks that ran, with history and model output when available. Required model assessments are validated against the purchase they describe. Missing, invalid or timed-out required assessments stop authorization.

<picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/readme/evidence.png">
  <img src="docs/assets/readme/evidence.gif" width="1280" alt="Animated decision evidence expands into a recorded Jev probability breakdown, followed by an illustrated assessment-error case that stops authorization.">
</picture>

<sub>Both animations illustrate the evaluation flow. The Jev probabilities come from a [recorded response](docs/eval/jev-public-2026-09-25-evidence.json), not a live purchase.</sub>

## Run locally

Requires [Python 3.13+](https://www.python.org/downloads/) and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/davidfarah2003/Bucheggang.git
cd Bucheggang
uv sync

export LEASH_POLICY_STORE="$PWD/data/policy"
export LEASH_APP_ORIGIN="http://127.0.0.1:8000"
export LEASH_ENABLE_MODELS=0

uv run python -m leash.api
```

Open http://127.0.0.1:8000/app/ and create a demo account. This starts the Wallet with model calls disabled. Simulator-backed confirmation requires the challenge configuration described in the setup guide.

Shop currently hands requests to an external MCP client. The in-app provider adapter is unfinished.

[Setup guide](docs/setup.md) · [Connect an agent](docs/setup.md#connect-an-agent) · [Replay the public inputs](docs/run-replay.md) · [Design](docs/idea/viseca-agent-control-layer.md)

## Contributors

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/davidfarah2003">
        <img src="https://avatars.githubusercontent.com/u/37240868?v=4&amp;s=160" width="80" height="80" alt="David Farah"><br>
        <sub>David Farah</sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/deroskarmodulo">
        <img src="https://avatars.githubusercontent.com/u/100204300?v=4&amp;s=160" width="80" height="80" alt="Oskar Schmölz"><br>
        <sub>Oskar Schmölz</sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Rishabh-Barola">
        <img src="https://avatars.githubusercontent.com/u/93294516?v=4&amp;s=160" width="80" height="80" alt="Rishabh-Barola"><br>
        <sub>Rishabh-Barola</sub>
      </a>
    </td>
  </tr>
</table>
