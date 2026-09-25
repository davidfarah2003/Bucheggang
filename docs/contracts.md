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

`record(mandate_id, event, accepted)` is idempotent: the same authorization with the same accepted decision changes nothing. Only a Decision the API accepted with `approve` moves `approvals`, taking `billing_amount_chf`, `merchant_id` and the simulated `timestamp` from the event. A `step_up` stays pending until `/resolve` is accepted, or, for a local purchase (section "Purchase input and idempotency"), until the Wallet answers or the book times it out; the runner then records the final `approve` or `decline` with the same `authorization_id`, which is the one change allowed after a first record. Any other change to a recorded authorization raises. The runner calls `record` only after the API accepted the submit or `/resolve`. `record` does no simulator I/O; it writes `data/state/<mandate_id>.json`, and the engine is its only writer.

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

Support keys cover every feature. Missing reasons cover exactly the null-valued features. Probability values are finite, within [0, 1], and sum to one within 0.015, the drift three two-decimal provider values can carry; values are never renormalized. A unique maximum must equal `selected`; a tie requires null. Malformed distributions, duplicate questions, schema mismatches and stale bindings raise. The Jev adapter separately rejects duplicate raw JSON keys and a provider choice that disagrees with its probability argmax.

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
| `GET /pairings/pending` | Customer session. Pairings begun by an agent and not yet approved: `[{ pairing_id, agent_label, scopes, created_at, expires_at }]`. `pairing_id` is the digest-derived file id; the code itself is never listed |
| `POST /pairings/{pairing_id}/approve` | Customer session, exact Origin. Approves the pending pairing for the session's account; 204, or 404 when unknown, expired or already decided. The Wallet's Needs tab uses this for the Approve button on the connection card |
| `GET /pairing/{code}` | `{ agent_label, scopes: [str], expires_at }` for a begun, unexpired pairing code, else 404. Requires a session. |
| `POST /pairing/{code}/approve` | → 204. Binds the pairing to the session's `account_id`; 404 for an unknown, expired or already approved code. Requires a session. |
| `GET /agents` | `[{ agent_id, agent_label, scopes, created_at, last_used_at, revoked_at }]` for the session's account, newest first |
| `POST /agents/{agent_id}/revoke` | → the agent record with `revoked_at` set; 404 if the agent is not the account's. Idempotent. |
| `GET /drafts?state=pending|confirmed|rejected|all` | Defaults to `all`; returns the summaries `{ draft_id, version, hash, state: proposed|confirming|confirmed|rejected, instruction, plain_english: [str], uncertainty_policy, open_questions: int, created_at, mandate_id: str|null }` of every draft whose `created_for` is the session's `account_id`, so a bound draft is listed from the moment the agent proposes it, in state `proposed`. `state=pending` returns `proposed` and `confirming` drafts. Every draft has an owner; there is no link-only access. Newest first. |
| `GET /global-policy` | `{ customer, version, hash, rules: [Rule], updated_at }`; missing policy is 200 with version 0, empty rules, their canonical SHA-256 and `updated_at: null` |
| `PUT /global-policy` | `{ expected_version, expected_hash, rules: [Rule] }` replaces the full list and returns the new record; 409 for a stale version or hash, or if the customer-owned mandate set changes while its locks are acquired; 422 for invalid rules or duplicate controls; 503 if lock acquisition times out. `plain_english` may be omitted and is generated by the server; `source_text` is the caller label. |
| `GET /drafts/{draft_id}` | `PolicyDraft` |
| `GET /drafts/{draft_id}/boundary-results` | Customer-owned computed outcomes of the draft's `boundary_cases`: `{ draft_id, version, hash, evaluated_at, phase: proposal|revision|confirmation, engine_version, results: [{ case_index, description, expected, observed, reason_codes, case_input_hash }] }`. `case_index` is zero-based, unique and contiguous in authored order; `results` has exactly one entry per current case, and `version`, `hash` and each `expected` match `GET /drafts/{draft_id}`. 404 for another account's draft; a `hash_version` 1 draft is 200 with `results: []`. Results live next to the draft, outside the hashed payload; proposal and revision regenerate the whole list, and confirmation replaces it with the confirmation-phase evaluation before any simulator call. `case_input_hash` is SHA-256 of compact sorted-key JSON for `{event, facts, state, history}` from `model_dump(mode="json")`; description, expected and why are excluded. Results whose evaluation predates the draft's current hash give 409 with detail `boundary results are stale`; the server never re-evaluates on read. The app shows them as computed outcomes on authored synthetic inputs, apart from `examples[]` and live purchase evidence. |
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

LEASH_APP_ORIGIN must be the canonical `scheme://netloc`: an HTTP or HTTPS scheme, a valid DNS label set or IP literal, and an optional integer port from 1 to 65535. A trailing colon, backslash, control character, path, query, fragment or non-canonical spelling is rejected at startup by the shared Wallet API and MCP validator.

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

### Purchase input and idempotency

This subsection fixes what `buy` accepts, how the backend turns it into the `Event` the engine already judges, and what happens when the same purchase is sent twice. It is agreed before any `buy` code; the parked tool stays parked until an implementation PR cites it.

