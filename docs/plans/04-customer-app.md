# 04 Customer app

- Status: in progress
- Owner: Rishabh (proposed)
- Lane: app. Channel `team.zurichbuchegg.app`, branch `lane/app`, worktree `.worktrees/app`
- User flow steps for this demo: task-policy confirmation, step-up, one active policy, and history in the standalone Viseca Wallet
- Design: [Viseca Wallet](../idea/viseca-agent-control-layer.md#viseca-wallet), [Demo presentation](../idea/viseca-agent-control-layer.md#demo-presentation)
- Papers: [AutoCedar](../papers/2607.03656v1.pdf) (the reviewer sees plain-English claims and boundary examples, never raw policy code), [SAFR](../papers/SAFR.pdf) (the audit fields are the judge panel)
- Challenge page: customer-facing controls should be mobile-first; the later Shopping Harness may share the Wallet's web app shell, while the Wallet remains usable on its own
- Contracts: the backend HTTP table in [contracts.md](../contracts.md). The app codes against those routes and nothing else.

## Goal

The current demo is the standalone Viseca Wallet at `/app/`: it loads the single pending task draft named by `?draft=<id>`, lets the customer confirm it, then shows that mandate across four screens and the judge panel. It does not require the customer to open or configure a Shopping Harness; an external MCP-compatible agent can create the draft and link directly to the Wallet. The product target is one mobile-first web app with distinct Shopping Harness and Wallet pages or swipeable views over the same backend. Neither interface computes purchase decisions or holds the challenge key. The app targets a 400 px phone viewport.

## Scope

In:

1. Wallet request page at `/app/?draft=<id>`: the customer's sentence, readable rules, source phrases, example outcomes and open-question options. Confirm sends the draft's `version` and `hash`; Reject sends its version, hash and reason.
2. Step-up screen: what is being bought, from whom, for how much; the one reason the engine paused (`customer_message`); a countdown from `expires_at`; Approve and Reject for a pending step-up.
3. Policy page: the one confirmed mandate for this demo, its rules, spend so far, purchase count, Tighten and Revoke.
4. History: every decision for the mandate with its outcome and one-line reason; tapping one opens the judge panel.
5. Judge panel: the `Event` as received (with `item_details` shown verbatim and marked untrusted), every `Check` with value and source, the state before and after, elapsed time, engine version, mandate version.

Out:

- Real Viseca authentication. A local username is enough for the demo; production authentication remains with Viseca.

## Steps

1. Serve the standalone mobile-first Wallet at `/app/`, with the draft ID in the query URL. Use plain HTML, CSS and JavaScript in `app/`, served by FastAPI. No frontend build step. It must work at 400 px wide.
2. Load the named saved proposal through the backend. Never read a sample JSON file after the route exists. There is no mock mode.
3. Build the confirmation flow, single active-mandate view, step-up screen, history and judge panel.
4. Polling: the step-up list refreshes every 2 s; a pending step-up that the runner has already resolved (timeout) disappears with a note.
5. Capture screenshots of the Wallet screens in `docs/screens/` for the pitch deck.

## How we check it works

- Confirm with a stale hash shows the 409 message and reloads the draft.
- A pending step-up answered in the app is resolved on the simulator within the human window (checked in the runner's log, plan 05).
- Revoke on the policy page makes the next purchase in a run decline with `mandate_revoked`.
- Every view renders at 400 px with no horizontal scroll.
- The Wallet request URL loads the specified saved draft; after confirmation it shows the returned mandate without requiring a harness.
- The judge panel for AU0016 shows `return_days: unknown` with source `merchant_text` and the resulting `step_up`.

## Decisions

- Use plain HTML, CSS and JavaScript in `app/`, served by FastAPI. This keeps the app readable and removes a build step before the deadline.
- Show the saved policy draft as the authoritative view, with a sentence explaining that the shopping agent proposed it. There is no second policy display.
- Use the local `/session` cookie contract for the demo. The app loads saved drafts through `GET /drafts/{id}` and uses the runner's live step-up routes.
- Deliver the mobile-first Wallet demo first. It works directly from `/app/?draft=<id>` without a Shopping Harness.
- Mount the customer UI in the FastAPI shell with `leash.api.static.mount_customer_app(api)`.
- `docs/screens/` has a 400 px review capture and preview captures for approvals, policy, activity and the judge panel. The previews use the organizer's example Event and temporary browser data, not a live decision. Replace the judge preview with AU0016 after the decision detail route is live.

## Later

- Add the Shopping Harness as a separate page or swipeable view in the same web app. It offers configured agent or model providers including Apertus, ChatGPT/OpenAI, Claude/Anthropic, Grok/xAI, Gemini/Google and DeepSeek. Provider errors are visible and never trigger a silent model switch. The harness is optional; the customer can use the Wallet directly with drafts created by an external MCP-compatible agent.
- Connect the selected agent to the existing policy-authoring MCP tools. The agent proposes and previews policy; only the Wallet confirms it.
- Present supported numeric policy limits with clear units and editable sliders. Any uncertainty band must map to an explicit backend rule; otherwise show it as an open question. Do not approximate policy meaning in the UI.
- Add a pending-draft inbox and a list of confirmed mandates after the current live flow works end to end. The Wallet must remain directly usable without the Harness. Agree any required list-route contracts before implementation.
- Add persistent account-wide global policy controls after the live runner loop, app step-up flow and replay work end to end. Do not add `GlobalPolicy` to `docs/contracts.md` or the engine signature before then.
- When global policies are added, compose their rules with the task rules into one effective `PolicyDraft` at confirmation and hash exactly what is sent to the simulator. The live API supports one active mandate per team; a new confirmation supersedes it, and hard-rule PATCH returns `409 mandate_widening` even for an unchanged list. Global updates therefore apply on the next confirmed mandate; the Wallet must disclose when an existing active mandate still uses the earlier version.

## Log

(one line per finished task: date time, who, what, how it was tried, sha)
2026-09-24 18:38 rb_turbo_charged: built responsive review, step-up, policy, activity and evidence screens; `node --check app/app.js` exited 0, local HTTP returned 200 for page, CSS, JS and draft, Chrome at 400 px rendered the review with `scrollWidth: 400`; @6ebf233.
2026-09-24 18:41 rb_turbo_charged: constrained tightening controls to active mandates and strictly lower purchase caps; `node --check app/app.js` exited 0; mutation routes are not implemented yet, so the behavior was not run against the backend; @7e24ed0.
2026-09-24 18:55 rb_turbo_charged: showed the full Event and explicit unknown Check values in the judge panel, retained resolved-step-up notices across navigation, and captured four phone previews in `docs/screens/`; `node --check app/app.js` exited 0 and Chrome rendered approvals, policy, activity and the judge panel at 400 px with `scrollWidth: 400` using temporary organizer-example data; live route checks remain open; @d6c2f5b.
2026-09-24 18:58 rb_turbo_charged: added `leash.api.static.mount_customer_app` for the UI and temporary sample path; `PYTHONPATH=src uv run --no-project --with fastapi --with httpx python3 -c '...'` called both mounted paths and returned `app 200`, `draft 200`; the first call without `PYTHONPATH=src` failed with `ModuleNotFoundError: leash`; shell inclusion remains open.
2026-09-24 20:32 oskar1: aligned demo scope with the owner ruling: standalone mobile-first Wallet first; Harness, sliders, draft inbox, mandate list and global policies are Later.
