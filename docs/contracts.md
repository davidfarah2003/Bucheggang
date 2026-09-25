# Contracts between lanes

The executable versions are the pydantic models in `src/leash/contracts/`, owned by the engine lane. A change to this file or that package is agreed on `team.zurichbuchegg.contracts` by the builders of every lane it touches, lands as its own PR, and is merged before any lane depends on it. Field names below are the names in code.

## Who produces what, for whom

| Object | Produced by | Consumed by |
| --- | --- | --- |
| `PolicyDraft` | policy | app (display), engine (rules), runner (mandate creation) |
| `Mandate` | runner, after the app confirms | policy, engine, app |
| `Event` | runner (from the API, or from `scripts/replay.py`) | engine, extract, app |
| `PurchaseFacts` | extract | engine |
| `AssessmentBundle` | classifier, before evaluation | engine (pure composition); model-enabled release held |
| `Decision` | engine | runner (submit), app (display) |
| `StepUp`, `StepUpAnswer` | runner and app | each other |

## PolicyDraft

```
draft_id            str, ours (uuid)
version             int, starts at 1; any material change is a new version
hash                str, sha256 of the canonical JSON named by hash_version (below)
hash_version        1 | 2, default 1
instruction         str, the cardholder sentence, verbatim
rules[]             Rule
examples[]          { description: str, expected: approve|decline|step_up, why: str }   display only, agent-authored
boundary_cases[]    BoundaryCase, default []; present only with hash_version 2
open_questions[]    { question: str, options: [str], confirming_answers: [str], answer: str|null }
                    confirming_answers is the subset of options that confirms the rule as displayed; any other
                    answer leaves the draft unconfirmable and needs a revised draft. Stays in our store, never sent
                    to the simulator.
uncertainty_policy  ask | decline | approve
created_at          datetime
created_for         str, the account_id of the agent that proposed it; immutable, not in the hash,
                    never sent to the simulator (section "Identity source")
```

Hash versions. Version 1 hashes the compact sorted-key JSON of `{instruction, rules, uncertainty_policy}` and stays byte-for-byte what it is today; every existing draft keeps its hash. Version 2 hashes `{hash_version: 2, instruction, rules, uncertainty_policy, boundary_cases}` in the same canonical form (`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`), with each case serialized by `model_dump(mode="json")`. No evaluator version goes into the hash. A draft with `boundary_cases` must carry `hash_version: 2`; `hash_version: 2` with no case is invalid. A revision that removes every case moves the draft to `hash_version: 1` with a new version and a version 1 hash.

`BoundaryCase` is an authored purchase the draft must decide as `expected`. Every input is complete and explicit; nothing is read from the packaged data:

```
description   str
expected      approve | decline | step_up
why           str
event         Event, strict, complete
facts[]       PurchaseFacts, exactly one per event item
state         MandateState for event.mandate.mandate_id
history       History, a frozen slice, every row on event.authorization.card_id and before its timestamp
```

`History` is `{ authorizations: [HistoryAuthorization] }`, and `HistoryAuthorization` is the subset of an `authorization_history.csv` row the engine reads: `authorization_id, card_id, timestamp, transaction_type, status, merchant_id, merchant_name, merchant_country, customer_device_id (str|null)`. Duplicate `authorization_id`s raise. Only rows with `status: approved` and `transaction_type: purchase` count as familiarity; every row counts toward card history.