Authority. `buy` and `get_purchase_status` need the scope `purchase:decide`, which is not in the fixed set every pairing grants today. When this subsection is implemented, `begin_pairing` gains an optional `scopes` request limited to the known set, the Wallet's pairing screen shows the requested scopes and the customer approves exactly those, and the agent record carries them; a token without `purchase:decide` calling `buy` raises `Unauthorized("this agent is not paired for purchases")`. Existing tokens are never widened; an agent paired before this lands re-pairs to buy.

Simulator boundary. A purchase decided through `buy` is a local decision of this backend. It creates no simulator authorization, is never submitted to `POST /v1/authorizations/{id}/decision`, and appears in no simulator run or score. In demo mode the simulator originates every attempt, so `buy` stays parked for the submission; the `AGT` id prefix marks a local purchase wherever a decision is listed, and nothing keys behaviour on that prefix.

Input. `buy` takes exactly the fields in the MCP tool table and nothing else; unknown keys raise `InvalidPurchase` naming the key. Every value is typed and checked before the engine sees it:

```
mandate_id        str, confirmed for the paired agent's account_id, status active; otherwise InvalidPurchase
purchase_key      str, 16 to 64 characters, the agent's own idempotency key for this purchase attempt
cart[]            1 to 50 lines; item_id, item_name, item_category non-empty; quantity int >= 1;
                  unit_price_chf > 0 with at most 2 decimals; item_details str (untrusted merchant text, may be empty)
merchant          merchant_id, merchant_name, merchant_category, merchant_city non-empty; merchant_mcc 4 digits; merchant_country ISO 3166-1 alpha-2
delivery_fee_chf  >= 0, at most 2 decimals, default absent means the agent must send 0 explicitly
total_chf         > 0, at most 2 decimals; must equal sum(quantity * unit_price_chf) + delivery_fee_chf to the cent, else InvalidPurchase("total does not match the cart")
facts[]           one PurchaseFacts per cart line, same item_id in the same order; sources[field] must be agent_form for every supplied field;
                  conflicts must be empty (the agent has one source); contains_instructions and excerpt as the agent's own screen of item_details
```

The backend never fills a missing value. A cart line without a `facts` entry, a `facts` entry whose `item_id` is not in the cart, a `sources` value other than `agent_form`, or a non-empty `conflicts` list is `InvalidPurchase` with the line number.

Event construction. The backend builds the `Event` the engine already takes, so the same `evaluate(event, policy, state, facts, history=...)` runs for a simulator attempt and for an MCP purchase and nothing is keyed on which path produced it:

```
type                                "authorization.request"
request_id                          "local-" + the purchase file name (the sha256 hex of the key)
deadline_at                         timestamp + LEASH_PURCHASE_BUDGET_S, a new setting with no default; this is Event.deadline_at, Runtime has no deadline
authorization.authorization_id      "AGT" + 13 upper-case base32 characters from 8 random bytes, minted once per accepted purchase_key
authorization.source_authorization_id  the same value
authorization.scenario_id           "SCEN0000"   (no simulator scenario; the engine never reads it)
authorization.replay_order          1            (the engine never reads it)
authorization.mandate_id            the input mandate_id
authorization.profile_id, card_id   from the mandate's identity record (below); a mandate without one is InvalidPurchase("mandate has no card on record")
authorization.initiator_type        "agent"
authorization.merchant              the input merchant, plus availability "online", recurring_capable "false"
authorization.timestamp             the backend's clock, UTC, at acceptance of the purchase_key
authorization.amount, currency      total_chf, "CHF"
authorization.billing_amount_chf    total_chf
authorization.items_subtotal        sum(quantity * unit_price_chf)
authorization.delivery_fee          delivery_fee_chf
authorization.channel               "ecommerce"
authorization.customer_device_id    the paired agent_id (the agent is the device)
authorization.authority_status      "active" (checked above; a revoked mandate is InvalidPurchase before construction)
authorization.card_status_at_attempt "active"
authorization.spend_in_period_before_chf  null (the engine derives period spend from MandateState)
authorization.recent_attempt_count_10m    the number of purchase files on this mandate whose timestamp is within the 10 minutes before this timestamp, decided or not, excluding this one; the engine reads it at checks.py:132
authorization.fulfillment_method    "delivery"
authorization.delivery_by           null
authorization.order_returnable, order_cancellable  "unknown"
authorization.related_authorization_id, related_authorization_status  null
authorization.purchase_description  the confirmed draft's instruction
authorization.items[]               line_no from 1 in cart order; item_id, item_name, item_category, quantity, unit_price = unit_price_chf, currency "CHF", item_details
mandate                             mandate_id, customer_id, card_id, profile_id from the identity record; status "active"; instruction, hard_rules and uncertainty_policy from the effective policy exactly as policy_context.refresh builds them for a simulator event
context.approved_spend_in_period_chf  null
context.recent_authorizations       one RecentAuthorization per decided purchase file on this mandate with a timestamp in the 1440 minutes before this timestamp: authorization_id and timestamp from the file, merchant_id and billing_amount_chf from the Event stored in the file, status "approved" for a final approve, "declined" for a final decline, "pending" for an unanswered step_up; the engine reads it at checks.py:157-159 and rules.py:192; the related-authorization branch at checks.py:166-167 never runs because related_authorization_id is null
runtime.received_at                 timestamp
runtime.history_window_minutes      1440
runtime.context_basis               "run_decisions_and_scenario_timestamps", the only value the type accepts
```

