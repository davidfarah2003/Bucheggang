# Classifier plan review

- Plan: [Classifier with personal history](02-classifier-design.md).
- Date: 2026-09-24.
- Reviewer seat: `classifier_plan_reviewer`, Cotal peer, read-only.
- Recorded model pin: `gpt-6-astra`, verified by connector startup and the reviewer's orientation result.
- Scope: implementation proposal only. No code approval, merge authorization, model-performance validation or deployment approval.
- Current status: revised proposal APPROVED at SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`. Contract clarifications and release gates remain as listed below.

## First verdict

BLOCK at plan SHA-256 `c464d919c58a1543b897727f7130c011befb2de46c3b8503e64483a076d3b835`.

The reviewer confirmed the hash before and after inspection. The complete findings arrived by Cotal DM. The record below preserves the findings and the coordinator's response; it does not claim the revision is approved.

### B1: Composite evidence provenance, high

The extractor computes `matches_request` using both product type and size but copies only the product-type source. A catalogue-backed product type can therefore give a derived match a `structured` label even when its size dependency is a merchant claim. The proposed evidence-reliance rule cannot be enforced safely from that single aggregate source.

Required correction: retain complete per-field/per-check dependency provenance, tied to the exact cart line and evidence reference. Check every dependency against the confirmed reliance policy. Add a mixed catalogue/text manual example.

Verified against `src/leash/extract/facts.py:125-133`. Revised plan sections 6, 9 and 11 require the contract/extraction change before learned approval.

### B2: Policy-mutation race, high

The initial plan serialized competing submissions and checked policy versions immediately before sending. That leaves tightening/revocation free to complete between the final check and submission. The simulator has no conditional policy-version parameter and existing runs retain their original snapshot.

Required correction: coordinate app policy mutation, final validation, submit/resolve and durable state recording under one mandate-scoped boundary. Recheck budget for customer approval after other spending. Describe local ordering separately from external simulator mutation and platform-confirmed cancellation.

Verified against `viseca-2026/technical_details.md:380` and `:394-397`. Revised section 3 requires one service coordinator, a declared local-policy overlay, unresolved-write journaling/reconciliation and an explicit limit on the guarantee for external mutations. Section 9 gates integration on contract agreement.

### B3: Unenforced pipeline deadline, high

The initial plan allocated a shared reserve but did not specify total-duration cancellation or finite budgets for all new stages. Existing extraction uses synchronous `urlopen` with a socket timeout; its Log records a 5.16 s response under a nominal 5 s cap. The simulator's default 8 s deadline starts at queueing, before delivery.

Required correction: use an absolute remaining-time budget across extraction, Jev, policy refresh, lock wait and submission; enforce cancellation for the entire response; resolve the inconsistent extraction caps; reject insufficient time visibly without a fabricated decision. Exercise the real combined pipeline with delayed delivery.

Verified against `src/leash/extract/model.py:114`, plan 03's Log and `viseca-2026/technical_details.md:245-247`. Revised section 3 specifies cancellable async transport, proposed stage caps under one absolute deadline and unresolved handling for timed-out writes.

## Additional findings addressed in the revision

- I1, medium: June originally selected the candidate, fitted calibration and chose thresholds. The revision selects the candidate by May forward validation, fits calibration on June 1-15, selects thresholds on June 16-30 and freezes July for evaluation.
- I2, medium: unseen customers with long histories do not measure cold starts. The revision calls for separate zero-history, 1-5-prior-purchase and new-card slices, with counts and no unsupported calibration claim.
- I3, medium: historical card-level velocity differs from live run-level velocity; approved counts include nonpurchase records; historical lifecycle status differs from today's card catalogue. The revision names all three and requires a frozen feature derivation before fitting.
- I4, low: probability validation was underspecified. The revision requires bounded finite values, normalization, complete question/line coverage, duplicate rejection and explicit tie/conflict handling.

## Owner decisions retained

- Agree whether updated local policy imposes additional restrictions over the simulator's frozen run snapshot. Do not claim the simulator applies PATCH retroactively.
- Select behavioural escalation thresholds and approve evidence-reliance rules before activation. A model score is neither customer consent nor a fraud finding.
- Accept a dated release scope and cross-lane prerequisite ownership. The revision proposes a 09:00 CEST scope decision on 2026-09-25, ahead of the 10:30 dry run. These remain proposed planning commitments.

## Positive assessment

The reviewer considered the shared-model/personal-feature design reasonable. They supported the distinction between historical decline propensity and fraud/consent, customer-separated and chronological evaluation, exclusion of public attempts from training, explicit user/card/mandate scopes, pre-event features, empty-history handling, policy precedence, justification binding and no-fallback error handling.

## Review evidence and limits

The reviewer read the complete plan, AGENTS.md, shared contracts, relevant lane plans, current extraction source, local data documentation and simulator timing/update documentation. They performed read-only file/hash/git inspection. They did not edit files, train models, call providers or the simulator, run the application, tests or a linter, or read secrets. Timing figures cited in the review were prior documented observations.

## Revision verdict

APPROVE implementation proposal at SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`.

The same reviewer read the full revision and verified this hash before and after inspection. They confirmed B1-B3 were resolved at proposal level and I1-I4 were materially incorporated. They found no new proposal blocker. The recorded model remained `gpt-6-astra`; no model change was inferred.

Three nonblocking details must be settled in the step-1 contract work:

1. R1, mutation reconciliation: persist PATCH/DELETE intent as well as decision/resolve intent. Keep approvals blocked while either outcome is unresolved. Reconcile authorization outcomes through authorization/event records; reconcile mutation outcomes using GET mandate state plus the local overlay/version record. Authorization records alone cannot prove a timed-out tightening succeeded.
2. R2, human deadline: automated decisions use `event.deadline_at`; customer resolutions use the authoritative human-window expiry from `StepUp.expires_at`. Apply total-duration cancellation to both, using the correct deadline. The automated deadline must not reject an otherwise timely human answer.
3. R3, redundant model selection: an internally contradictory provider-selected option must have one adapter-contract treatment. Recommended decision for the contract: derive the choice locally; if the accepted provider schema includes a redundant selected option, disagreement is a malformed-response error, not business uncertainty. Valid probability ties remain uncertain. Do not allow a schema error to flow into `uncertainty_policy=approve`.

These are implementation requirements to resolve before coding the corresponding paths. The plan file remains unchanged after approval so its reviewed hash stays verifiable.

The local effective-policy overlay, coordination contract, cross-lane ownership, customer-confirmed reliance rules, model thresholds and dated scope cutoff still require the named owners' decisions. Real deadline performance, provider access, model calibration and implementation correctness were not established by this review.

The follow-up used read-only file/hash inspection and checked the previously reviewed extraction/contract files for changes. No files were edited by the reviewer, and no fitting, provider inference, simulator/app execution, tests or linter were run.