The policy store evaluates each case with `evaluate(case.event, candidate, case.state, case.facts, history=case.history)` at proposal, at revision and again at confirmation before any simulator call, and raises `InvalidDraft` naming the case when the observed outcome differs from `expected`. The confirmation persists the observed outcome, the case-input hash, the policy version and the engine version. `examples[]` are unchanged and remain agent claims the Wallet shows as such; the app shows computed outcomes separately from them. Cases stay in our store and are never sent to the simulator.

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
conflicts[]            { field: str, kind: merchant_text_contradiction | catalogue_event_mismatch }, default []
```

`conflicts` marks a fact that two observations of the same line disagree on. `merchant_text_contradiction`: the merchant copy states the fact twice with different values ("No returns. Returns accepted within 30 days.", two sizes). `catalogue_event_mismatch`: the local catalogue and the event's structured item fields disagree on name or category. The extractor never picks a side: the field is `unknown`, has no entry in `sources`, and appears once in `conflicts`; a value or a source on a conflicting field is a validation error. Silence is never a conflict. A conflict is not a `matches_request: false`; that stays reserved for a mismatch between two independently trusted typed identities.

The engine reports a conflict-affected check as `uncertain`, never `pass`, with reason code `fact_conflict` alongside the check's own code. Under `uncertainty_policy: approve` such a check resolves to `step_up`, never `approve`; under `ask` to `step_up`; under `decline` to `decline`. A conflict never upgrades merchant text to a trusted source and never clears an injection flag.

## MandateState

```
mandate_id            str
approvals[]           { authorization_id, merchant_id, amount_chf, timestamp (simulated) }
handled               { authorization_id: accepted Decision }
pending_step_ups      [authorization_id]
declined              [authorization_id]
customer_approvals[]  { authorization_id, mandate_id, amount_chf, timestamp (simulated) }   derived, never saved
```

`customer_approvals` holds the customer's accepted approvals on other mandates. `leash.engine.state.load(mandate_id, customer_mandates=())` fills it from the state files of the mandates named in `customer_mandates` (the caller passes the customer's confirmed mandate ids from the policy store's confirmations; the default is none, which is the behaviour before this field). A period rule on `authorization.billing_amount_chf` or `state.approvals_count` counts this mandate's approvals plus `customer_approvals` in its window, so a daily or trailing-30-day limit survives supersession; an approval under a superseded or revoked mandate still counts. A rule without `scope: period` stays per mandate. An authorization approved on two mandates raises `StateConflict`. `record` and `_save` drop the list; the file holds only the mandate's own state.

`record(mandate_id, event, accepted)` is idempotent: the same authorization with the same accepted decision changes nothing. Only a Decision the API accepted with `approve` moves `approvals`, taking `billing_amount_chf`, `merchant_id` and the simulated `timestamp` from the event. A `step_up` stays pending until `/resolve` is accepted; the runner then records the final `approve` or `decline` with the same `authorization_id`, which is the one change allowed after a first record. Any other change to a recorded authorization raises. The runner calls `record` only after the API accepted the submit or `/resolve`. `record` does no simulator I/O; it writes `data/state/<mandate_id>.json`, and the engine is its only writer.

## Check and Decision

```
Check
  name     str, from the check list in plan 02
  result   pass | fail | uncertain
  value    str | number | null
  source   event | history | agent_form | merchant_text | state | model
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

`within_policy`, `amount_over_limit`, `period_limit_exceeded`, `purchase_count_exceeded`, `mandate_expired`, `mandate_revoked`, `item_mismatch`, `unrequested_item`, `return_terms_missing`, `return_terms_short`, `merchant_type_mismatch`, `unfamiliar_merchant`, `lookalike_merchant`, `gift_card`, `subscription`, `protection_plan`, `duplicate_order`, `requote_after_decline`, `velocity`, `new_device`, `country_blocked`, `country_unfamiliar`, `no_card_history`, `injected_instructions`, `customer_confirmation`, `customer_declined`, `step_up_timeout`, `engine_timeout`, `model_history_uncertain`, `fact_conflict`.

`fact_conflict` accompanies the uncertain check on a line whose `PurchaseFacts.conflicts` names the field the check reads (section "PurchaseFacts").

`country_blocked` comes only from a failed customer rule on `authorization.merchant.merchant_country`. `country_unfamiliar` is the uncertain result of the built-in country check, for a card with history but none in that country. `no_card_history` is one uncertain result for a card with no row in `authorization_history.csv` before the purchase and no approval recorded on the mandate: device, merchant and country familiarity are unknown, and `new_device`, `unfamiliar_merchant` and `country_unfamiliar` are not reported for it.

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

## Classifier assessments

P1/P2 adds these shared types in `leash.contracts.classifier`. They describe successful history processing and model calls. The pure evaluator never calls a model or reads a data file.

