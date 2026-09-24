# Contracts between lanes

The executable versions are the pydantic models in `src/leash/contracts/`, owned by the engine lane. A change to this file or that package is agreed on `team.zurichbuchegg.contracts` by the builders of every lane it touches, lands as its own PR, and is merged before any lane depends on it. Field names below are the names in code.

## Who produces what, for whom

| Object | Produced by | Consumed by |
| --- | --- | --- |
| `PolicyDraft` | policy | app (display), engine (example purchases), runner (mandate creation) |
| `Mandate` | runner, after the app confirms | policy, engine, app |
| `Event` | runner (from the API, or from `scripts/replay.py`) | engine, extract, app |
| `PurchaseFacts` | extract | engine |
| `Decision` | engine | runner (submit), app (display) |
| `StepUp`, `StepUpAnswer` | runner and app | each other |

## PolicyDraft

```
draft_id            str, ours (uuid)
version             int, starts at 1; any material change is a new version
hash                str, sha256 of the canonical JSON of instruction + rules + uncertainty_policy
instruction         str, the cardholder sentence, verbatim
rules[]             Rule
examples[]          { description: str, expected: approve|decline|step_up, why: str }
open_questions[]    { question: str, options: [str], confirming_answers: [str], answer: str|null }
                    confirming_answers is the subset of options that confirms the rule as displayed; any other
                    answer leaves the draft unconfirmable and needs a revised draft. Stays in our store, never sent
                    to the simulator.
uncertainty_policy  ask | decline | approve
created_at          datetime
```

`Rule` is the simulator's rule plus two fields of ours:

```
field         str, from the vocabulary below
operator      < | <= | = | != | > | >= | in | not_in
value         number | str | [str]          (never bool, null, object, or [number])
currency      CHF | EUR | GBP | USD | absent
scope         purchase | period | absent
period_days   int >= 1 | absent
source_text   str, the phrase in the instruction this rule came from   (ours)
plain_english str, one sentence for the confirmation screen             (ours)
```

Simulator payload for `POST /v1/mandates`: `instruction`, `hard_rules` (each rule without `source_text` and `plain_english`), `uncertainty_policy`, `guidance: []`, `open_questions: []`. Only fields the API accepts go out; `source_text` and `plain_english` stay in our store.

## Rule field vocabulary

The engine resolves these and nothing else. A draft that references another field fails validation.

| Field | Type | Source |
| --- | --- | --- |
| `authorization.billing_amount_chf` | number | event |
| `authorization.items_subtotal` | number | event |
| `authorization.delivery_fee` | number | event |
| `authorization.currency` | str | event |
| `authorization.channel` | str | event |
| `authorization.fulfillment_method` | str | event |
| `authorization.order_returnable` | str | event |
| `authorization.merchant.merchant_id` | str | event |
| `authorization.merchant.merchant_category` | str | event |
| `authorization.merchant.merchant_mcc` | str | event |
| `authorization.merchant.merchant_country` | str | event |
| `items.category` | str, checked for every cart line | event |
| `items.count` | number | derived |
| `facts.product_type` | str | extract |
| `facts.size` | str | extract |
| `facts.return_days` | number | extract |
| `facts.is_gift_card`, `facts.is_subscription`, `facts.is_protection_plan`, `facts.is_addon` | "true" / "false" as strings (rule values cannot be booleans) | extract |
| `history.merchant_seen_on_card` | "true" / "false" | `authorization_history.csv` |
| `history.device_seen_on_card` | "true" / "false" | `authorization_history.csv` |
| `state.approvals_count` | number | engine state |

`scope: period` with `period_days: N` on a numeric field compares the sum of accepted approvals in the trailing N days (simulated timestamps) plus this purchase. A field whose value is unknown for this purchase makes the rule `uncertain`, never `pass`.

## Mandate

```
mandate_id     str, from the simulator's confirm response
draft_id       str
version        int
hash           str
status         active | superseded | revoked | expired
confirmed_at   datetime
```

## Event

Mirror of `viseca-2026/data/schemas/authorization_event.schema.json`, validated strictly. The top level is `type`, `request_id`, `deadline_at`, `authorization`, `mandate`, `context`, `runtime`. `authorization.items[]` carries `item_details`, which is untrusted text.

## PurchaseFacts

One per cart line. This is the form the shopping agent fills when it calls `buy`; the backend checks it deterministically. In demo mode the simulator does not send the form, so `leash.extract.extract_event` fills it from the event's structured item fields and a deterministic parse of `item_details`. No model reads merchant text or fills the form on the backend's behalf. Every field may be `unknown`.

```
item_id                str
product_type           str | unknown
size                   str | unknown
return_days            int | unknown
is_addon               bool | unknown
is_gift_card           bool | unknown
is_subscription        bool | unknown
is_protection_plan     bool | unknown
matches_request        bool | unknown
contains_instructions  bool
excerpt                str | null          (the injected text, if any)
sources                { field_name: agent_form | structured | merchant_text }
```

## MandateState

```
mandate_id            str
approvals[]           { authorization_id, merchant_id, amount_chf, timestamp (simulated) }
handled               { authorization_id: accepted Decision }
pending_step_ups      [authorization_id]
declined              [authorization_id]
```

`record(mandate_id, event, accepted)` is idempotent: the same authorization with the same accepted decision changes nothing. Only a Decision the API accepted with `approve` moves `approvals`, taking `billing_amount_chf`, `merchant_id` and the simulated `timestamp` from the event. A `step_up` stays pending until `/resolve` is accepted; the runner then records the final `approve` or `decline` with the same `authorization_id`, which is the one change allowed after a first record. Any other change to a recorded authorization raises. The runner calls `record` only after the API accepted the submit or `/resolve`. `record` does no simulator I/O; it writes `data/state/<mandate_id>.json`, and the engine is its only writer.