The purchase file therefore stores the built `Event` next to the `Decision`, so later purchases can build `context` from it without a second source.

Neither `runtime.history_window_minutes` nor `runtime.context_basis` is read by the engine (`rg history_window_minutes src/leash/engine` and `rg context_basis src/leash/engine` are empty at ffdb74b); they are set so the `Event` validates, and their values are fixed here so two backends build the same event.

Identity record. `confirmation.json` holds the draft, the simulator draft ID, the mandate ID and the confirmer, and no card or profile (`store.record_confirmation`). The simulator never returns the card for a mandate; it appears only in the events it delivers, as `mandate.customer_id`, `mandate.card_id` and `mandate.profile_id`. The implementation PR therefore adds `identity.json` to the draft folder, written once by the runner under the mandate lock from the first `Event` it accepts for the mandate, holding exactly those three values, and never overwritten; a later event that carries different values for the same mandate raises before evaluation. `buy` reads it and refuses a mandate that has none. In practice this means an agent can buy on a mandate only after the simulator has delivered at least one attempt for it. The file does not exist today.

`history` is not passed: `evaluate` is called with `history=None`, exactly as the runner calls it (`loop.py` never passes a `History`), so `_history_index` uses the packaged `authorization_history.csv` (`evaluate.py:45-48`, `data.py:115`) and the card's familiarity comes from the same rows as for a simulator attempt. Local purchases never enter that CSV, so a merchant first seen through `buy` stays unfamiliar to the history checks; the duplicate and velocity checks see it through `state` and `context` instead. `state` is the current `MandateState`. The decision is recorded with `leash.engine.state.record` and appears in `GET /mandates/{mandate_id}/decisions`, `GET /decisions/{authorization_id}` and, for a `step_up`, `GET /step-ups/pending`, exactly like a simulator decision.

Local origin. The runner's `Coordinator.authorization` prepares a simulator intent for every decision (`coordinator.py:118-153`), and intents require the originating simulator `run_id` and a verified remote receipt (`intents.py:80`, `:130-134`, `:171`); a local purchase has neither, and no simulator response or run ID is ever invented for it. A local purchase is therefore never passed to `Coordinator.authorization` or to the intent journal. It is finished by `records.recover_accepted(event, decision, accepted_at, accepted, resolution=False, state_before=...)` (`records.py:152-193`) under the mandate lock, with `accepted_at` the backend's clock and `accepted` the object `{ "origin": "local", "purchase_key_file": <file name> }` in place of a simulator receipt. That helper calls `leash.engine.state.record` and writes `data/decisions/<mandate_id>/<authorization_id>.json` with the keys `decision, event, state_before, state_after, accepted_at, accepted` that `records._read` requires (`records.py:208-212`), so the decision appears in `GET /mandates/{mandate_id}/decisions` and `GET /decisions/{authorization_id}` through `records.mandate_history` and `records.decision_detail` unchanged, and `check_consistent` holds. The purchase file gets the `authorization_id` after that write. The MandateState section names the local finish next to `/resolve`; the pure functions `apply` and `record` and the locks `customer_lock` and `mandate_locks` are reused as they are.

Idempotency. `purchase_key` is unique per `(agent_id, mandate_id)`. The backend stores `purchases/<sha256(agent_id + ":" + mandate_id + ":" + purchase_key)>` under the mandate lock, `O_EXCL`, before it evaluates, holding the canonical input hash (SHA-256 of compact sorted-key JSON of the validated input without `purchase_key`) and, once decided, the `authorization_id`:

```
same key, same input hash, decided       -> the stored Decision and its original reference are returned again, with the original expires_at; no new authorization_id, no second evaluation, no state change, no renewed authority
same key, same input hash, not yet decided, before deadline_at  -> PurchaseInProgress; the agent polls get_purchase_status with the authorization_id it already holds, or retries after the decision budget
same key, same input hash, not yet decided, after deadline_at   -> PurchaseFailed("decision was not recorded before <deadline_at>"); the purchase stays undecided for ever, no decision is substituted, and the agent mints a new key
same key, different input hash           -> PurchaseKeyReused, the purchase is not evaluated; the agent must mint a new key for a changed cart
new key                                  -> a new purchase, judged on the current state, which includes every earlier accepted decision on the mandate
```

There is no expiry on a used key within the mandate's life. A revoked or expired mandate rejects every `buy` before the key is looked at, including a repeat of a decided key: the stored Decision is readable through `get_purchase_status`, and a repeat `buy` on a dead mandate is InvalidPurchase. A crash after the key file is written, with no durable evaluated result, leaves the file without a decision. Nothing recovers it into a decision: `get_purchase_status` and a repeat `buy` report `PurchaseInProgress` until `deadline_at` and `PurchaseFailed` after it, the file is kept as the record of the failure, and the runner's log carries the error that interrupted the evaluation. A decision exists only when the engine produced it or the Wallet answered a step-up.