```
HistoryFeatures
  schema_version       hist-1
  customer_id, card_id  str, lookup identity only
  as_of                timezone-aware simulated purchase time
  values               { feature name: finite number | null }
  missing              { undefined feature name: nonempty reason }
  support              { feature name: nonnegative integer }

BehaviorAssessment
  score                finite historical-decline probability in [0, 1]
  model_id             nonempty configured model name
  artifact_version     lowercase SHA-256 of the scored artifact
  feature_schema_version  same version as HistoryFeatures
  support              { name: nonnegative integer }
  escalation_fired     bool, set only by a separately approved operating rule

JevAnswer
  question_id          spend_pattern | activity_pattern
  options              { ordinary: probability, unusual: probability, unclear: probability }
  selected             ordinary | unusual | unclear | null on an exact top tie

SemanticAssessment
  requested_model, served_model  equal nonempty identifiers
  prompt_version       nonempty version
  answers              exactly one JevAnswer for each history question
  latency_ms           nonnegative integer

AssessmentBundle
  authorization_id     str
  purchase_digest      lowercase SHA-256
  policy_hash          lowercase SHA-256 of the effective policy
  as_of                same time as HistoryFeatures and the authorization
  features             HistoryFeatures
  behaviour            BehaviorAssessment | null
  semantic             SemanticAssessment | null
```

Support keys cover every feature. Missing reasons cover exactly the null-valued features. Probability values are finite, within [0, 1], and sum to one within 1e-6. A unique maximum must equal `selected`; a tie requires null. Malformed distributions, duplicate questions, schema mismatches and stale bindings raise. The Jev adapter separately rejects duplicate raw JSON keys and a provider choice that disagrees with its probability argmax.

`assessment_purchase_digest(event, features)` hashes canonical sorted JSON containing the complete authorization, mandate ID, customer ID, card ID and `features.model_dump(mode="json")`, using compact separators and rejecting non-finite values. The digest binds the full feature values, missingness and support metadata as well as the purchase. Producers must use the shared helper. The evaluator revalidates mutable assessment objects and compares the authorization, digest, policy hash, event time, mandate identity and feature identity before composing a decision. A supplied bundle must use the shared type, rather than a lookalike private model. It contains no mandate-state-derived model features; deterministic checks still receive the current `MandateState`. Atomic state/policy rechecks and mutation intents remain separate runner release gates.

Each model check has `source=model` and only `pass` or `uncertain`. Its `value` is deterministic JSON preserving the score or distribution and model/artifact/prompt versions; `note` is readable text. `model_history_uncertain` identifies an uncertain model check. A model pass cannot satisfy or remove an unknown required fact, clear an injection flag or overturn a deterministic failure. Uncertainty follows the existing effective policy, including its approve/ask/decline choices.

These history-only questions do not permit catalogue fields, merchant text or agent justifications. `line_no` and evidence-satisfaction changes remain deferred. No model-enabled caller, trained artifact or operational threshold is enabled by this contract change. The model-enabled merge/release hold remains in force.

## Engine entry points

```
leash.engine.evaluate(event: Event, policy: PolicyDraft, state: MandateState,
                      facts: list[PurchaseFacts] | None,
                      assessments: AssessmentBundle | None = None,
                      history: History | None = None) -> Decision  # pure, no I/O
leash.engine.state.load(mandate_id, customer_mandates=()) -> MandateState   # customer_approvals filled from the named mandates
leash.engine.state.record(mandate_id: str, event: Event, accepted: Decision) -> MandateState   # idempotent, returns the saved state
```

`assessments=None` is the model-off startup configuration. A history-only bundle with both model outputs null adds no model checks. Neither form may substitute for a failed required assessment: a failure raises before evaluation. The startup caller must enforce which successful outputs its configuration requires.

`history=None` keeps the packaged `authorization_history.csv` files as the familiarity source, which is what every current caller gets. An explicit `History` replaces them entirely for that call: familiarity, card history and `no_card_history` are computed from its rows alone, with the same before-timestamp rule. The boundary-case check in the policy store is the first caller; the runner keeps `None`.

`facts=None` leaves every `facts.*` field unknown for legacy callers. An extraction execution failure must raise. The current runner's timeout substitute decisions remain separate P4 work and are a blocker for the model-enabled path; this interface change does not claim to have removed them.

## Runner coordination

`leash.runner.records.customer_lock(customer)` guards enumeration of a customer's owned mandates. Its file is `data/locks/customer/<sha256 of customer>.lock`. `mandate_locks(ids, deadline_at=...)` nests inside it and acquires the sorted unique mandate IDs. An empty set is valid for a customer's first confirmation. Mutation callers hold the customer guard and mandate locks through the accepted write and local persistence, then release in reverse order. They re-read the confirmation set after locking and raise if it changed. Never acquire the customer guard while holding a mandate lock.

