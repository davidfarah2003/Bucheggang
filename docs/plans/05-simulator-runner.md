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

1. Settings and API client with a 30 s request timeout, matching the organizer's curl helper. No retry on 5xx or anywhere else: a non-2xx raises `ApiError(status, body)` (AGENTS.md section 6). Call `/healthz` and `/v1/bootstrap` once to see them answer.
2. Mandate client. Try it on the `SCEN0000` instruction (the quickstart's rule) once the key arrives; before that, against a recorded response.
3. `scripts/replay.py` with the `SCEN0002` fixture draft. This lets the engine lane replay today, before the key.
4. Run loop and deadline guard. Try it against the live API as soon as the key arrives.
5. Step-up handling and timeout resolution.
6. Persistence, so a restarted worker does not count spend twice. Try it once by killing the worker mid-run.
7. Live run of `SCEN0000`, then `SCEN0001` to `SCEN0004`, log in `docs/eval/`.

## How we check it works

- Live `SCEN0000` accepted; live `SCEN0002` completes with the decision log in `docs/eval/`.
- `grep -rn "TEAM_API_KEY\|Bearer" src/` matches only `leash/runner/settings.py` and the client.
- A worker killed mid-run and restarted counts spend once.

## Open questions

- Revocation while a purchase is queued or in step-up: the spec says the platform's behaviour is unspecified. Proposed: after DELETE, the worker declines anything still queued for that mandate with `mandate_revoked`, and resolves pending step-ups with `decline`. Check against the live API on Friday morning and record here.
- `POST /v1/team/reset` before each demo run? Proposed: yes, then create a fresh mandate; old IDs are never reused.

## Log

(one line per finished task: date time, who, what, how it was tried, sha)
2026-09-24 19:47 runner_builder: settings, API client and mandate client (leash.runner.settings, .api, .mandates); tried with `uv run python -c` calling api.healthz() -> {"status":"ok","service":"saw26-sandbox","api_version":"0.1.0"}, api.bootstrap() -> team_id team2, limits decision_timeout_seconds 8, step_up_timeout_seconds 120, long_poll_max_seconds 25, features.reset false, live scenarios SCEN0101 SCEN0135 SCEN0130 SCEN0106 SCEN0122 (not SCEN0000..0004); mandates.create(SCEN0000 quickstart draft, rule billing_amount_chf <= 20 CHF purchase, uncertainty ask) -> draft_c108c8b3cdf66c29, confirm -> TMd8b7df71d23ca697, get -> status active; get("TMdoesnotexist") raised ApiError 404 mandate_not_found; key redacted, read only in settings.py, @e383b5d
2026-09-24 19:47 runner_builder: bootstrap says team reset is disabled (features.reset false), so the open question on POST /v1/team/reset before demo runs resolves to: create a fresh mandate per run instead.
2026-09-24 19:58 runner_builder: run loop and deadline guard (leash.runner.loop.run_loop(run_id, evaluate, state), start_run, poll, handle, decide_with_guard; CLI leash.runner.cli with smoke evaluator decline_everything_smoke, never used in the demo). Live: POST /v1/scenario-runs with SCEN0000 returned HTTP 500 because our team only has SCEN0101 and the other bootstrap IDs, and the SCEN0000 mandate TMd8b7df71d23ca697 read back "superseded" (409 mandate_not_current) after the reviewer created a newer one, so the team holds one active mandate at a time. Fresh mandate TM58df07bd7241697f. First run run_effe33ed32ae00ce hit strict validation: envelope event_id is an int, and the run record has flat *_event_count fields plus status, not a counters object; both events went to platform timeout (decision_source timeout, reason timeout). Fixed; `uv run python -m leash.runner.cli --scenario SCEN0101 --mandate-id TM58df07bd7241697f --evaluate decline_everything_smoke` -> run_153aed19cb9ec643, AU10001 and AU10002 submitted about 8.0 s before deadline_at, accepted status declined with decision_source team, 204 then run status completed, 2/2 finalized. Guard tried offline on a recorded live event with deadline_at now+2 s and a 3 s evaluator: step_up engine_timeout returned after 1.01 s. The evaluator thread keeps running after the guard fires, so a hung evaluate holds the single worker and later requests also time out to engine_timeout. Key redacted, @d52f6e2