Local recording recovery. Once evaluation has returned, the purchase file receives a durable `recording` object before any spending-state or history write. It contains the validated decision, persistent mandate-local `state_before`, acceptance time, original facts and pending question with its original expiry, if applicable. A checked Wallet answer or expired timeout saves its decision, pre-resolution state and local acceptance metadata in the pending file's `recording` field before resolving state. These are local storage records, never simulator intents or fabricated remote receipts. Finishing the state, history and purchase or pending-file writes removes `recording` last.

The coordinator completes these saved writes under the customer and owned-mandate locks before another mutation. The Wallet sweeper also discovers unfinished recordings, including purchases interrupted before their pending-question file existed. Recovery reuses the saved decision and expiry; it makes no model call, invents no answer and does not evaluate an unfinished purchase again. An identity mismatch or ambiguous ordering between unfinished records raises. Older partial writes without saved recording inputs cannot be reconstructed by this mechanism.

`step_up`. Same as a simulator step-up: the Wallet answers through `POST /step-ups/{authorization_id}/answer`, or the book times the pending step-up out to `decline` with reason `step_up_timeout` once its `expires_at` has passed, the same rule as for a simulator attempt. A timeout applies only to an accepted pending step-up that a human could have answered, never to an undecided purchase. Today `StepUpBook.answer` and `StepUpBook.sweep` finish through `Coordinator.authorization` (`stepups.py:179-195`), which needs a simulator run, and `answer` raises when the book file has no `run_id` (`stepups.py:216-218`); the book file is `{ step_up, status, resolution }` plus `run_id` (`stepups.py:6-7`, `:158`) and `StepUp` has no origin field (`decision.py:166-170`). The implementation PR adds `origin: "local"` to the book file next to `run_id` for a local step-up, leaves `run_id` absent for it, and gives `answer` and `sweep` a second finish: when the book file carries `origin: "local"`, `_finish` calls `records.recover_accepted(..., resolution=True, accepted={ "origin": "local", ... })` instead of `Coordinator.authorization`, which writes the `<authorization_id>.resolve.json` record and records the final `Decision`; the missing `run_id` check applies only to a file without `origin`. The `origin` key in the book file is the only thing that selects that finish. Nothing in the engine reads it. The agent sees `resolved: false` in `get_purchase_status` and nothing it sends can resolve it. `get_purchase_status` on an `authorization_id` that belongs to another agent's account is `PurchaseUnknown`, the same error as a nonexistent id.

Out of scope for this contract and for the demo: a payment processor, a merchant order, inventory or price lookup by the backend, a `buy` that the backend retries or re-quotes, and any purchase created from the Wallet or the Harness page instead of through a paired agent. `reference` is data for a later processor integration and is not consumed by anything we ship.


## Harness provider session

This is the implementation contract for the server-side Shopping Harness adapter. Implementation status is recorded in plan 04. The foundation milestone adds owned storage and GET readback while create and message requests return `provider_unconfigured` before creating a session, starting pairing or reserving a message. Successful creation and execution require the later pairing and provider adapter. The standalone Wallet and external MCP clients keep their current flow. This section does not enable a provider, model-based purchase scoring or a payment processor.

### Provider selection and credentials

The first supported pair is `provider: "anthropic"`, `model: "claude-sonnet-5"`. It is the initial UI selection, but both fields are required in the create request. Unknown provider/model pairs are 422; an unavailable configured pair is 503 `provider_unconfigured`. There is no substitution, alias to another model or automatic provider retry. Other providers named in plan 04 remain unavailable until separately implemented and exercised.

The adapter is disabled unless an operator sets `LEASH_HARNESS_ENABLED=1` after confirming that the host's ignored `.env` contains its Anthropic credential. Unset or `0` leaves it disabled; other values refuse startup. The foundation accessor in `leash.runner.settings` reads only that enable flag, including when it is `1`. The completed adapter adds a separate scoped accessor for the required `ANTHROPIC_API_KEY`; that accessor must never print the key. No credential or optional provider package is loaded while disabled, so the existing Wallet can run without the adapter dependency. When enabled, a missing dependency or credential produces `provider_unconfigured`; it never starts a turn with a different configuration. The implementation uses the official Anthropic Python SDK with automatic retries disabled and the pinned Anthropic endpoint/model. It does not inherit a browser-supplied URL or silently use a different gateway, provider credential or model. The browser, provider messages and tool-visible arguments receive no provider key, agent token or pairing verifier. The release still needs one actual provider request after the operator's credential confirmation; this contract makes no claim that a credential is present.

`LEASH_HARNESS_ENABLED` controls chat/tool execution only. It does not change `LEASH_ENABLE_MODELS`, the deterministic evaluator or the separate Jev release gate. Runtime purchase models remain off.

### Customer routes

