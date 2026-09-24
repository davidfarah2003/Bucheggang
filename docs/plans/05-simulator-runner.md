# 05 Simulator runner

- Status: draft
- Owner: David (proposed)
- Lane: runner. Channel `team.zurichbuchegg.runner`, branch `lane/runner`, worktree `.worktrees/runner`
- User flow step: everything between "mandate confirmed" and "decision recorded": mandate calls, scenario start, polling, deadlines, decision submission, `/resolve`, state persistence, offline replay
- Design: [Hackathon demo mode](../idea/viseca-agent-control-layer.md#hackathon-demo-mode), [Demo constraints](../idea/viseca-agent-control-layer.md#demo-constraints)
- Papers: [SAFR](../papers/SAFR.pdf) (no unattended auto-approve on timeout; the audit log is written at the point of decision)
- Challenge API: [technical_details.md, steps 4 to 8 and the endpoint table](../../viseca-2026/technical_details.md); the existing [viseca_quickstart.ipynb](../../viseca_quickstart.ipynb) already does the connection check and is the starting point
- Contracts: `Event`, `Decision`, `MandateState`, `StepUp`, engine entry points in [contracts.md](../contracts.md)

## Goal

A worker that keeps a scenario run moving under the deadlines, with every accepted result written down once. It is the only code that holds the bearer key and the only code that talks to the simulator. It also provides `scripts/replay.py`, which feeds the 45 public attempts through the same `evaluate` call offline.

## Scope

In:

- `leash.runner.settings`: base URL and key from `.env`; `GET /v1/bootstrap` at start for the real deadline and human-window values.
- Mandate client: create, confirm, get, PATCH (tighten), DELETE (revoke). Called by the policy lane's confirm route and the app's tighten and revoke routes.
- Run loop: `POST /v1/scenario-runs`, then `GET /v1/decision-requests/next?wait=25` in a loop; 204 means check progress and continue; validate the envelope and the event strictly; skip a live ID already in `MandateState.handled` (reconcile, do not resubmit); otherwise call extract with a budget, then `evaluate`, then submit before `deadline_at`.
- Deadline guard: the budget for extract is `deadline_at - now - 2 s`, capped at 1.5 s; if `evaluate` has not returned 1 s before the deadline (it should take under 50 ms), submit `step_up` with `engine_timeout`. Never miss a deadline silently; log it.
- `step_up` handling: record as pending, expose through `GET /step-ups/pending`; when the app answers, `POST /resolve` and record; when the human window passes with no answer, `POST /resolve` with `decline` and `step_up_timeout`.
- State persistence after every accepted result (`data/state/<mandate_id>.json`), so a restarted worker reconciles instead of double-counting.
- Structured log per authorization: received, extract ms, evaluate ms, submitted at, accepted, time to deadline.
- `scripts/replay.py`: builds events from the CSVs in `replay_order`, assigns fresh real-clock deadlines, runs extract and `evaluate` with a given draft per scenario, prints the decision table and writes `docs/eval/replay-<date>.csv`.

Out:

- Deciding anything (plan 02). Reading merchant text (plan 03). Screens (plan 04).

## Steps

1. Settings and API client with retries on 5xx and a 30 s request timeout, matching the organizer's curl helper. `/healthz` and `/v1/bootstrap` smoke test.
2. Mandate client with a test against the `SCEN0000` instruction (the quickstart's rule) once the key arrives; before that, against a recorded response.
3. `scripts/replay.py` with the `SCEN0002` fixture draft. This unblocks the engine lane's replay test today, before the key.
4. Run loop and deadline guard, with a fake simulator (`tests/runner/fake_api.py`) that serves the CSV attempts over HTTP, delivers one authorization twice, and returns 204 between events.
5. Step-up handling and timeout resolution against the fake simulator.
6. Persistence and restart reconciliation test: kill the worker mid-run, restart, spend counted once.
7. Live run of `SCEN0000`, then `SCEN0001` to `SCEN0004`, log in `docs/eval/`.

## How we check it works

- Fake-simulator test: 45 attempts, zero missed deadlines, one duplicate delivery recorded once, one step-up resolved by an answer and one by timeout.
- Live `SCEN0000` accepted; live `SCEN0002` completes with the decision log in `docs/eval/`.
- `grep -rn "TEAM_API_KEY\|Bearer" src/` matches only `leash/runner/settings.py` and the client.
- Restart test passes.

## Open questions

- Revocation while a purchase is queued or in step-up: the spec says the platform's behaviour is unspecified. Proposed: after DELETE, the worker declines anything still queued for that mandate with `mandate_revoked`, and resolves pending step-ups with `decline`. Check against the live API on Friday morning and record here.
- `POST /v1/team/reset` before each demo run? Proposed: yes, then create a fresh mandate; old IDs are never reused.

## Log

(one line per finished task: date time, who, what, test, sha)
