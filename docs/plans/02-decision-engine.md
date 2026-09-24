# 02 Decision engine

- Status: draft
- Owner: David (proposed)
- Lane: engine. Channel `team.zurichbuchegg.engine`, branch `lane/engine`, worktree `.worktrees/engine`
- User flow step: one proposed purchase in, `approve` / `decline` / `step_up` out, with evidence
- Design: [Decision pipeline](../idea/viseca-agent-control-layer.md#decision-pipeline), [Security requirements](../idea/viseca-agent-control-layer.md#security-requirements)
- Papers: [SAFR](../papers/SAFR.pdf) (checkpoint between proposal and execution, every action re-evaluated, audit record fields), [Verifiable Intent security model](https://verifiableintent.dev/spec/security-model/) (budgets and occurrence limits need state; signatures alone cannot enforce them), [AP2 specification](https://ap2-protocol.org/ap2/specification/) (approval bound to the exact purchase)
- Challenge API: [technical_details.md, steps 6 to 8 and Rule format](../../viseca-2026/technical_details.md); [event schema](../../viseca-2026/data/schemas/authorization_event.schema.json)
- Contracts: `Event`, `MandateState`, `Check`, `Decision`, reason codes, engine entry points in [contracts.md](../contracts.md). This lane owns `src/leash/contracts/`.

## Goal

A pure function, `evaluate(event, policy, state, facts) -> Decision`. No network, no model, under 50 ms. Every explicit requirement (amount, period budget, purchase count, expiry, allowed categories) is decided here and nowhere else. The runner calls it for live purchases, the policy lane calls it for the example purchases on the confirmation screen, and `scripts/replay.py` calls it for the 45 offline attempts.

## Scope

In:

- The contracts package: strict pydantic models mirroring the organizer schema.
- Rule evaluation over the field vocabulary, with `scope: purchase` and `scope: period` plus `period_days`.
- Mandate state per `mandate_id`: accepted approvals by simulated timestamp, handled live authorization IDs with their accepted result, pending step-ups, declines. Persisted to `data/state/<mandate_id>.json` after every accepted result.
- Checks beyond the rules, each returning a `Check`: every cart line against the requested item; unrequested add-ons; return terms; merchant category and type; merchant and device familiarity from `authorization_history.csv` (the base pack covers all four scenario cards); velocity from `recent_attempt_count_10m`; country; duplicate orders and re-quotes via `related_authorization_id`; gift cards, subscriptions, protection plans; injected instructions reported by the extract lane; lookalike merchant (name close to a known merchant, different `merchant_id`).
- Mapping uncertainty to the mandate's `uncertainty_policy` (`ask` becomes `step_up`).
- The `Decision` record with reason codes, evidence, a one-paragraph explanation, `engine_version`, elapsed time and the mandate version used.

Out:

- Reading merchant text (plan 03). The engine consumes `PurchaseFacts`; unknown facts count as uncertain.
- HTTP, polling, deadlines (plan 05).
- The confirmation flow (plan 01).

## Steps

1. Contracts package with tests that load `example_authorization_request.json` and reject a mutated copy (a missing required field, a boolean rule value).
2. Rule evaluator: resolve a field path against the event, facts, history and state. Operators `<`, `<=`, `=`, `!=`, `>`, `>=`, `in`, `not_in`. Period rules add the trailing-window approvals (simulated timestamps) to the purchase amount before comparing. Unknown value gives `uncertain`, never `pass`.
3. State store with idempotent `record`. Only an API-accepted `approve` moves spend and count. A pending `step_up` moves nothing. Delivery fees are already inside `billing_amount_chf`; do not add them twice.
4. Built-in checks, each a small function with a positive and a negative test, in this order: mandate active and not expired; hard rules; cart lines vs requested item; add-ons; return terms; merchant type; familiarity; velocity; country; duplicate and re-quote; gift card, subscription, protection plan; lookalike merchant; injected instructions.
5. Combine: any `fail` on an explicit rule or a hard check gives `decline`. Any `uncertain` with no `fail` gives the `uncertainty_policy` outcome. All `pass` gives `approve`. Injected instructions never change a rule: they add a reason code and evidence, and mark that line's facts uncertain.
6. Explanation and customer message in the customer's own terms ("CHF 230 is over your CHF 200 limit"). Evidence lists every check with value and source.
7. `tests/engine/test_latency.py`: p99 under 50 ms over the 45 replayed attempts.
8. `tests/engine/test_no_fixture_ids.py`: no string in `src/leash/engine/` matches `SCEN00`, `AU00` or `replay_order`.

## How we check it works

- Unit tests per check, positive and negative arm, all green.
- `scripts/replay.py --scenario SCEN0001 SCEN0002 SCEN0003 SCEN0004` (plan 05) runs every attempt with the policies from plan 06; decisions match `docs/eval/labels.csv`. Mismatches are listed in the Log with a reason, never hidden.
- Duplicate delivery of one live ID changes nothing the second time (test).
- Rolling spend: two approvals then a third over a 7-day limit is declined; a declined purchase in between does not count (test).
- Latency and fixture-ID tests green.

## Open questions

- "A shop I use regularly" (SCEN0000, SCEN0001 wording): is an unseen merchant a `fail` or `uncertain`? Proposed: `fail` when the instruction names prior use explicitly, `uncertain` otherwise. Decide with the policy lane; record the answer here.
- AU0016 (CHF 175, return terms not stated): `uncertain`, so `ask`, unless the confirmed draft answered the open question in plan 01. Confirm.
- Split orders in SCEN0001 (two purchases minutes apart at one merchant): treat as one order for the per-order limit, or two? The data does not say. Proposed: two purchases, each against the per-order limit, both against the period limit; note it on the judge panel.

## Log

(one line per finished task: date time, who, what, test, sha)