All three routes use the existing authenticated customer cookie. Both POST routes require the exact configured Origin, with the existing 401/403 behavior. The server derives the account from the session; no request may supply an account, agent token, MCP endpoint, provider endpoint, phase or customer answer. An unknown or foreign session ID returns the same 404.

| Route | Input and response |
| --- | --- |
| `POST /agent-sessions` | `{ client_request_id: UUID, provider: "anthropic", model: "claude-sonnet-5" }` -> 201 `AgentSession` after durable creation, initially `pairing_required`. An identical repeated create key for this account returns the same session, 200; a different payload on that key is 409. Unsupported input is 422 and a disabled or unavailable provider is 503 before creating a session or beginning pairing. |
| `POST /agent-sessions/{session_id}/messages` | `{ client_message_id: UUID, expected_version: int >= 1, text: str }`, text 1-8000 characters -> 202 `{ session: AgentSession, operation_id }` after the message/operation is durably reserved. The operation performs provider/MCP work asynchronously. Same message ID and same input returns 200 with the original operation ID and the current session snapshot, without executing it again; this lookup precedes the version check. Changed input on an existing ID, a stale version for a new message or a second active operation returns 409. |
| `GET /agent-sessions/{session_id}` | 200 `AgentSession`. A read-only snapshot, with no provider call, MCP mutation, implicit retry or phase advancement. The browser polls while an operation is running. |

Session-specific request errors return `{ error: { code, stage, message }, session_id: str | null, version: int | null }`; IDs and versions are present only for an already owned session. Authentication and Origin failures retain the existing 401/403 middleware response. A disabled/unavailable-provider create request creates no session; its error is a request-level response. Provider and MCP failures after session creation are persisted in that owned session before its operation stops. A missing operator credential on a turn is `provider_unconfigured` at stage `configuration`, with no provider call. Provider authentication, timeout and malformed-response failures use `provider_auth_error`, `provider_timeout` and `provider_response_invalid`; they do not expose the provider's raw error body. Validation errors do not reserve a message or execute a tool.

`AgentSession` is the browser-safe view below. Unknown fields are rejected on writes. Timestamps are UTC; IDs are server-generated except the two client idempotency IDs. `version` increases on every persisted change. Null IDs mean that no successful tool result has bound such an object yet.

```
session_id, version, provider, model, created_at, updated_at
phase: pairing_required | briefing | awaiting_policy_confirmation | confirmed |
       searching | awaiting_purchase_answer | completed | rejected | failed
operation: null | { id, client_message_id, status: queued | running | succeeded | failed,
                    started_at: timestamp | null, finished_at: timestamp | null }
messages[]: { id, sequence, client_message_id: UUID | null, role: user | assistant,
              text, status: complete | partial, created_at }
tool_calls[]: { id, sequence, operation_id, name, status: planned | running | succeeded | failed | unknown,
                started_at: timestamp | null, finished_at: timestamp | null,
                summary, draft_id: str | null, authorization_id: str | null }
errors[]: { id, sequence, operation_id: str | null, stage: configuration | pairing | provider | tool | recovery,
            code, message, occurred_at }
connection: { status: pending | connected | revoked | lost, agent_id: str | null,
              agent_label, scopes: [str], pairing_expires_at: timestamp | null }
draft_id, mandate_id, authorization_id: str | null
backend_status: { policy: null | pending | confirmed | rejected,
                  purchase: null | pending | approve | decline,
                  observed_at: timestamp | null }
wallet_link: null | { kind: pairing | policy | purchase, url, expires_at: timestamp | null }
available_actions: { send_message: bool, open_wallet: bool, search: bool, buy: bool }
```

Every new message, tool-call entry or error receives one immutable positive `sequence` from the session's shared counter, under its lock. Each array is returned in increasing sequence order, so the UI can interleave them without guessing from timestamps. Updating a tool's status increments the session version and keeps its original sequence. `backend_status` records the latest authoritative observation and its time; it is not a prediction. The next explicit message refreshes the bound object's status before any phase transition or provider call. A Wallet return may show the current object through its existing owned routes and offer Continue; chat text or a cached observation cannot authorize resumption.

Assistant text is provider output, not authoritative workflow state. Tool summaries are server-generated from validated tool results, not a provider's claim that an action happened. The UI displays those separately and renders user, assistant, tool-summary and error content as escaped text, never executable HTML. Errors contain a stable code and a redacted explanation, never raw HTTP headers, credentials, private provider traces or another account's data. Raw tool arguments/results are not copied into this browser view. An approved decision is labelled an authorization result; it is never labelled an order or charge.

### Pairing and server-side custody

Creation reserves the session before beginning a real MCP pairing for a clearly labelled Harness agent. The server keeps the verifier in memory and exposes only the existing Wallet pairing link to the owning browser. The customer approves through the existing Wallet route. A message received while `pairing_required` first checks the authoritative pairing record: if unapproved it returns 409 `waiting_for_pairing` without reserving a provider turn; if approved, the adapter completes pairing through MCP and verifies that the returned account matches the session owner before using the token. A mismatch fails the session without exposing either account's details or using that token.

