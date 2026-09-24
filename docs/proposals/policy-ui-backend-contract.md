# Backend contract proposal for the follow-on policy UI

Status: proposal, read only. Nothing in `src/leash/contracts/`, `docs/contracts.md`, the routes or the store changes until the spine rules on Harness and global-policy scope. Requested by Oskar through oskar2 on 2026-09-25. Written by david_main against main at 0b7c2c1.

Three questions: (a) customer-scoped draft and mandate list shapes, (b) the smallest daily or monthly global spend model the engine can enforce across mandate supersession, (c) the slider fields and ranges the backend can honour exactly.

## What exists today

Identity. Every app route takes `customer` from the local `/session` cookie (`src/leash/api/main.py`, `authenticated_customer`). Ownership of a mandate is derived from `confirmation.json` in the draft folder, keyed by `confirmed_by` (`src/leash/policy/ownership.py`, `owned_confirmations`). A draft that has not been confirmed has no customer on it: `DraftStore.create` records no owner and the MCP authoring server has no customer identity, only the bearer token. The only pending-state marker with a customer is `confirmation_pending.json` (`confirmed_by`), written when the app starts a confirmation.

Store layout under `LEASH_POLICY_STORE` (default `data/policy/`): one folder per `draft_id`, files `v1.json`, `v2.json`, ..., `confirmation_pending.json`, `simulator_draft.json`, `confirmation.json`, `rejection.json`, `audit.jsonl`. Customer edits after confirmation live beside it in `data/mandate_edits/<mandate_id>.json` (`MandateEdits` in `src/leash/api/mandates.py`). Engine state is `data/state/<mandate_id>.json` (`MandateState`). Accepted decisions are `data/decisions/<mandate_id>/<authorization_id>.json` and `<authorization_id>.resolve.json`.

Routes the app already calls: `GET /drafts/{id}`, `POST /drafts/{id}/confirm`, `POST /drafts/{id}/reject`, `GET /mandates/{id}`, `POST /mandates/{id}/tighten`, `POST /mandates/{id}/revoke`, `GET /mandates/{id}/decisions`, `GET /decisions/{authorization_id}`, `GET /step-ups/pending`, `POST /step-ups/{authorization_id}/answer`. `GET /mandates/{id}` returns `{mandate, draft, effective_policy, state}` and reads the simulator on every call.

Engine period accounting (`src/leash/engine/rules.py`, `_in_window`): a `scope: period` rule on `authorization.billing_amount_chf` sums `state.approvals` whose simulated `timestamp` lies in `(now - period_days, now]`, excluding the current authorization, then adds this purchase. `state.approvals` is per mandate (`MandateState.mandate_id`). Period scope is defined for exactly two fields: `authorization.billing_amount_chf` and `state.approvals_count`. Any other field with `scope: period` raises.

Simulator constraints (`viseca-2026/technical_details.md`, lines 366 to 394): PATCH may add hard rules and may move `uncertainty_policy` to `decline`; it never removes or replaces a rule. One active mandate per team; a new confirmation supersedes the previous one. Observed on 2026-09-24 (plan 04, Later): a hard-rule PATCH returns `409 mandate_widening` even for an unchanged list, so in practice only the `uncertainty_policy` tighten works live. Revoking while a purchase is queued is unspecified.

## (a) Customer-scoped list responses

Two read-only routes, no new contract models. Both filter by the session customer and return only what the customer can already open one by one.

### `GET /drafts?state=pending|confirmed|rejected|all`

Default `state=pending`. Ownership of an unconfirmed draft is the open problem: today no customer is attached at creation. Two ways to close it, one decision for the owners:

1. The MCP server takes a customer id from the bearer token mapping (one token per customer in the demo), and `DraftStore.create` records `created_for`. Then `GET /drafts` lists drafts with `created_for == customer`. This is the shape the Wallet inbox needs and it is a store change (one new field in `v1.json`, nothing in the hash).
2. Until then, the inbox lists only drafts that have `confirmation_pending.json` with `confirmed_by == customer` plus every confirmed and rejected draft owned by the customer. An unconfirmed draft still reaches the Wallet by `?draft_id=` as today.

Item shape, one per draft, latest version only:

```
draft_id            str
version             int
hash                str
state               pending | confirming | confirmed | rejected   (DraftStore.decision_state plus confirmation_pending.json)
instruction         str
plain_english[]     str, one per rule, in rule order
uncertainty_policy  ask | decline | approve
open_questions      int, count of questions with answer == null
created_at          datetime
mandate_id          str | null   (from confirmation.json when confirmed)
```