`customer_lock` accepts an optional monotonic `stop_at`. `mandate_locks` requires an aware absolute `deadline_at` and can share that `stop_at`. The runner uses one remaining budget across both lock levels. Immutable confirmation metadata may be read first solely to identify the customer; owned-set enumeration and financial-state reads happen inside coordination.

The runner stores durable mutation intents under `data/intents/`, including its persistent pre-dispatch state and separate customer-wide evaluation snapshot. An unresolved intent blocks new dispatch until authoritative read-back and local recovery finish. Models are not enabled by this coordination interface. Policy confirmation must adopt the same helper after this change merges; until that follow-up, confirmation/supersession is not covered by the shared ordering.

## Runner mandate client

Owned by the runner lane. Called by the policy lane's confirm route and the app's tighten and revoke routes. Every method calls the simulator once and raises `leash.runner.api.ApiError(status, body)` on any non-2xx; there is no retry inside these methods and no fallback.

```
leash.runner.mandates.create(draft: PolicyDraft, global_rules: [Rule]) -> str # POST /v1/mandates, returns the simulator draft_id
leash.runner.mandates.confirm(simulator_draft_id: str) -> str                 # POST /v1/mandates/{draft_id}/confirm with {"confirmed": true}, returns mandate_id
leash.runner.mandates.get(mandate_id: str) -> dict                            # GET /v1/mandates/{mandate_id}, the raw stored mandate
leash.runner.mandates.tighten(mandate_id: str, patch: dict) -> dict           # PATCH /v1/mandates/{mandate_id}
leash.runner.mandates.revoke(mandate_id: str) -> None                         # DELETE /v1/mandates/{mandate_id}
```

`create` builds the simulator payload from `global_rules + draft.rules` (no `source_text`, no `plain_english`). The policy lane reads one global policy snapshot for the authenticated customer at confirmation, calls `create` then `confirm`, and stores the returned `mandate_id` and exact global policy version, hash and rules on the confirmation record. Our `draft_id` and the simulator's `draft_id` are different values; the store keeps both.

## Backend HTTP for the app

Served by `leash.api`. Paths and shapes are what the app lane codes against.