The MCP credential is sent only by the server-side adapter to the configured trusted MCP endpoint. Neither its value nor the verifier is sent to the provider. They are kept in the live adapter's memory, outside the JSON session store. Loss of that custody on restart fails the affected session with `pairing_required_after_restart`; a fresh session and customer-approved pairing are required. No credential is reconstructed from a digest. Existing drafts remain available in the Wallet. The temporary pairing link is composed from in-memory pairing data and is not stored in clear with the durable transcript.

Policy-only sessions request only the implemented policy scopes. Purchase capability requires the separately agreed purchase scope and customer approval; an existing token is never widened. The adapter validates the current token/account before each privileged tool dispatch. Revocation stops further dispatch and is recorded as an error. Pairing approval, policy confirmation, tightening, revocation and purchase answers are never provider tools.

### Phase enforcement

The server owns transitions. A model response, a chat message such as "I approved", or a browser navigation does not change a mandate or resolve a purchase.

| Phase | Permitted work and transition |
| --- | --- |
| `pairing_required` | No provider call or search. The customer uses the existing pairing UI. An explicit message after approved pairing completes the binding and enters `briefing`. |
| `briefing` | Provider conversation may clarify the instruction and call only implemented policy-authoring/read tools. A successful proposal binds its returned `draft_id`, enters `awaiting_policy_confirmation` and provides the persisted-ID Wallet link. It stops that operation before search or purchase. |
| `awaiting_policy_confirmation` | No search or purchase. On an explicit new message, the server reads the bound draft's authoritative owned status. Pending returns 409 `waiting_for_policy`; rejected enters `rejected`; confirmed with a mandate ID binds it and enters `confirmed`. A provider claim of confirmation has no effect. |
| `confirmed` / `searching` | Before each new operation or purchase, recheck the bound mandate's owner and active status. Search is permitted only through an implemented, explicitly configured capability. A server-side inventory/search tool needs its own agreed input/provenance contract and real implementation. Until then `available_actions.search` and `available_actions.buy` are false; no provider-native search tool is exposed. An unavailable search tool raises a persisted error; generated product claims do not stand in for a search. Future results must retain their actual sources and distinguish a discovered offer from a verified final checkout total. |
| `awaiting_purchase_answer` | A successful implemented `buy` returning step_up binds its authorization ID and supplies the Wallet purchase link. Only authoritative readback after the existing Wallet answer or timeout can produce a final result. No provider call extends the human window or supplies an answer. An explicit message can request readback; pending returns 409 `waiting_for_purchase`. |
| `completed` / `rejected` / `failed` | Terminal, read-only session. No automatic retry or further tool execution. The customer may create a new session; that does not revive, approve or repeat a prior purchase. |

Before a provider request, the adapter constructs the allowed tool set for the current phase. It waits for a complete provider response and validates every returned tool name and its entire argument object before dispatch. A truncated response or partial tool-argument stream cannot dispatch a tool. Unknown or disallowed tools fail the operation. ID-bearing read/purchase tools must refer to the session's server-bound draft or mandate, not an ID chosen by the model. The adapter exposes no shell, arbitrary HTTP request, arbitrary MCP server, Wallet mutation or credential tool. Pairing tools are adapter-controlled and absent from the provider's tool set.

A session can expose `buy` and purchase readback only after their own reviewed contract and implementation land. A successful buy binds the returned authorization ID: final approve enters `completed`, final decline enters `rejected`, and step_up enters `awaiting_purchase_answer`. Authoritative readback after the Wallet answer or timeout applies the same final transitions. The adapter uses the purchase tool's idempotency and local-versus-simulator origin rules. It never constructs a simulator receipt or invokes simulator decision/resolve endpoints for a local purchase. A failed or pending purchase yields no completed-purchase claim. The remaining search and purchase capabilities may stay unavailable while briefing/proposal support is implemented, and the UI must show that limitation.

### Persistence and failure handling

Session records live under `LEASH_POLICY_STORE/agent-sessions/`, mode 0600, with account ownership set at creation and never changed. A per-session file lock protects version comparison, message-ID reservation and the single active operation. JSON replacements are atomic, with file and parent-directory synchronization before reporting durable acceptance. Creating the account-scoped `client_request_id` mapping is exclusive so concurrent create requests return one session. A mapping left without its session after a crash is a recovery error; it must not create a second session or pairing on replay. Reads never dispatch work. Network calls do not hold the customer's mandate locks; individual MCP policy/purchase mutations retain their existing customer-first locking requirements.

The adapter persists an operation and each tool-call intent before sending it. It records the validated result before the next tool or phase. One operation has a 60-second total deadline, at most eight tool dispatches and a 4096-output-token provider budget per request; exceeding a limit stops the operation and persists an error, with no fabricated assistant result or business decision. SDK retry behavior is disabled. No alternate provider is selected after failure.

A process restart never replays an operation left queued/running or a mutating tool with an unknown outcome. The session becomes `failed` with an explicit recovery error and retains its known IDs and observations. A mutation whose response was lost remains marked `unknown` until a separately defined authoritative readback can establish its outcome; absence of a response is not a decline, approval or timeout. Where a tool has no authoritative reconciliation contract, no result is invented. The browser can still open any known owned draft or purchase in the Wallet.