No rules, no hash inputs, no examples in the list. The Wallet opens `GET /drafts/{id}` for the confirmation screen exactly as now, so the confirm still sends the fetched `version` and `hash`.

### `GET /mandates?status=active|superseded|revoked|expired|all`

Default `all`. Source: `owned_confirmations(store, customer)`, one row per `confirmation.json`. Item shape:

```
mandate_id       str
draft_id         str
version          int      (record version + edits revision, as GET /mandates/{id} computes it)
hash             str
status           active | superseded | revoked | expired
confirmed_at     datetime
instruction      str
approvals_count  int      (len(state.approvals) from data/state, 0 when no state file)
pending_step_ups int      (len(state.pending_step_ups))
```

`status` needs the simulator (`GET /v1/mandates/{id}`) per row, which is what `GET /mandates/{id}` does today. For a list that is one call per mandate. Two options: the list route makes those calls and fails loudly on the first simulator error (consistent with no fallbacks), or the list returns `status: null` and the Wallet reads status on open. I propose the first with a cap of the customer's mandates, which is a handful in the demo. A superseded mandate is one whose simulator status says so; we never infer it from ordering.

Both routes: 401 without a session, 200 with an empty list for a customer with nothing, 502 on a simulator failure with the simulator's body in `detail`, matching `_simulator_call`.

## (b) Smallest global spend model the engine can enforce

Constraint that decides the shape: the engine counts approvals per mandate (`MandateState.approvals`), and the simulator supersedes mandates, so a customer who confirms a second task in a day starts with an empty approvals list. A global daily or monthly cap that lives inside the mandate rules therefore resets on supersession. That is a real gap and the design already names it (plan 04, Later; idea doc, Global policies).

Proposal, two parts, with the engine signature unchanged.

### Global rule set, composed at confirmation

`data/global/<customer>.json`:

```
customer            str
version             int
rules[]             Rule    (same Rule contract, same vocabulary, same validation as a draft)
updated_at          datetime
```

At `POST /drafts/{id}/confirm`, the confirm route composes `global.rules + draft.rules` into the `hard_rules` sent to `POST /v1/mandates`, and the hash the store checks stays the draft's own hash (instruction + draft rules + uncertainty policy) as today. The composed list is what `GET /v1/mandates/{id}` returns and what `_effective` already compares against `draft.rules + edits.rules`. To keep `_effective` truthful, the confirmation record gains `global_version` and `global_rules` (the exact rules composed), so the comparison becomes `global_rules + draft.rules + edits.rules`. This is a one-field extension of `confirmation.json` and no contract model change, since `Rule` is reused.

A global edit applies to the next confirmed mandate. The Wallet says so on the policy screen when an active mandate's `global_version` is older than the customer's current global version. This matches the ruling already recorded in plan 04.

### Spend accounting across mandates

The smallest model the engine can enforce without a new signature: a period rule on `authorization.billing_amount_chf` whose window reads approvals from every mandate the customer confirmed, not only the current one.

Change: `_in_window` and `_prior_approvals` read `ctx.state.approvals` today. Add one field to `MandateState`:

```
customer_approvals[]   { authorization_id, mandate_id, amount_chf, timestamp }
```

filled by `engine.state.load` from every `data/state/<other_mandate>.json` whose confirmation belongs to the same customer, at load time. `evaluate` stays pure: it still receives one `MandateState`. The period rule then sums over `customer_approvals` plus its own approvals, deduplicated by `authorization_id`. This is the only engine change and it is contained in `rules.py` and `state.py`. The reason code stays `period_limit_exceeded`; `words.py` already phrases it as "your spending over the last N days".

Which rule shapes this supports exactly:

| Global control | Rule |
| --- | --- |
| daily agent spend cap of CHF X | `authorization.billing_amount_chf <= X, scope period, period_days 1, currency CHF` |
| monthly agent spend cap of CHF X | same with `period_days 30` |
| at most N agent purchases in D days | `state.approvals_count < N, scope period, period_days D` |
| never gift cards | `facts.is_gift_card = "false"` (engine already blocks detected gift cards globally, so this is redundant today) |
| blocked merchant countries | `authorization.merchant.merchant_country not_in [..]` |
| blocked merchant categories | `authorization.merchant.merchant_category not_in [..]` |

"Calendar month" is not expressible; the vocabulary only has trailing windows. A monthly cap is a trailing 30-day cap and the Wallet must label it that way.

Semantics that need to be stated once and then hold:

- Only accepted approvals count. A `step_up` counts only after the customer approves it and the runner records the resolve.
- Approvals under a superseded or revoked mandate still count in the window. Supersession changes permission going forward; it does not refund spend.
- A purchase that is itself over the cap is declined, never partially approved.
- Replay is unchanged: replay runs one scenario at a time with fresh state, so `customer_approvals` is empty there and the 45-attempt table is identical. Live differs from replay only when two mandates were confirmed by the same customer in one window, which is the case the model exists for.

What this does not cover: card-level spend outside the agent (the history CSV has it, but the design scopes global policy to agent shopping), and any per-merchant sub-budget.

## (c) Slider fields and ranges the backend supports exactly

A slider is honest only where the engine compares a number with `<`, `<=`, `>`, `>=` on a field the contract lists as a number. That is six fields. Anything else is a select or a toggle.

| UI control | Field | Operator | Unit | Range and step | Notes |
| --- | --- | --- | --- | --- | --- |
| Maximum per purchase | `authorization.billing_amount_chf` | `<=` | CHF | 10 to 3000, step 10 | the public history pack tops out at CHF 2955, so 3000 covers it |
| Spend cap over N days | `authorization.billing_amount_chf` scope period | `<=` | CHF, with `period_days` | amount 10 to 5000 step 10; days 1, 7, 14, 30 | window is trailing simulated days, not calendar |
| Maximum purchases | `state.approvals_count` | `<` | count | 1 to 10 step 1 | value N means at most N purchases; UI shows N, rule stores `< N` |
| Purchases over N days | `state.approvals_count` scope period | `<` | count, with `period_days` | as above | |
| Minimum return window | `facts.return_days` | `>=` | days | 0 to 60 step 1 | unknown makes the rule uncertain; 0 means "any stated window" |
| Maximum delivery fee | `authorization.delivery_fee` | `<=` | CHF | 0 to 50 step 1 | rule currency CHF; engine converts event currency at FX_TO_CHF |
| Maximum item count | `items.count` | `<=` | count | 1 to 20 step 1 | sums quantity over cart lines |

Not sliders:

- `authorization.currency`, `channel`, `fulfillment_method`, `order_returnable`, `merchant_category`, `merchant_mcc`, `merchant_country`, `items.category`, `facts.product_type`, `facts.size`: `in` / `not_in` multi-select or a single `=`. Values are strings; sizes compare after lowercase and whitespace normalisation, with an "EU " prefix dropped.
- `facts.is_gift_card`, `is_subscription`, `is_protection_plan`, `history.merchant_seen_on_card`, `history.device_seen_on_card`: a toggle writing `= "true"` or `= "false"` as strings. Do not offer `facts.is_addon` (plan 01 Decision 2026-09-25 00:20).
- `uncertainty_policy`: a three-way select, tightening only after confirmation.

Rules the slider UI must respect, all already enforced by `DraftStore._validate_rule` and `Rule`:

- `value` is a finite number for the numeric fields, never a boolean, null or object.
- `scope: period` requires `period_days >= 1` and is only valid on `billing_amount_chf` and `approvals_count`.
- `currency` is one of CHF, EUR, GBP, USD; the Wallet sends CHF.
- Every rule carries `source_text` and `plain_english`. A slider-authored rule uses the slider label as `source_text` and a generated sentence as `plain_english`, for example "Pay no more than CHF 200 per purchase."
- Any change to a draft is a new version through `DraftStore.revise` with the fetched `expected_version` and `expected_hash`; the confirm then sends the new version and hash. A slider can never edit a confirmed mandate; after confirmation only `tighten` (add a stricter rule, or `uncertainty_policy` to decline) is possible, and live the simulator currently refuses rule additions.

Sanity check against the engine at 0b7c2c1: `evaluate` decides `decline` on any failed rule, then `uncertainty_policy` on any uncertain rule, then `approve`. A slider-authored rule therefore behaves exactly like an agent-authored one.

## Dependencies and order

1. Spine ruling on Harness and global-policy scope. Nothing below starts before it.
2. Owners choose (a)1 or (a)2 for draft ownership. (a)1 touches `DraftStore.create` and the MCP server; (a)2 touches nothing.
3. `GET /drafts` and `GET /mandates` list routes: policy lane, no contract change, one PR.
4. Global rule set and composition at confirm: policy lane, `confirmation.json` gains two fields, `_effective` reads them. One PR, after 3.
5. `customer_approvals` in `MandateState` and the window change: engine lane, contract change, agreed on `team.zurichbuchegg.contracts` first, own PR. Replay must be row-for-row unchanged.
6. Slider UI: app lane, after 3, against the table in (c). Global controls after 4 and 5.

None of this is before the noon freeze. Steps 3 to 6 are afternoon or post-submission work, and `docs/roadmaps/post-submission-product-roadmap.md` is where they belong if they slip.
