<picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/readme/hero.png">
  <img src="docs/assets/readme/hero.gif" width="1280" alt="Leash">
</picture>

Leash checks the purchases an AI shopping agent submits against rules you approve in the Wallet. Set a budget and choose what it may buy. Requests that need your approval appear in the Wallet.

[Watch the demo](docs/demo/leash-user-flow.mp4) · [Run locally](#run-locally) · [Connect an agent](docs/setup.md#connect-an-agent)

<img src="docs/assets/readme/wallet.png" width="1440" alt="The Wallet's request, policy review and spending-limit screens.">

<sub>Local demo screens with an unconfirmed example policy.</sub>

Demo music: "Wallpaper" by Kevin MacLeod (incompetech.com), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). [Music credits](docs/demo/music/README.md). Re-record the video with `scripts/record_demo.py`.

## Architecture

<img src="docs/assets/readme/architecture.png" width="1280" alt="The shopping agent and customer Wallet send requests to the Leash backend. The backend calls the decision engine and stores policies, evidence and state.">

## The classifier

A failed policy rule means decline. The Wallet shows the checks and optional model output behind each decision. If a required assessment fails, the request stops.

<picture>
  <source media="(prefers-reduced-motion: reduce)" srcset="docs/assets/readme/classifier.png">
  <img src="docs/assets/readme/classifier.gif" width="1280" alt="An illustrated sequence showing purchase inputs, policy checks, optional history models, the reason for customer review and how assessment failures stop a request.">
</picture>

<sub>The flow is illustrated. The Jev probabilities come from a [recorded response](docs/eval/jev-public-2026-09-25-evidence.json).</sub>

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

Open http://127.0.0.1:8000/app/ and create a demo account. Model calls are disabled in this setup. Shop hands requests to an external MCP client; the in-app provider adapter is unfinished.

[Simulator and model setup](docs/setup.md) · [Replay the public inputs](docs/run-replay.md) · [Design](docs/idea/viseca-agent-control-layer.md) · [Contracts](docs/contracts.md)

Built for the [Viseca challenge](viseca-2026/challenge.md). This prototype records purchase authorizations. It doesn't place orders or process payments.

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