Implementation order: merge this contract; add the scoped provider configuration and owned session store/routes; implement real MCP pairing and policy tools; add the pinned provider adapter after operator credential confirmation; then wire the Shop UI against observed responses. Search and purchasing each require their capability checks and their own completed integration. The live model-off Wallet demonstration remains independent of this work.

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

Pairing. `begin_pairing` creates two secrets: a pairing code of 16 random bytes (128 bits) that travels in the link, and a verifier of 32 random bytes (256 bits) that stays with the agent. It stores the code's digest, the verifier's digest, the agent label and the fixed scope set, valid for 5 minutes. The customer opens the link while logged in, or opens the Pair screen (`/app/#pair`) while logged in and types the pairing code into its code field; either way the Wallet calls `GET /pairing/{code}`, shows the label, the scopes and the expiry and offers Approve, which calls `POST /pairing/{code}/approve`. The typed code goes to the same two routes and nowhere else; no new route exists for it, and the verifier never enters the browser. The link's origin is `LEASH_APP_ORIGIN`, which `leash.policy.mcp_server` reads at startup with the same validation as `leash.api` and refuses to start without, for stdio and streamable HTTP alike. The Wallet must be reachable at that origin from the customer's device: the demo runs the MCP client and the Wallet on one machine with the loopback origin, and a client on another machine needs a Wallet deployed at a trusted origin, never a tunnel opened for it. Approval writes `account_id` and `status: approved` under the file lock. `complete_pairing` takes the code and the verifier, reads the record under the lock, requires `status: approved`, an unexpired record and `sha256(verifier)` equal to the stored digest by constant-time comparison, then, still under the lock, first rewrites the pairing file with `status: consumed` and then writes the agent record with a token of 32 random bytes (256 bits). A crash between the two writes leaves a consumed pairing and no agent: the next `complete_pairing` raises `PairingUnknown` and the agent begins a fresh pairing. A code is therefore completed at most once and no second credential is ever minted for it. The token is returned once, in the tool result over the transport, and is never stored in clear. A wrong verifier and an unknown, expired or consumed code all raise the same `PairingUnknown`; the API side returns 404 for the same states. Expired pairing files are deleted on every `begin_pairing`. Someone who sees the link can approve nothing without the customer's session and can complete nothing without the verifier; the code alone selects the pairing to show and is dead after five minutes or one use. The Wallet serves the pairing page with `Referrer-Policy: no-referrer` and the API never writes the code to a log.

Scopes are one fixed set for every paired agent: `policy:propose` (`propose_task_policy`) and `policy:read` (`get_policy_status`, `get_policy_summary`, `get_policy_authoring_instructions`). `buy` and `get_purchase_status` stay parked; when they land, the Authority paragraph of "Purchase input and idempotency" adds `purchase:decide` as an opt-in scope requested at `begin_pairing`, and this fixed set stays the default. The set is recorded on the agent record and displayed at approval so a later narrowing is a data change.

Token presentation. Streamable HTTP: `Authorization: Bearer <agent_token>` on every request. The ASGI middleware no longer rejects requests; it reads the header into the request context. Each tool that needs a principal computes `sha256(token)` and reads exactly the file with that name in `agents/`; there is no scan and no comparison against a list. A missing file, a file that fails to parse, a record whose `account_id` is empty, or `revoked_at` set all raise the same `Unauthorized`; a valid record has `last_used_at` updated. Two agents can never share a digest because the token is 256 random bits, and a collision on write is refused (`O_EXCL`) and raises. Stdio: the process serves one agent; it reads `LEASH_AGENT_TOKEN` from its environment at startup if set, and otherwise holds the token returned by its own `complete_pairing` in memory for the rest of the process. The client helper in `docs/mcp-client.md` sends the token from `LEASH_AGENT_TOKEN`.

Ownership. `propose_task_policy` stores `created_for = account_id` of the presenting agent; the value is immutable, is not part of the draft hash and is not sent to the simulator. `get_policy_status` and `get_policy_summary` require the presenting agent's `account_id` to equal `created_for`, else raise as unknown. The app routes `GET /drafts/{id}`, confirm and reject require the session's `account_id` to equal `created_for`, else 404. Drafts have an owner from creation, so the legacy ownerless-draft rules become unreachable for new drafts and are deleted with the demo data. Revocation flips `revoked_at`; existing drafts and mandates of the account are untouched, the agent only loses the tools.

Locking. The confirm route and `PUT /global-policy` take `leash.runner.records.customer_lock(account_id)` first, as ruled for #58, then the mandate locks. Pairing approval and token consumption use the per-file flock only; they touch no mandate state.

Split. This section merges first. Then, in order: the policy lane builds `leash.api` accounts, sessions, pairing routes and the Origin check, and `leash.policy.mcp_server` pairing tools and per-tool authorization, in one PR; the app lane builds Register, Login, Pair and Agents screens against the table above in a second PR. The runner lane is not touched. Both PRs need the exact-head review from a different model family before merge.