| Method and path | Body / returns |
| --- | --- |
| `POST /account` | `{ username: str, password: str }` → 201 `{ account_id, username }` and a session cookie. Username 1 to 80 non-whitespace characters, unique, created exclusively (`O_EXCL`); a taken username is 409. Password 8 to 256 characters. |
| `POST /session` | `{ username: str, password: str }` → `{ account_id, username }` and a new HttpOnly `leash_session` cookie. Unknown username and wrong password both return 401 `"username or password is wrong"`. After 5 failures on one account within 60 s, login for that account returns 429 until 60 s have passed. |
| `GET /session` | `{ account_id, username }` for the current cookie, or 401 if no valid session exists |
| `DELETE /session` | 204, deletes the session record and clears the cookie, or 401 if no valid session exists |
| `GET /pairing/{code}` | `{ agent_label, scopes: [str], expires_at }` for a begun, unexpired pairing code, else 404. Requires a session. |
| `POST /pairing/{code}/approve` | → 204. Binds the pairing to the session's `account_id`; 404 for an unknown, expired or already approved code. Requires a session. |
| `GET /agents` | `[{ agent_id, agent_label, scopes, created_at, last_used_at, revoked_at }]` for the session's account, newest first |
| `POST /agents/{agent_id}/revoke` | → the agent record with `revoked_at` set; 404 if the agent is not the account's. Idempotent. |
| `GET /drafts?state=pending|confirmed|rejected|all` | Defaults to `all`; returns the summaries `{ draft_id, version, hash, state: proposed|confirming|confirmed|rejected, instruction, plain_english: [str], uncertainty_policy, open_questions: int, created_at, mandate_id: str|null }` of every draft whose `created_for` is the session's `account_id`, so a bound draft is listed from the moment the agent proposes it, in state `proposed`. `state=pending` returns `proposed` and `confirming` drafts. Every draft has an owner; there is no link-only access. Newest first. |
| `GET /global-policy` | `{ customer, version, hash, rules: [Rule], updated_at }`; missing policy is 200 with version 0, empty rules, their canonical SHA-256 and `updated_at: null` |
| `PUT /global-policy` | `{ expected_version, expected_hash, rules: [Rule] }` replaces the full list and returns the new record; 409 for a stale version or hash, or if the customer-owned mandate set changes while its locks are acquired; 422 for invalid rules or duplicate controls; 503 if lock acquisition times out. `plain_english` may be omitted and is generated by the server; `source_text` is the caller label. |
| `GET /drafts/{draft_id}` | `PolicyDraft` |
| `GET /drafts/{draft_id}/boundary-results` | Customer-owned computed outcomes of the draft's `boundary_cases`: `{ draft_id, version, hash, evaluated_at, phase: proposal|revision|confirmation, engine_version, results: [{ case_index, description, expected, observed, reason_codes, case_input_hash }] }`. `case_index` is zero-based, unique and contiguous in authored order; `results` has exactly one entry per current case, and `version`, `hash` and each `expected` match `GET /drafts/{draft_id}`. 404 for another account's draft; a `hash_version` 1 draft is 200 with `results: []`. Results live next to the draft, outside the hashed payload; proposal and revision regenerate the whole list, and confirmation replaces it with the confirmation-phase evaluation before any simulator call. Results whose evaluation predates the draft's current hash give 409 with detail `boundary results are stale`; the server never re-evaluates on read. The app shows them as computed outcomes on authored synthetic inputs, apart from `examples[]` and live purchase evidence. |
| `POST /drafts/{draft_id}/confirm` | `{ version, hash, answers: { question: answer } }` → `Mandate`, or 409 on hash or version mismatch, or if the customer-owned mandate set changes while its locks are acquired; 503 if lock acquisition times out |
| `POST /drafts/{draft_id}/reject` | `{ version, hash, reason }` → 204, or 409 on hash or version mismatch or if the customer-owned mandate set changes while its locks are acquired; 503 if lock acquisition times out |
| `GET /mandates?status=active|superseded|revoked|expired|all` | Defaults to `all`; returns customer-owned mandate summaries `{ mandate_id, draft_id, version, hash, status, confirmed_at, instruction, approvals_count, pending_step_ups, global_policy_version, global_policy_hash }`, newest first. Status is read from the simulator; a simulator error is returned to the caller. |
| `GET /mandates/{mandate_id}` | `{ mandate: Mandate, draft: PolicyDraft, effective_policy: { rules: [Rule], uncertainty_policy }, state: MandateState, global_policy_version, global_policy_hash }`. `draft` is the confirmed draft and never changes; `effective_policy` is what the simulator holds now, read back after a tighten. The global policy metadata is from the confirmation snapshot; edits apply to later confirmations. |
| `POST /mandates/{mandate_id}/tighten` | `{ rules: [Rule] }` appends to the rule list, or `{ uncertainty_policy: "decline" }`; existing rules are never removed or replaced (the simulator's PATCH rules) → `Mandate` |
| `POST /mandates/{mandate_id}/revoke` | → `Mandate` (DELETE on the simulator) |
| `GET /mandates/{mandate_id}/decisions` | `[{ decision: Decision, state_after: MandateState }]`, oldest first |
| `GET /step-ups/pending` | `[StepUp]` |
| `POST /step-ups/{authorization_id}/answer` | `StepUpAnswer` → accepted result |
| `GET /decisions/{authorization_id}` | `Decision` + `Event` + state before and after |

All customer routes except `POST /account` and `POST /session` require a valid session cookie and return 401 without one. Every browser mutation, including `POST /account` and `POST /session` and every cookie-authenticated one (confirm, reject, answer, tighten, revoke, `PUT /global-policy`, pairing approve, agent revoke), requires an `Origin` header equal to `LEASH_APP_ORIGIN`, a configured value read at startup (the local demo sets `http://127.0.0.1:<port>`), never derived from the request's `Host`; a missing or different `Origin` is 403. The API sets no CORS headers. The Origin check runs before any session read; the middleware only tests that the cookie is present, and the route's session dependency performs the single session read and `last_seen_at` write. Confirmation, tightening, revocation and step-up answers are only reachable through these authenticated app routes. None of them is an MCP tool. The identity model behind these routes is in the section "Identity source" below.

## Harness link

The built-in Shopping Harness (plan 04, Later) and any external MCP agent hand the customer to the trusted Wallet for two moments only: confirming a proposed policy and answering a step-up. The link carries one server-persisted identifier and nothing else.

```
proposal   /app/?draft_id=<draft_id>              the draft the agent proposed, owned by the agent's account
purchase   /app/?authorization_id=<authorization_id>   the pending step-up the runner recorded
```

Entry. The Wallet resolves the identifier against the signed-in account. A draft whose `created_for` is another account, an unknown identifier, or a purchase that is not pending for one of the account's mandates is an error screen with an escape to Shop; nothing is created on entry. The agent never sends the policy text, the rules, or a customer answer over the link; the Wallet reads them from the store.

Return. The agent resumes only on backend state it can read back, never on the Wallet's say-so:

| Moment | Readback | Resume when |
| --- | --- | --- |
| proposal | `GET /drafts/{draft_id}` for content; the owned `GET /drafts?state=all` summary for `proposed`, `confirming`, `confirmed` or `rejected`; over MCP, `get_policy_status` | `confirmed` with a `mandate_id`. `rejected` gives the agent no authority and it stops. |
| purchase | `GET /step-ups/pending` while pending; `GET /decisions/{authorization_id}` for the latest accepted result; over MCP, `get_purchase_status` | the accepted result exists. A `decline`, a `step_up_timeout` or a `customer_declined` stops the purchase. |

Readback is a poll by the agent at its own cadence. There is no callback, no push event and no route that lets the agent set a state. The Harness runs in the customer's browser session and holds no agent token or provider key; the server-side adapter that turns its chat into MCP calls is the one process holding credentials, and that adapter is a later plan-04 decision recorded there before any code.

## Purchase over MCP

`buy` and `get_purchase_status` stay parked until this section is implemented under its own PR. When they land they do not integrate a payment processor. The contract is:

```
buy          paired agent token + confirmed mandate_id + final typed cart, merchant and all-in total
             -> Decision (approve | decline | step_up with authorization_id), the same evaluate the runner uses
step_up      resolved only in the Wallet, or times out to decline (section StepUp and StepUpAnswer)
outcome      get_purchase_status -> { authorization_id, decision, resolved, final,
                                      reference: { authorization_id, mandate_id, decision, decision_hash, expires_at } | null }
```

`reference` is present only for a final `approve` and is what an external processor consumes to take payment; the backend records no charge and makes no order claim. `decision_hash` is the SHA-256 of the canonical accepted `Decision`. A cart or total that differs from what the agent showed the customer is the agent's problem: the engine judges the typed values it receives, and `facts.*` rules apply to the `facts` the agent supplies with `sources[field] = agent_form`.

## Identity source

Ruled 2026-09-25 by the contracts owner on Oskar's direction. This replaces the earlier `LEASH_MCP_TOKENS` capability-map ruling and the shared `LEASH_MCP_TOKEN` bearer; neither ships. It is a local credential system for the demo, and the section ends with what a bank integration replaces.

The customer identifier used everywhere (`customer` in ownership records, `created_for` on drafts, `customer_lock`) is the `account_id`: 16 random bytes, hex, assigned at registration. Usernames are for login only and are never used as the ownership key. Local demo data written before this change is discarded; there is no migration.

Store. Everything lives under `LEASH_POLICY_STORE/identity/`, one JSON file per record, mode 0600, written to a temporary name and renamed, read and written under the existing flock helpers. Secrets are stored only as digests.

| Directory | Key | Record |
| --- | --- | --- |
| `accounts/` | `sha256(username)` | `{ account_id, username, password: "scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>", created_at, failed_logins: [timestamps within the last 60 s] }`. Registration writes the final file name with `O_EXCL`; the second of two simultaneous registrations of one username gets `FileExistsError` and answers 409. This is the one record that is not written by temporary name and rename. |
| `sessions/` | `sha256(cookie value)` | `{ account_id, created_at, last_seen_at }` |
| `pairings/` | `sha256(pairing_code)` | `{ verifier_digest: sha256(verifier), agent_label, scopes, status: begun \| approved \| consumed, account_id: str \| null, created_at, expires_at }` |
| `agents/` | `sha256(agent_token)` | `{ agent_id, account_id, agent_label, scopes, created_at, last_used_at, revoked_at: datetime \| null }` |

Passwords. `hashlib.scrypt` from the standard library, `n=2**14, r=8, p=1, dklen=32`, a fresh 16-byte salt per account. No new dependency; argon2 is a later swap of the prefix and stays out of the demo. Comparison uses `hmac.compare_digest`. A login failure records a timestamp on the account; five within 60 s make further attempts 429 until the oldest is older than 60 s. A login for an unknown username runs scrypt against a fixed dummy record so it takes as long as a wrong password, and unknown-username failures are counted in one process-wide window with the same limit. Both limits answer 429 with the same body, and the 401 body is the same for unknown name and wrong password. Passwords, cookies, codes and tokens never appear in a log line, an error message, a URL other than the pairing link, or a browser storage API.

Sessions. The cookie value is 32 random bytes, URL-safe. Only its SHA-256 is stored. A session expires after 12 hours idle or 24 hours absolute, measured from the record; an expired session is 401 and its file is removed on the failed read. Every login writes a new session; logout deletes the record. Cookie flags: `HttpOnly`, `SameSite=Strict`, `Path=/`. The Wallet API is served on 127.0.0.1 and never through the tunnel, so `Secure` is not set; a deployment that serves HTTPS sets it.

Pairing. `begin_pairing` creates two secrets: a pairing code of 16 random bytes (128 bits) that travels in the link, and a verifier of 32 random bytes (256 bits) that stays with the agent. It stores the code's digest, the verifier's digest, the agent label and the fixed scope set, valid for 5 minutes. The customer opens the link while logged in; the Wallet shows the label, the scopes and the expiry and offers Approve. Approval writes `account_id` and `status: approved` under the file lock. `complete_pairing` takes the code and the verifier, reads the record under the lock, requires `status: approved`, an unexpired record and `sha256(verifier)` equal to the stored digest by constant-time comparison, then, still under the lock, first rewrites the pairing file with `status: consumed` and then writes the agent record with a token of 32 random bytes (256 bits). A crash between the two writes leaves a consumed pairing and no agent: the next `complete_pairing` raises `PairingUnknown` and the agent begins a fresh pairing. A code is therefore completed at most once and no second credential is ever minted for it. The token is returned once, in the tool result over the transport, and is never stored in clear. A wrong verifier and an unknown, expired or consumed code all raise the same `PairingUnknown`; the API side returns 404 for the same states. Expired pairing files are deleted on every `begin_pairing`. Someone who sees the link can approve nothing without the customer's session and can complete nothing without the verifier; the code alone selects the pairing to show and is dead after five minutes or one use. The Wallet serves the pairing page with `Referrer-Policy: no-referrer` and the API never writes the code to a log.

Scopes are one fixed set for every paired agent: `policy:propose` (`propose_task_policy`) and `policy:read` (`get_policy_status`, `get_policy_summary`, `get_policy_authoring_instructions`). `buy` and `get_purchase_status` stay parked. The set is recorded on the agent record and displayed at approval so a later narrowing is a data change.

Token presentation. Streamable HTTP: `Authorization: Bearer <agent_token>` on every request. The ASGI middleware no longer rejects requests; it reads the header into the request context. Each tool that needs a principal computes `sha256(token)` and reads exactly the file with that name in `agents/`; there is no scan and no comparison against a list. A missing file, a file that fails to parse, a record whose `account_id` is empty, or `revoked_at` set all raise the same `Unauthorized`; a valid record has `last_used_at` updated. Two agents can never share a digest because the token is 256 random bits, and a collision on write is refused (`O_EXCL`) and raises. Stdio: the process serves one agent; it reads `LEASH_AGENT_TOKEN` from its environment at startup if set, and otherwise holds the token returned by its own `complete_pairing` in memory for the rest of the process. The client helper in `docs/mcp-client.md` sends the token from `LEASH_AGENT_TOKEN`.

Ownership. `propose_task_policy` stores `created_for = account_id` of the presenting agent; the value is immutable, is not part of the draft hash and is not sent to the simulator. `get_policy_status` and `get_policy_summary` require the presenting agent's `account_id` to equal `created_for`, else raise as unknown. The app routes `GET /drafts/{id}`, confirm and reject require the session's `account_id` to equal `created_for`, else 404. Drafts have an owner from creation, so the legacy ownerless-draft rules become unreachable for new drafts and are deleted with the demo data. Revocation flips `revoked_at`; existing drafts and mandates of the account are untouched, the agent only loses the tools.

Locking. The confirm route and `PUT /global-policy` take `leash.runner.records.customer_lock(account_id)` first, as ruled for #58, then the mandate locks. Pairing approval and token consumption use the per-file flock only; they touch no mandate state.

Split. This section merges first. Then, in order: the policy lane builds `leash.api` accounts, sessions, pairing routes and the Origin check, and `leash.policy.mcp_server` pairing tools and per-tool authorization, in one PR; the app lane builds Register, Login, Pair and Agents screens against the table above in a second PR. The runner lane is not touched. Both PRs need the exact-head review from a different model family before merge.

Bank integration. In production the account store and the password check are replaced by the bank's identity provider: the session is established by the bank app's authenticated context or an OIDC login, `account_id` becomes the bank's stable customer subject, and pairing keeps the same shape (customer approves a labelled agent in the Wallet, the agent receives a scoped revocable token). Nothing in the engine, runner or contracts depends on how the session was obtained.

## MCP tools

Served by `leash.policy.mcp_server` over stdio or streamable HTTP, backed by the same `LEASH_POLICY_STORE` directory as `leash.api`. The two pairing tools are the only tools an unpaired agent can call; every other tool needs the agent token from the section "Identity source" and raises `Unauthorized("pair this agent in the Wallet first")` without one. This is the whole agent-facing surface (plan 01, steps 2 and 9 to 12). Every tool raises on bad input; nothing is defaulted. No tool confirms, resolves, tightens or revokes. `propose_task_policy` returns the full stored `PolicyDraft`, including the rules and hash the agent submitted. The read-only `get_policy_status` and `get_policy_summary` tools return no rule fields or hash.

| Tool | Input → returns |
| --- | --- |
| `begin_pairing` | `{ agent_label: str }` (1 to 80 characters, shown to the customer) → `{ pairing_code, verifier, expires_at, scopes }`. The agent hands the customer `/app/?pair=<pairing_code>` and keeps `verifier` to itself; it never appears in a link, a log or the Wallet. No token needed |
| `complete_pairing` | `{ pairing_code: str, verifier: str }` → `{ agent_token, agent_id, account_id, scopes }` exactly once, after the customer approved in the Wallet; before approval raises `PairingPending`; a wrong verifier, an unknown, consumed or expired code all raise the same `PairingUnknown`. No token needed |
| `get_policy_authoring_instructions` | `{ instruction: str }` → `{ guide, request_instructions }`; `guide` is the `policy://authoring-guide` resource (field vocabulary, rule format, proposal shape, restrictions) |
| `propose_task_policy` | `{ instruction: str, proposal: { rules: [Rule], examples: [...], open_questions: [...], uncertainty_policy } }` → the stored `PolicyDraft` (`draft_id`, `version: 1`, `hash`, the validated fields). Invalid proposal raises `InvalidDraft` with the reason. The agent then hands the customer `/app/?draft_id=<draft_id>` |
| `get_policy_status` | `{ draft_id: str }` → `{ draft_id, version, status: pending \| confirmed \| rejected, mandate_id: str \| null, confirmed_at: datetime \| null, rejected_reason: str \| null }`. `mandate_id` is set only when `status` is `confirmed`. Unknown draft raises |
| `get_policy_summary` | `{ draft_id: str }` → `{ draft_id, version, instruction, plain_english: [str], examples: [{ description, expected, why }], open_questions: [{ question, options, answer: str \| null }], uncertainty_policy }`. The sentences are the same ones the Wallet shows |
| `buy` | `{ mandate_id: str, cart: [{ item_id, item_name, item_category, item_details, unit_price_chf, quantity }], merchant: { merchant_id, merchant_name, merchant_category, merchant_mcc, merchant_country }, facts: [PurchaseFacts] }` → `Decision` (`approve`, `decline` or `step_up` with `authorization_id`). Parked for the submission: raises `NotImplementedError("purchases arrive through the simulator in demo mode; see plan 01 step 12")`. Scope when it lands: section "Purchase over MCP" |
| `get_purchase_status` | `{ authorization_id: str }` → `{ authorization_id, decision: Decision, resolved: bool, final: approve \| decline \| null }`; a `step_up` is `resolved: false` until the Wallet answers or it times out. Parked with `buy` |

`facts` in `buy` is the form the agent's own model fills; the backend checks it deterministically and records `sources[field] = agent_form` for every field the agent supplied. The agent never sends the policy; the backend reads the confirmed policy for `mandate_id` from its own store.
