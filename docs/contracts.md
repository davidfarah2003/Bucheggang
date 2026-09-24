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
open_questions[]    { question: str, options: [str], answer: str|null }
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
status         active | revoked | expired
confirmed_at   datetime
```

## Event

Mirror of `viseca-2026/data/schemas/authorization_event.schema.json`, validated strictly. The top level is `type`, `request_id`, `deadline_at`, `authorization`, `mandate`, `context`, `runtime`. `authorization.items[]` carries `item_details`, which is untrusted text.

## PurchaseFacts

One per cart line. Every field may be `unknown`.

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
sources                { field_name: structured | merchant_text | model }
```

## MandateState

```
mandate_id            str
approvals[]           { authorization_id, amount_chf, timestamp (simulated) }
handled               { authorization_id: accepted Decision }
pending_step_ups      [authorization_id]
declined              [authorization_id]
```

`record(mandate_id, authorization_id, accepted)` is idempotent. Only a Decision the API accepted with `approve` moves `approvals`. A `step_up` stays pending until `/resolve` is accepted.

## Check and Decision

```
Check
  name     str, from the check list in plan 02
  result   pass | fail | uncertain
  value    str | number | null
  source   event | history | merchant_text | model | state
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
leash.engine.state.record(mandate_id, authorization_id, accepted: Decision) -> None   # idempotent
```

`facts=None` means the extract lane did not answer in time; every `facts.*` field is then unknown.

## Backend HTTP for the app

Served by `leash.api`. Paths and shapes are what the app lane codes against.

| Method and path | Body / returns |
| --- | --- |
| `GET /drafts/{draft_id}` | `PolicyDraft` |
| `POST /drafts/{draft_id}/confirm` | `{ version, hash, answers: { question: answer } }` → `Mandate`, or 409 on hash or version mismatch |
| `POST /drafts/{draft_id}/reject` | `{ reason }` → 204 |
| `GET /mandates/{mandate_id}` | `Mandate` + `PolicyDraft` |
| `POST /mandates/{mandate_id}/tighten` | `{ rules: [Rule] }` or `{ uncertainty_policy }` → `Mandate` (PATCH on the simulator) |
| `POST /mandates/{mandate_id}/revoke` | → `Mandate` (DELETE on the simulator) |
| `GET /mandates/{mandate_id}/decisions` | `[Decision]` with the state after each |
| `GET /step-ups/pending` | `[StepUp]` |
| `POST /step-ups/{authorization_id}/answer` | `StepUpAnswer` → accepted result |
| `GET /decisions/{authorization_id}` | `Decision` + `Event` + state before and after |

Confirmation, tightening, revocation and step-up answers are only reachable through these authenticated app routes. None of them is an MCP tool.