## Check and Decision

```
Check
  name     str, from the check list in plan 02
  result   pass | fail | uncertain
  value    str | number | null
  source   event | history | agent_form | merchant_text | state
  note     str

Decision
  authorization_id   str
  decision           approve | decline | step_up
  reason_codes[]     str, from the list below
  customer_message   str, one or two sentences, for the app and the API
  evidence[]         Check
  explanation        str, one paragraph for the judge panel
  engine_version     str
  mandate_version    int
  elapsed_ms         int
  decided_at         datetime
```

## Reason codes

`within_policy`, `amount_over_limit`, `period_limit_exceeded`, `purchase_count_exceeded`, `mandate_expired`, `mandate_revoked`, `item_mismatch`, `unrequested_item`, `return_terms_missing`, `return_terms_short`, `merchant_type_mismatch`, `unfamiliar_merchant`, `lookalike_merchant`, `gift_card`, `subscription`, `protection_plan`, `duplicate_order`, `requote_after_decline`, `velocity`, `new_device`, `country_blocked`, `injected_instructions`, `customer_confirmation`, `customer_declined`, `step_up_timeout`, `engine_timeout`.

Add a code by PR to this file.

## StepUp and StepUpAnswer

```
StepUp
  authorization_id   str
  decision           Decision (the step_up)
  event              Event
  expires_at         datetime, real clock, from the run's human window

StepUpAnswer
  authorization_id   str
  decision           approve | decline
  customer_message   str
  answered_at        datetime
```

## Engine entry points

```
leash.engine.evaluate(event: Event, policy: PolicyDraft, state: MandateState,
                      facts: list[PurchaseFacts] | None) -> Decision      # pure, no I/O
leash.engine.state.load(mandate_id) -> MandateState
leash.engine.state.record(mandate_id: str, event: Event, accepted: Decision) -> MandateState   # idempotent, returns the saved state
```

`facts=None` means the extract lane did not answer in time; every `facts.*` field is then unknown.

## Runner mandate client

Owned by the runner lane. Called by the policy lane's confirm route and the app's tighten and revoke routes. Every method calls the simulator once and raises `leash.runner.api.ApiError(status, body)` on any non-2xx; there is no retry inside these methods and no fallback.

```
leash.runner.mandates.create(draft: PolicyDraft) -> str                       # POST /v1/mandates, returns the simulator draft_id
leash.runner.mandates.confirm(simulator_draft_id: str) -> str                 # POST /v1/mandates/{draft_id}/confirm with {"confirmed": true}, returns mandate_id
leash.runner.mandates.get(mandate_id: str) -> dict                            # GET /v1/mandates/{mandate_id}, the raw stored mandate
leash.runner.mandates.tighten(mandate_id: str, patch: dict) -> dict           # PATCH /v1/mandates/{mandate_id}
leash.runner.mandates.revoke(mandate_id: str) -> None                         # DELETE /v1/mandates/{mandate_id}
```

`create` builds the simulator payload from the draft as described under PolicyDraft above (no `source_text`, no `plain_english`). The policy lane's confirm route calls `create` then `confirm`, and stores the returned `mandate_id` on our `Mandate`. Our `draft_id` and the simulator's `draft_id` are different values; the store keeps both.

## Backend HTTP for the app

Served by `leash.api`. Paths and shapes are what the app lane codes against.

| Method and path | Body / returns |
| --- | --- |
| `POST /session` | `{ username: str }` with 1 to 80 non-whitespace characters → `{ username }` and an HttpOnly `leash_session` cookie for the local demo login |
| `GET /session` | `{ username }` for the current cookie, or 401 if no valid session exists |
| `DELETE /session` | 204 and clears the current cookie, or 401 if no valid session exists |
| `GET /drafts/{draft_id}` | `PolicyDraft` |
| `POST /drafts/{draft_id}/confirm` | `{ version, hash, answers: { question: answer } }` → `Mandate`, or 409 on hash or version mismatch |
| `POST /drafts/{draft_id}/reject` | `{ version, hash, reason }` → 204, or 409 on hash or version mismatch |
| `GET /mandates/{mandate_id}` | `{ mandate: Mandate, draft: PolicyDraft, effective_policy: { rules: [Rule], uncertainty_policy }, state: MandateState }`. `draft` is the confirmed draft and never changes; `effective_policy` is what the simulator holds now, read back after a tighten |
| `POST /mandates/{mandate_id}/tighten` | `{ rules: [Rule] }` appends to the rule list, or `{ uncertainty_policy: "decline" }`; existing rules are never removed or replaced (the simulator's PATCH rules) → `Mandate` |
| `POST /mandates/{mandate_id}/revoke` | → `Mandate` (DELETE on the simulator) |
| `GET /mandates/{mandate_id}/decisions` | `[{ decision: Decision, state_after: MandateState }]`, oldest first |
| `GET /step-ups/pending` | `[StepUp]` |
| `POST /step-ups/{authorization_id}/answer` | `StepUpAnswer` → accepted result |
| `GET /decisions/{authorization_id}` | `Decision` + `Event` + state before and after |

All customer routes except `POST /session` require a valid local session cookie and return 401 without one. The demo login identifies a customer by username without a password. Confirmation, tightening, revocation and step-up answers are only reachable through these authenticated app routes. None of them is an MCP tool.
