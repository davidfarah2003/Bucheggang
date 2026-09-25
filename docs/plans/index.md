# Plans

One file per lane, numbered in user-flow order. Each plan's Log records implementation and verification. The status below describes the lane as a whole, not the state of every task or an open PR.

Deadline: expert-round submission Friday 25 September 2026 at 12:00, final submission 17:30 (timeline in `AGENTS.md`, section 10).

| # | Plan | Lane | Channel | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| 01 | [Policy draft and confirmation](01-policy-confirmation.md) | policy | `team.zurichbuchegg.policy` | Oskar | in progress |
| 02 | [Decision engine](02-decision-engine.md) | engine | `team.zurichbuchegg.engine` | David | in progress |
| 03 | [Merchant-text extraction](03-merchant-text-extraction.md) | extract | `team.zurichbuchegg.extract` | Oskar | in progress |
| 04 | [Customer app](04-customer-app.md) | app | `team.zurichbuchegg.app` | Rishabh | in progress |
| 05 | [Simulator runner](05-simulator-runner.md) | runner | `team.zurichbuchegg.runner` | David | in progress |
| 06 | [Evaluation and demo](06-evaluation-and-demo.md) | all | `team.zurichbuchegg` (spine) | everyone; Rishabh drives the pitch | in progress |
| 07 | [End-to-end delivery](07-end-to-end-delivery.md) | cross-lane | `team.zurichbuchegg` (spine) | Oskar, David and Rishabh by lane | in progress |

For the merged local Wallet entry point and shared policy store, see [run-wallet.md](../run-wallet.md) and [mcp-client.md](../mcp-client.md). The authenticated customer-owned `GET /drafts` and `GET /mandates` list routes landed in policy PR #48. Policy PR #52 made draft file publication atomic and tightened proposal validation. [Plan 07](07-end-to-end-delivery.md) records the current release cut, product journey, dependencies and acceptance gates across lanes. Open PRs and held work remain outside this index's shipped status.

Status values: `draft`, `agreed`, `in progress`, `done`, `dropped`.