Bank integration. In production the account store and the password check are replaced by the bank's identity provider: the session is established by the bank app's authenticated context or an OIDC login, `account_id` becomes the bank's stable customer subject, and pairing keeps the same shape (customer approves a labelled agent in the Wallet, the agent receives a scoped revocable token). Nothing in the engine, runner or contracts depends on how the session was obtained.

## MCP tools

Served by `leash.policy.mcp_server` over stdio or streamable HTTP, backed by the same `LEASH_POLICY_STORE` directory as `leash.api`. The two pairing tools are the only tools an unpaired agent can call; every other tool needs the agent token from the section "Identity source" and raises `Unauthorized("pair this agent in the Wallet first")` without one. This is the whole agent-facing surface (plan 01, steps 2 and 9 to 12). Every tool raises on bad input; nothing is defaulted. No tool confirms, resolves, tightens or revokes. `propose_task_policy` returns the full stored `PolicyDraft`, including the rules and hash the agent submitted. The read-only `get_policy_status` and `get_policy_summary` tools return no rule fields or hash.

| Tool | Input → returns |
| --- | --- |
| `connect` | `{ agent_label: str, wait_seconds?: int (1..290, default 240) }` → `{ agent_id, account_id, scopes, paired: true }` (plus `agent_token` over HTTP only). Begins a pairing and blocks until the customer taps Approve on the pending connection card in the Wallet's Needs tab, then completes it; the stdio server keeps the token. `PairingTimeout` after `wait_seconds`, `PairingUnknown` if the pairing expired. The two-step `begin_pairing` and `complete_pairing` remain for clients that hold the token themselves |
| `wait_for_policy` | `{ draft_id: str, wait_seconds?: int (1..290, default 240) }` → the `get_policy_status` result once `status` is `confirmed` or `rejected`; `PolicyPending` after `wait_seconds`. Read-only |
| `begin_pairing` | `{ agent_label: str }` (1 to 80 characters, shown to the customer) → `{ pairing_code, verifier, expires_at, scopes, wallet_url }`. `wallet_url` is `<LEASH_APP_ORIGIN>/app/?pair=<pairing_code>`, built from the origin the MCP server read at startup, never from a request `Host`. The agent hands the customer `wallet_url`, or the bare `pairing_code` to type into the Wallet's Pair screen, and keeps `verifier` to itself; it never appears in a link, a log or the Wallet. No token needed |
| `complete_pairing` | `{ pairing_code: str, verifier: str }` → `{ agent_token, agent_id, account_id, scopes }` exactly once, after the customer approved in the Wallet; before approval raises `PairingPending`; a wrong verifier, an unknown, consumed or expired code all raise the same `PairingUnknown`. No token needed |
| `get_policy_authoring_instructions` | `{ instruction: str }` → `{ guide, request_instructions }`; `guide` is the `policy://authoring-guide` resource (field vocabulary, rule format, proposal shape, restrictions) |
| `propose_task_policy` | `{ instruction: str, proposal: { rules: [Rule], examples: [...], open_questions: [...], uncertainty_policy } }` → the stored `PolicyDraft` (`draft_id`, `version: 1`, `hash`, the validated fields). Invalid proposal raises `InvalidDraft` with the reason. The agent then hands the customer `/app/?draft_id=<draft_id>` |
| `get_policy_status` | `{ draft_id: str }` → `{ draft_id, version, status: pending \| confirmed \| rejected, mandate_id: str \| null, confirmed_at: datetime \| null, rejected_reason: str \| null }`. `mandate_id` is set only when `status` is `confirmed`. Unknown draft raises |
| `get_policy_summary` | `{ draft_id: str }` → `{ draft_id, version, instruction, plain_english: [str], examples: [{ description, expected, why }], open_questions: [{ question, options, answer: str \| null }], uncertainty_policy }`. The sentences are the same ones the Wallet shows |
| `buy` | `{ mandate_id: str, purchase_key: str, cart: [{ item_id, item_name, item_category, item_details, unit_price_chf, quantity }], merchant: { merchant_id, merchant_name, merchant_category, merchant_mcc, merchant_country, merchant_city }, delivery_fee_chf: number, total_chf: number, facts: [PurchaseFacts] }` (validation, idempotency and the `purchase:decide` scope in section "Purchase over MCP", subsection "Purchase input and idempotency") → `Decision` (`approve`, `decline` or `step_up` with `authorization_id`). Parked for the submission: raises `NotImplementedError("purchases arrive through the simulator in demo mode; see plan 01 step 12")`. Scope when it lands: section "Purchase over MCP" |
| `get_purchase_status` | `{ authorization_id: str }` → `{ authorization_id, decision: Decision, resolved: bool, final: approve \| decline \| null }`; a `step_up` is `resolved: false` until the Wallet answers or it times out. Needs the `purchase:decide` scope. Parked with `buy` |

`facts` in `buy` is the form the agent's own model fills; the backend checks it deterministically and records `sources[field] = agent_form` for every field the agent supplied. The agent never sends the policy; the backend reads the confirmed policy for `mandate_id` from its own store.
