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

1. Contracts package. Load `example_authorization_request.json` through it once to see it parse.
2. Rule evaluator: resolve a field path against the event, facts, history and state. Operators `<`, `<=`, `=`, `!=`, `>`, `>=`, `in`, `not_in`. Period rules add the trailing-window approvals (simulated timestamps) to the purchase amount before comparing. Unknown value gives `uncertain`, never `pass`.
3. State store with idempotent `record`. Only an API-accepted `approve` moves spend and count. A pending `step_up` moves nothing. Delivery fees are already inside `billing_amount_chf`; do not add them twice.
4. Built-in checks, each a small function, in this order: mandate active and not expired; hard rules; cart lines vs requested item; add-ons; return terms; merchant type; familiarity; velocity; country; duplicate and re-quote; gift card, subscription, protection plan; lookalike merchant; injected instructions.
5. Combine: any `fail` on an explicit rule or a hard check gives `decline`. Any `uncertain` with no `fail` gives the `uncertainty_policy` outcome. All `pass` gives `approve`. Injected instructions never change a rule: they add a reason code and evidence, and mark that line's facts uncertain.
6. Explanation and customer message in the customer's own terms ("CHF 230 is over your CHF 200 limit"). Evidence lists every check with value and source.
7. Time the replay of the 45 attempts once and write p99 in the Log. Target under 50 ms.

## How we check it works

- `scripts/replay.py --scenario SCEN0001 SCEN0002 SCEN0003 SCEN0004` (plan 05) runs every attempt with the policies from plan 06; decisions match `docs/eval/labels.csv`. Mismatches are listed in the Log with a reason, never hidden.
- Feeding the same live ID twice changes nothing the second time (try it once by hand).
- Rolling spend: two approvals then a third over a 7-day limit is declined; a declined purchase in between does not count (try it once in the replay).
- `grep -rn "SCEN00\|AU00\|replay_order" src/leash/engine/` prints nothing.

## Decisions

- For "a shop I use regularly", an unseen merchant fails when the confirmed instruction explicitly requires prior use. If it does not, merchant familiarity is uncertain.
- AU0016 has unknown return terms, so it is uncertain and follows the confirmed draft's uncertainty policy. If the customer answered the return-terms question during confirmation, evaluate against the rule created from that answer.
- Treat the two SCEN0001 purchases minutes apart as separate orders for the per-order limit. Count both against the period limit and explain this interpretation on the judge panel.

## Log

(one line per finished task: date time, who, what, how it was tried, sha)
2026-09-24 19:47 engine_builder: task 1 contracts package src/leash/contracts/ (Event strict mirror of the organizer schema, PolicyDraft, Rule, Mandate, PurchaseFacts, MandateState, Check, Decision, StepUp, StepUpAnswer); `uv run python -c "Event.model_validate(json.load(open('viseca-2026/data/scenario_fixtures/example_authorization_request.json')))"` printed `AU_EXAMPLE_0001 20.0 1`; docs/samples/scen0002_draft.json parses as PolicyDraft; an extra key plus a string amount raise 2 validation errors. Unknown facts are `None` in PurchaseFacts. @a6ec5bf
2026-09-24 19:51 engine_builder: task 2 rule evaluator leash.engine.rules (evaluate_rule, evaluate_rules, reason_code; history familiarity from authorization_history.csv; period scope sums accepted approvals in the trailing window of simulated time). Tried with the 12 SCEN0002 attempts, the sample draft and leash.extract facts: AU0012 all pass, AU0013 size 42 fail, AU0014/AU0015 return days 0/7 fail, AU0016 return days unknown gives uncertain, AU0017 trail shoes fail, AU0021 CHF 215 fail, AU0022 sustainable_goods fail, approvals_count fails after the first approval; under 0.1 ms per attempt. A 7-day CHF 400 period rule passed at 150+165 and failed at 250+165 with an 8-day-old approval excluded. Branch lane/engine-rules, stacked on PR #15. @602e280
