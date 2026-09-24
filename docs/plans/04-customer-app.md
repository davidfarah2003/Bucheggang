# 04 Customer app

- Status: in progress
- Owner: Rishabh (proposed)
- Lane: app. Channel `team.zurichbuchegg.app`, branch `lane/app`, worktree `.worktrees/app`
- User flow steps: confirmation screen; step-up screen; policy and purchase history; the judge panel behind every decision
- Design: [Viseca authentication app](../idea/viseca-agent-control-layer.md#viseca-authentication-app), [Demo presentation](../idea/viseca-agent-control-layer.md#demo-presentation)
- Papers: [AutoCedar](../papers/2607.03656v1.pdf) (the reviewer sees plain-English claims and boundary examples, never raw policy code), [SAFR](../papers/SAFR.pdf) (the audit fields are the judge panel)
- Challenge page: technical preference that customer-facing controls fit Viseca's one mobile app; UI and decision backend decoupled
- Contracts: the backend HTTP table in [contracts.md](../contracts.md). The app codes against those routes and nothing else.

## Goal

Four screens a customer would use on a phone, plus one panel for judges. The app never computes a decision and never holds the challenge key. It reads drafts, mandates, decisions and pending step-ups from `leash.api` and writes confirmations, step-up answers, tightening and revocation through the authenticated routes.

## Scope

In:

1. Confirmation screen: the customer's sentence; each rule as one line of plain English with its source phrase highlighted; four example purchases with their expected outcome; open questions with options; Confirm and Reject. Confirm sends the draft's `version` and `hash`.
2. Step-up screen: what is being bought, from whom, for how much; the one reason the engine paused (`customer_message`); a countdown from `expires_at`; Approve and Reject. A list when several are pending.
3. Policy page: active mandate, its rules, spend so far in the period, purchase count, Tighten (add a rule, or set `uncertainty_policy` to `decline`) and Revoke.
4. History: every decision for the mandate with its outcome and one-line reason; tapping one opens the judge panel.
5. Judge panel: the `Event` as received (with `item_details` shown verbatim and marked untrusted), every `Check` with value and source, the state before and after, elapsed time, engine version, mandate version. Phone-width layout is fine; it is opened on a laptop during the pitch.

Out:

- Real Viseca login. A local username is enough; put a note in the footer.
- The shopping-agent chat. The agent's side is a terminal transcript in the demo (plan 06).

## Steps

1. Frontend decision: plain HTML, CSS and JavaScript in `app/`, served by FastAPI. No frontend build step. Pages must work at 400 px wide.
2. Build against the `SCEN0002` fixture draft from plan 01 and the example event from `viseca-2026/data/scenario_fixtures/` before the backend routes exist. Until the routes exist, pages read the sample JSON directly. Remove that data read when the routes land. There is no mock mode in the app.
3. Confirmation screen, then step-up screen. These two are in the demo.
4. Policy page with tighten and revoke.
5. History and judge panel.
6. Polling: the step-up list refreshes every 2 s; a pending step-up that the runner has already resolved (timeout) disappears with a note.
7. A screenshot of each screen in `docs/screens/` for the pitch deck.

## How we check it works

- Confirm with a stale hash shows the 409 message and reloads the draft.
- A pending step-up answered in the app is resolved on the simulator within the human window (checked in the runner's log, plan 05).
- Revoke on the policy page makes the next purchase in a run decline with `mandate_revoked`.
- Every screen renders at 400 px with no horizontal scroll.
- The judge panel for AU0016 shows `return_days: unknown` with source `merchant_text` and the resulting `step_up`.

## Open questions

- Frontend choice: plain HTML, CSS and JavaScript, served by FastAPI. This keeps the app readable and removes a build step before the deadline.
- Show the saved policy draft as the authoritative view, with a sentence explaining that the shopping agent proposed it. There is no second policy display.

## Log

(one line per finished task: date time, who, what, how it was tried, sha)
