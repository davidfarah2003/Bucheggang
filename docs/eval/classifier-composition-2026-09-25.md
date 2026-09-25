# Classifier composition verification

P1/P2 adds shared assessment contracts and pure evaluator composition. It does not enable a model in the runner. The model-enabled merge and release hold remains in force.

## Real provider calls

Four actual requests used the classifier adapter frozen at `2b2f83f`, through OpenRouter System One, with the P1/P2 changes on measurement base `9bb1ebc`. Every request constrained the provider to TypeSafe with fallbacks disabled and requested `typesafe/jev-1.13-20260917`. The adapter accepted the same served model and provider on every response. [Captured distributions and code hashes](classifier-composition-2026-09-25.json) preserve the four results without credentials or raw merchant fields.

Credential-file reading went through `leash.runner.settings._parse_env`. Only the scoped OpenRouter credential was passed into the adapter's explicit `api_key` argument. Neither credential value was printed or stored in this evidence.

The provider received numeric history values, missingness and support counts. It received no customer/card/authorization identifiers, merchant text, purchase descriptions, catalogue fields or agent justifications. Features came from the actual supplied history records.

| Purchase input | Provider ms | Model checks | Baseline | With assessments |
| --- | ---: | --- | --- | --- |
| Public AU0001 | 539 | Both pass | approve | approve |
| Public AU0037 | 295 | Both pass | decline | decline |
| Saved live AU10319-414975d9 | 453 | Both uncertain | decline | decline |
| Saved live AU10234-fb2858da | 481 | Both pass | step_up | step_up |

AU0037 retained its deterministic price decline despite model passes. AU10319 retained `merchant_type_mismatch` while recording two model-uncertain checks. AU10234 retained `no_card_history` and `unrequested_item`; model passes did not satisfy the missing deterministic evidence. Every model check used `source=model` and preserved the actual probabilities and requested/served/prompt versions in its JSON value.

The public attempts were constructed by the existing replay builder. The two saved live inputs kept their actual authorization, original evaluation policy and recorded pre-decision state. Only receipt and deadline clocks were refreshed for offline evaluation. No result was submitted to the simulator and no customer answer was generated.

One attempted input selection found no recorded initial step-up with zero category support in both scopes. It raised before any provider request. The later step-up check used an actual recorded step-up without that extra condition. No invented purchase or model response was inserted to force a result.

These are four provider/evaluator composition observations. They do not establish accuracy, calibrated payment risk, whole-run latency or a successful customer Wallet journey. Those initial comparisons had no behavioural assessment.

## Feature binding and trained artifact

The engine-owner review found that the producer's newer digest included the complete feature map, while the initial shared helper bound only the event. The shared helper now takes `(event, features)` and hashes the same feature-bearing payload. It rejects non-finite values. The producer and consumer digests matched on all four saved inputs; changing a finite feature value after binding raised instead of returning a Decision.

The four original provider responses were composed again with their original feature profiles and the reviewed evaluation-only CatBoost artifact from classifier revision `bfb4df5`. Its SHA-256 was `e4815c5677073c4e985c56f09f045be3d72c4e3ae624b75f9d06870630c828cf`. Historical-decline scores were 0.029953, 0.163918, 0.139567 and 0.084303 in the table's order. Every `escalation_fired` value was false. Outcomes stayed approve, decline, decline and step_up.

No operational threshold was selected or activated, and no provider request was repeated. The JSON evidence preserves the feature-bound recomposition and artifact provenance separately from the original event-only comparison.

## Model-off and history-only replay

All 45 public attempts were evaluated sequentially with real history features derived by the frozen classifier code. Each shared `AssessmentBundle` bound those features to the actual authorization, policy hash, customer/card identity and simulated time. Behavioural and semantic outputs were explicitly null for this history-only run.

The result matched the model-off evaluator for every decision, reason-code list and evidence list: 11 approvals, 32 declines and 2 step-ups. No model check was added when both model outputs were absent. No live state file or customer resolution was written.

## Binding and validation refusals

Copies of the actual AU0001 assessment were altered in memory, then passed to the real evaluator. Each change raised before producing a Decision:

- Authorization ID changed: ValueError.
- Billed amount changed without a new purchase binding: ValueError.
- Effective policy hash changed: ValueError.
- Feature customer changed: ValueError.
- Feature time changed: ValidationError.
- Mandate-state identity changed: ValueError.
- A probability mutated to NaN after model construction: ValidationError.
- A question duplicated: ValidationError.
- Selected answer changed away from the unique argmax: ValidationError.
- A finite feature value changed after its digest was bound: ValueError.

The real adapter also rejected an expired absolute budget with `Jev has no time remaining before the deadline reserve`, before opening HTTP. None of these failures was replaced with a score or business outcome.

## Live-record history compatibility

An independent check at frozen classifier revision `96cce47` derived features for all 49 unique locally handled events in the four completed live runs. No identity or account-limit lookup failed. All 49 had prior approved card purchases; merchant familiarity was supported on 38, device familiarity on 43 and country familiarity on 47.

At measurement base `9bb1ebc`, the legacy deterministic engine still read its base-pack history. Passing the richer profile as a model assessment does not replace that reference source or clear `no_card_history`. Engine PR #45 separately addresses deterministic use of the additional history pack.

After rebasing onto its merge at `0b7c2c1`, all four captured real responses were composed again without new provider requests. Their outcomes stayed approve, decline, decline and step_up. AU10234's reasons changed from `no_card_history, unrequested_item` to `unrequested_item`, both with and without assessments. The extra history source removed the first uncertainty; the model pass still did not clear the remaining one. The JSON evidence includes this second comparison.

## Release limits

No caller enables models in this change. The history-only bundle has no mandate-state-derived model features; the evaluator still runs deterministic checks against the supplied current state. Final shared-lock rechecks, effective-policy refresh, durable mutation intents and bounded remote writes remain runner work.

The classifier producer must import the shared types, use the canonical purchase digest and enforce required outputs for its startup configuration. `assessments=None` is not permitted as recovery from an assessment failure. An approved operating threshold, full runner integration and human-ready live E2E still need their own observed results and reviews. The fitted artifact exercised above remains evaluation-only and cannot escalate.

## Rebase after customer-wide state support

The branch was rebased onto main5bc208d, including #49's CustomerApproval and MandateState.customer_approvals plus #48's owned list routes. The conflicting contract signature was resolved by retaining both evaluate(..., assessments=None) and state.load(mandate_id, customer_mandates=()). Both sets of engine Log entries remain. The classifier contract, model-check module and evaluator code are byte-identical to reviewed head6518cf8.

On rebased codee5b3ceb, all45 public attempts again returned11 approve,32 decline and2 step_up; local total p50 was0.233ms and p99/max0.421ms. The four captured genuine Jev responses and fitted-artifact scores recomposed to approve, decline, decline and step_up with three model checks each. Each captured state loaded with an empty customer_approvals field. Altering one feature in each bundle raised a digest error. No provider call or simulator request was made.

The first recomposition command assumed all capture rows used the public-input metadata shape. It stopped with KeyError after the first two rows; saved live rows use a Decision object instead. A second command handled those two recorded formats explicitly and completed all four. No application code or captured response was changed for that correction.

The earlier exact-head approvals do not approve the rebased head. The draft and both release holds remain in force pending the new delta review.
