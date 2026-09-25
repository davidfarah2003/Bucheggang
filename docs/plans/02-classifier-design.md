# Classifier with personal history

- Status: implementation proposal. Independent verdicts are recorded in [02-classifier-review.md](02-classifier-review.md). No implementation or model fitting authorized by this document.
- Owner: David; engine lane.
- Date: 2026-09-24.
- Repository baseline: `e7e2b0e`.
- Relationship: proposed extension to [02 Decision engine](02-decision-engine.md). [03 Merchant-text extraction](03-merchant-text-extraction.md) remains a separate lane. This proposal does not change the current shared contracts.
- Review scope: one Astra peer, read-only, reviewing this document at its exact SHA-256. A plan verdict does not approve a future implementation or PR.

## 1. Decision to make

Build a classifier that combines exact policy checks, Jev semantic assessments and a shared behavioural model. Personalization comes from features computed from the requesting user's earlier transactions. We do not fit one model per user.

The final decision remains `approve`, `decline` or `step_up`, with evidence. The learned history output estimates historical authorization-decline propensity. It is not a fraud probability or a measure of customer consent.

The first delivery covers deterministic enforcement, personal-history features, an offline behavioural-model comparison, and a bounded Jev assessment. An agent-justification input and external shopping datasets are later increments. Training a new text foundation model, production deployment and automatic policy learning are out of scope.

## 2. Evidence and limits

Counts were measured from the local CSVs on 2026-09-24:

| Pack | Historical rows | Customers | Agent purchases |
| --- | ---: | ---: | ---: |
| `viseca-2026/data/` | 4,701 | 20 | 453 |
| `viseca-2026/additional-data-history/` | 144,674 | 500 | 19,037 |
| Combined | 149,375 | 520 | 19,490 |

The additional pack has 140,096 purchases, including 8,154 declined purchases. Its 2,674 cash withdrawals and 1,904 refunds are separate transaction types. Transaction, customer and card IDs do not overlap between packs; shared merchant and item catalogue rows agree. The history columns match, and the additional-history SHA-256 matches its manifest.

Both packs are synthetic. Historical `status` records an observed authorization outcome. Neither history includes fraud labels, the customer's then-current mandate, cart-line evidence or agent justifications. The additional pack's authors report AUC 0.81 overall and 0.65 after excluding obvious hard-rule violations for their logistic-regression baseline; these results have not been reproduced here.

The 45 public purchase attempts have no organizer answer key. They remain an integration exercise with separately reviewed expected outcomes. They are not training examples for the history model.

Jev documentation describes typed choices and probabilities, with multiple questions evaluated per request. It warns about arithmetic, dates and adversarial content. An independent routing benchmark measured approximately 127 ms median and 231 ms p95 latency on 80 cases repeated three times. Those figures do not establish our payment accuracy or deployment latency.

## 3. Execution and ownership

The runner owns orchestration and simulator I/O. The engine owns deterministic decisions, history features and assessments. Extraction stays in plan 03.

1. The runner validates the event and retrieves the current effective policy and version, including tightening and revocation. It supplies the identity and evidence through trusted service lookups. An agent-supplied customer ID cannot select another person's history.
2. The engine checks deterministic terminal failures available without a model: inactive mandate, explicit amount/category/count violations and rolling-budget breaches. A conclusive decline can short-circuit further scoring. This is normal decision logic, not recovery from a failed dependency.
3. The runner obtains extraction results under a shared deadline budget. Extracted strings retain their provenance; a typed string is not automatically trustworthy.
4. The engine constructs the card/user history features locally and computes the configured behavioural assessment. It sends Jev only the relevant confirmed requirements and permitted evidence.
5. The pure evaluator combines complete, version-bound assessments with exact checks. It performs no model or network call.
6. Enter the mandate's shared coordination boundary before final validation and hold it through submission and durable outcome recording. The same boundary protects app tightening/revocation and customer `/resolve`, not just competing automated submissions. Recheck the current policy, available budget, counts, purchase binding and state revision there. On a changed version, the previous assessment is invalid and cannot be submitted as current.
7. Only a simulator-accepted result advances completed spend. A pending step-up advances no spend. Every customer approval is re-evaluated against current budget/state under the same boundary; another purchase may have consumed budget while the customer was deciding.

For the first implementation, one service process owns a `MandateCoordinator` per mandate and all app mutation/runner paths use it. Multiple service workers or a separate runner process are unsupported until they share a transactional coordinator. Persist submission intent before sending and accepted outcomes atomically afterward. If a write times out after dispatch or the process crashes, mark its outcome unresolved and block further approvals for that mandate until `/v1/authorizations` or the event feed confirms it. Do not count it as completed spend, assume it failed, or blindly resubmit. Restart reconciliation is required before new approval work.

The simulator freezes a policy snapshot when a run starts; PATCH affects later runs. Proposed product behaviour is to enforce a customer's later tightening/revocation as an additional local service restriction on our decisions in existing runs. Step 1 must obtain owner agreement for this semantics and expose both the run snapshot and local effective version. For mutations through our app, lock order is the declared order: an approval already dispatched before a revoke may complete; after the revoke is acknowledged locally, no later approval is dispatched by us. Direct external simulator changes cannot be made atomic with our decisions because the API has no conditional-version token. Do not promise that guarantee. Record local refusal/revocation and platform-confirmed cancellation separately; queued cancellation is unspecified by the organizer.

### Enforced deadline budget

The under-50-ms target covers only the pure evaluator. Convert the event's real-clock `deadline_at` to a monotonic absolute deadline on receipt, subtracting a 250 ms safety margin. Queue/delivery delay is already consumed. Lock waiting, policy refresh, model calls, submission and persistence all consume this same allowance.

For the first measured model-enabled configuration, reserve 2 s of remaining time for final coordination, policy/state validation and submission. Within that reserve, initially cap policy refresh/validation at 500 ms, the submission request at 1 s, and local recording/scheduling at 500 ms. Reserve a further 1 s for Jev before starting extraction. Extraction gets `min(5 s, remaining - 2 s - 1 s)`; Jev subsequently gets `min(1 s, remaining - 2 s)`. Every stage is also bounded by the absolute deadline. Nonpositive stage allowance raises a named deadline error before dispatch. These are proposed configuration budgets, not measured reliability claims; owner-approved changes require another whole-pipeline run.

Replace blocking `urlopen` in the model-enabled path with cancellable async HTTP transport under an absolute `asyncio.timeout_at` boundary, including the entire response-body read. Close/cancel outstanding streams on expiry. Do not wrap the current blocking call in a thread and claim a cancelled await stopped it. Apply total-duration boundaries to policy reads and submit/resolve as well. A dispatched write whose response is lost follows the unresolved-outcome procedure above; local cancellation does not prove remote rejection.

Step 1 must agree the async extraction interface and replace plan 05's obsolete 1.5 s extraction cap with this single budget policy. The current extraction cap is 5 s and its Log records a 5.16 s response under a nominal socket timeout. Model-enabled release requires a real whole-pipeline timing exercise including intentionally delayed delivery; provider medians alone do not satisfy this gate. When the allowance is exhausted, surface an execution failure without inventing a business decision.

## 4. Personalization and history scope

Keep three explicit scopes:

| Scope | Purpose |
| --- | --- |
| Card | Exact `history.*_seen_on_card` rules and supplied card-scoped derived fields. |
| Customer | Optional aggregate behaviour across cards that the service is authorized to access. This never changes a card-scoped rule's meaning. |
| Mandate | Accepted purchases, pending step-ups, duplicate deliveries and budget/count consumption under that authorization. |

Customer and card IDs are lookup keys and evaluation-group keys. Exclude raw identifiers, persona names, scenario IDs, authorization IDs and replay position from learned predictors. Do not use demographic/persona labels as risk shortcuts.

Initial features:

- Number and recency of earlier approved purchases at the merchant, separately for card and authorized customer scope.
- Number and recency of earlier approved purchases on the device. A payment with no applicable device is distinct from an unseen device.
- Amount relative to earlier approved purchase amounts in the same category; history count, median and amount percentile. Empty history yields explicit missing values and support counts, not an invented typical amount.
- Country/channel/category familiarity, with their observation counts.
- Earlier attempts in short windows, including declines; simulator `recent_attempt_count_10m` already counts prior attempts and excludes the current one.
- Time since earlier accepted purchases, and earlier agent-initiated purchasing activity.
- Explicit amount-to-limit ratios when the limit was known before the decision. Report model performance separately when deterministic issuer restrictions do and do not fire.

Build every feature from records available before the assessed event. Respect documented historical `(timestamp, authorization_id)` ordering and exclude the current target outcome. Live rolling windows use simulated authorization time; real-clock receipt/deadline timestamps govern only execution time.

Approved purchase history establishes completed-purchase familiarity. Refunds never create a new familiar merchant or device. Recompute purchase-only familiarity from the underlying rows: the supplied approved-count columns include approved nonpurchase activity and are not aliases for these features. Historical net-spend features may account for refunds explicitly; refunds do not restore a mandate budget without an agreed mandate rule. Historical lifetime totals must not be used as rolling-period totals.

Freeze each feature's scope, event-time availability, unit, missing-value meaning and derivation before fitting. Historical card-level velocity and live run-level `recent_attempt_count_10m` are different features. Do not train on one and substitute the other. A deployed model uses only features whose derivation is available consistently at inference; the run-only signal can remain an explicit independent check. Historical lifecycle checks use each row's `card_status`, not today's `cards.csv.status`.

A valid empty history is a supported data condition. The shared model sees missing features and observation counts. A failed lookup, corrupt history file or unavailable model is an execution error. Do not disguise a failure as an empty profile.

## 5. Behavioural model

Fit regularized logistic regression and CatBoost offline against the same purchase-only target: historical `status == declined`. Compare them before selecting one deployed artifact. There is one configured deployed model, with no automatic switching between candidates.

Use the additional pack for fitting. Keep all 20 base-pack customers out of parameter fitting, calibration and threshold selection. Their pre-existing history remains available at evaluation/inference time for profile construction, as it would for a real customer.

Record split membership once in a manifest using a fixed seed:

- Reserve 20% of additional-pack customers for unseen-customer evaluation.
- On the remaining customers, compare fixed candidate configurations using forward validation: fit through April and select the candidate on May. Then refit that selected configuration through May; no later result changes the candidate.
- Fit the declared calibration method on June 1-15 for those customers. Select the proposed escalation threshold on June 16-30, without refitting the calibrator on that second portion.
- Freeze the chosen artifact and evaluate on July, reporting seen-customer and reserved-customer results separately. Report actual July escalation rates and calibration; the June operating point is not a promise about July.
- Earlier activity of reserved customers may construct their profiles, but their outcomes cannot fit parameters or thresholds. Do not use July or the base-pack evaluation to choose between candidates.

Target-derived categorical encodings, imputation parameters and population statistics are fitted only within the training partition. IDs must not be predictors. A label's existence in the CSV does not make it available at event time.

Report PR-AUC, ROC-AUC, Brier score, calibration by score band and recall at stated escalation rates, with sample counts and a constant/majority baseline. Separate human- and agent-initiated purchases, card lifecycle violations and the subset that passes deterministic checks. Check feature availability and distribution differences between history and live events; a feature absent live cannot be required by the deployed model.

Report zero-history, low-support (1-5 earlier approved purchases) and new-card/existing-customer slices separately. A held-out customer with eleven months of profile history is not a cold start. If a slice has insufficient outcomes to assess calibration, say so and do not claim calibrated scores for that population. The offline comparison must show both candidate pipelines accept supported missing inputs without catching errors and substituting scores. Any numerical encoding for an empty feature is predefined with an explicit missingness flag and fitted preprocessing; it is never an error-recovery default.

No numeric escalation threshold is approved by this plan. Publish the June threshold trade-off table first. The lane owner selects the operational threshold and escalation budget before model-driven escalation is enabled. Until that decision, the experimental history score is evaluation-only and cannot affect a live decision. This is a deliberate release stage, never an error-triggered fallback.

Version the artifact with the input manifest hashes, feature schema, split manifest, calibration method, training-library versions and selected threshold. A missing or incompatible required artifact prevents startup of the model-enabled configuration.

## 6. Jev semantic assessment

Pin `jev-1.13.0` for the first measured comparison, subject to live provider availability. Missing credentials or an unavailable pinned version are blockers, not reasons to substitute another model. Do not fine-tune Jev; its documented API supports request-based customization.

Start with a small set of per-line questions:

| Question | Outcomes |
| --- | --- |
| Does the item fulfil the stated purpose? | `matches`, `contradicts`, `insufficient_evidence` |
| Is an extra item requested by the confirmed instruction? | `requested`, `unrequested`, `insufficient_evidence` |
| Does a proposed substitution preserve the specified requirements? | `preserves`, `violates`, `insufficient_evidence` |
| When a justification exists, do the supplied facts support its claim? | `supported`, `contradicted`, `unverifiable` |

Keep question IDs stable and bind each result to a cart line and requirement. Persist the probability distribution as a model assessment, not as externally verified truth. Validate complete expected question/line coverage, exact options, no duplicate JSON keys or results, finite probabilities in [0,1], and a distribution sum within 0.015 (two-decimal provider rounding, no renormalization) of 1. Reject a malformed response rather than renormalizing it. Derive the selected option by argmax; exact ties or disagreement with a returned selection remain uncertain and visible. A domain-specific acceptance threshold is separate from this shape validation. Jev confidence is derived from its output distribution and is not a guarantee of payment correctness.

Use exact code for amounts, sizes expressed in agreed structured units, dates, counts and return-day comparisons once acceptable facts are present. Jev does not calculate budget compliance or generate the final reason codes.

The extractor already returns `matches_request` and provenance, but the current composite provenance is insufficient: `facts.py:125-133` uses product type and size while recording only the product-type source for `matches_request`. Do not trust that aggregate source label when deciding admissibility.

Step 1 must add dependency provenance for every derived fact/check: exact cart line (`line_no`, `item_id`), contributing field, source kind, evidence reference and transformation. A match derived from catalogue product type and merchant-stated size retains both dependencies. Each dependency must be admissible under the confirmed evidence-reliance policy; the trusted catalogue dependency cannot upgrade the merchant claim. Recompute admissibility from the dependency set before preserving a deterministic match or mismatch. If provenance is incomplete, the check is uncertain. Include this rule in the shared contract and update extraction before any learned approval path is enabled.

Jev supplies an additional assessment of unresolved semantics; it cannot silently replace an extractor result or clear an instruction flag. Conflicting assessments remain visible and create uncertainty.

The merged extraction implementation at this baseline defaults `allow_model_resolution=False`. Jev must not bypass that rule by filling the same unknown fact through a different path. A semantic result may count toward satisfaction only under an explicit, customer-confirmed evidence-reliance rule agreed with policy/extract. Otherwise it can identify uncertainty for escalation and be displayed as supporting evidence. This gate is a prerequisite to model-assisted automatic approval.

Raw merchant descriptions, injection excerpts and unfiltered justifications are excluded from the evaluator interface. Jev receives only bounded, task-relevant fields, with merchant/agent provenance preserved. This reduces exposure; it does not make the model immune to prompt injection. Neither the model nor an evidence string can edit the mandate, select tools, fetch URLs or access credentials.

## 7. Agent justification extension

The simulator has no dedicated justification field. Do not repurpose `purchase_description`, generate an explanation and attribute it to the agent, or mutate the organizer event schema.

A later application-owned input can accept a short purpose and bounded claims. Store it separately with authenticated actor identity, mandate ID/version, purchase digest, request ID and expiry. The digest covers merchant ID, full cart quantities/options, amount/currency, delivery and material terms. A new cart or tightened policy invalidates the binding.

Claims carry references to evidence already held by our service. Resolve references from an allowlist within the same purchase; do not fetch agent-supplied URLs. An agent's claim about customer confirmation requires a real confirmation record. A signature proves the origin of a claim, not its factual truth.

Absence of optional justification is a valid event condition. It does not itself imply wrongdoing, and the absent claim question is not scheduled. A submitted but malformed or mismatched justification is rejected explicitly. Separate source-backed facts from unsupported claims in the audit record.

Do not present an agent-generated justification as new evidence when it was generated from the same purchase fields we already have. That is correlated restatement and cannot establish an accuracy gain.

## 8. Decision composition

No weighted sum can compensate for an explicit failed restriction.

1. A deterministic violation based on admissible evidence produces `decline`.
2. Model-only semantic disagreement, insufficient evidence, and an activated history-escalation threshold produce `uncertain` checks. They are not automatically hard violations or fraud findings.
3. An unresolved mandatory fact remains uncertain. A plausible explanation cannot satisfy it.
4. Ordinary uncertainty follows the confirmed effective policy: `ask -> step_up`, `decline -> decline`, `approve -> approve`. All current challenge scenarios request `ask`. Preserve the general contract rather than silently changing an `approve` mandate to `ask`.
5. Any security veto outside that uncertainty policy must be an explicit issuer/service restriction or confirmed policy rule, agreed and documented before implementation. Neither novelty nor a model probability creates an undeclared veto.
6. With no failures or unresolved required checks, approve. A low-risk history score cannot clear a failed or unknown requirement.

Populate customer messages and reason codes from check records using deterministic templates. Show model distributions and source references on the judge panel; do not ask Jev to invent an explanation.

Business uncertainty and execution failure are different states. Unknown return terms after successful extraction may require a customer answer. A timeout, malformed output or failed data lookup raises and is logged; no default score, no automatic `step_up`, and no fabricated decision are substituted. A model-enabled failure must not submit an approval. The runner surfaces the missed-decision/deadline outcome truthfully, according to the simulator contract.

## 9. Proposed interfaces and contract work

These are proposals, not existing models:

- `HistoryFeatures`: authorized scope, as-of timestamp, feature-schema version, values, missingness and support counts.
- `BehaviorAssessment`: historical-decline score, model/calibration version, support metadata and whether the approved escalation rule fired.
- `SemanticAssessment`: model/prompt version, per-question/per-line distributions, selected outcomes and evidence references.
- `AssessmentBundle`: authorization ID, purchase digest, effective-policy version/hash, state revision, as-of time and successful assessment outputs.
- `assess(...) -> AssessmentBundle`: bounded preprocessing and model execution outside the pure evaluator.
- `evaluate(event, effective_policy, state, facts, assessments) -> Decision`: deterministic composition, rejecting stale/mismatched bundles.

A contract PR is needed before dependent implementation. It must settle the local effective-policy overlay versus frozen run snapshot, shared mutation/submission coordinator, unresolved-write reconciliation, per-line identity (`line_no` plus `item_id`), full derived-fact dependency provenance, evidence-reliance setting, extra assessment metadata, async extraction and absolute-deadline budgets, typed failure reporting and step-up binding. Existing `PurchaseFacts` has only `item_id`; repeated instances of an item must not be conflated.

The plan does not change the public app response shapes or the simulator payload. Proposed evidence additions and reason codes need agreement with app and runner before merge.

Remove the stale `facts=None` timeout convention in `docs/contracts.md` and the automatic `engine_timeout -> step_up` path in plan 05 through that agreed contract work. Both conflict with the current no-fallback rule. Missing business facts remain explicit values within a successful extraction result.

## 10. Work packages and order

Proposed scope decision: Friday 2026-09-25 at 09:00 CEST, owned by David, before the 10:30 live dry run. The first model-enabled release target is exact policy enforcement, personal-history features in evidence, and bounded Jev semantic assessments under approved reliance rules. Behavioural-model fitting/calibration is an offline deliverable first; learned history effects require a separate explicit promotion at the cutoff. Agent justifications and external dataset expansion are outside this first release.

If the model-enabled path misses a prerequisite, David must explicitly select a smaller fixed release or delay it. Do not silently change the running configuration. No configured model call can disappear when it fails. The deadline is a proposed planning cutoff, not a claim that these tasks already have capacity or are committed by the other owners.

Prerequisite ownership for agreement: David owns engine contracts, profiles, Jev integration, behavioural experiments and runner coordination/deadlines; Oskar owns policy evidence-reliance support and extraction provenance/async changes; Rishabh owns app evidence and customer-facing state labels. Each affected owner must accept the interface work before step 1 is complete. The engine reviewer cannot authorize another lane's work.

| Step | Work | Owner | Evidence before moving on |
| --- | --- | --- | --- |
| 1 | Agree assessment/effective-policy interfaces and trust rules; establish package/dependency setup where missing. | engine with policy, extract, runner, app | Contract proposal agreed, then its own reviewed PR. No implementation depends on an unmerged interface. |
| 2 | Implement exact rule evaluation, state transitions and card/user history feature construction. | engine | One manual sequence showing scope isolation, rolling spend and duplicate handling; evidence in plan Log. |
| 3 | Fit and compare logistic regression/CatBoost on the frozen additional-history splits. | engine | Dataset/split manifest and separate calibrated, held-out metrics; no fraud claim. |
| 4 | Build the pinned Jev adapter, bounded evidence input and per-line questions. | engine with extract | Real provider run recording outputs, latency and error behaviour; no mock mode. |
| 5 | Compose successful assessments in the evaluator; connect deadline/version checks in runner. | engine with runner | Replay output plus one real end-to-end request; no swallowed model error. |
| 6 | Review threshold trade-offs and evidence-reliance policy before activating learned decision effects. | David with affected lane owners | Explicit selected settings, versions and rationale. A reviewer approval does not supply customer consent. |
| 7 | Add optional agent-justification input; assess whether it adds independent information. | engine with runner/app | Purchase binding and claim-support examples; report the absence of real justification labels. |
| 8 | Broaden text evaluation with ESCI and WebShop if time remains. | engine/evaluation | Source/licence record, fixed split and reviewed task mapping. No external dataset download is required for steps 1-6. |

Proposed code locations: `src/leash/engine/` for rules, profiles, behavioural inference, semantic adapter and composition; shared models under `src/leash/contracts/`; offline scripts under `scripts/`; manifests and reports under `docs/eval/`. Model weights and caches stay in ignored storage. The runner retains exclusive access to the challenge bearer key. Provider credentials are separately scoped, never placed in serialized assessments or logs.

The implementation order prioritizes an executable deterministic path and measurable additions. If a release omits a learned component, document that fixed scope before deployment. Do not build a runtime path that silently drops a configured component after failure.

## 11. Evaluation without adding test suites

Follow AGENTS.md: no unit-test files, no test suite and no linter. Use ordinary offline evaluation scripts, one-off manual exercises and the actual replay. Record commands and observed output; planned checks below are not completed checks.

Compare fixed configurations: exact rules; rules plus Jev; rules plus history; all components. Each configuration is declared before the run and must complete successfully. This comparison is an experiment, not a production failover mechanism.

For the 45 public attempts, report known-policy-violation approvals, unnecessary declines, escalation rate, every disagreement with reviewed labels, and p50/p95/p99 latency for each stage and the full pipeline. Publish counts alongside percentages. Do not tune on this replay and then describe it as held-out evidence. If it influences design, label the result a development/integration replay and reserve separately authored cases for the later check.

The policy-compliance label set must include the confirmed instruction, cart, admissible facts, earlier accepted decisions and reason for the expected outcome. Have a person reconcile independent labels before looking at classifier outputs. Start with a few hundred reviewed policy/cart cases if time permits; this is a work estimate, not a statistical assurance. Keep variants of one underlying request/product in the same partition.

For a manual walkthrough, include two users with different amount baselines, two cards under one user, a new user with valid empty history, a known budget breach, missing return terms, and a repeated item on two cart lines. Include a catalogue-trusted product type combined with a merchant-stated matching size under a policy that has not accepted merchant size evidence: the mixed-provenance match must remain uncertain.

Exercise tightening/revocation concurrent with approval, customer approval after another purchase consumed budget, a stale policy-bound result, duplicate delivery and restart with an unresolved dispatched write. Verify declared ordering and reconciliation, without claiming the simulator cancelled an existing purchase. Finally run the actual provider pipeline with delayed event delivery and one real provider/configuration failure. Verify bounded elapsed time and visible execution failure without a fabricated decision. Exact budget checks remain decisive in every configuration.

Use [Amazon ESCI](https://github.com/amazon-science/esci-data) for product-request relevance, with its official query-based split. An ESCI complement is not an authorized add-on. [WebShop](https://github.com/princeton-nlp/WebShop) offers richer shopping requests; confirm dataset-specific reuse terms. Neither is a complete payment-authorization label set. Do not pool fraud labels from IBM/IEEE-CIS with our historical approval/decline target.

No production-safety, conformal-risk or calibrated-payment-probability guarantee follows from these small synthetic evaluations.

## 12. Readiness and stop conditions

- The plan is ready for implementation only after independent review and the user's go-ahead.
- Required cross-lane contracts and evidence-reliance rules must be agreed before model-assisted approval.
- Required model/provider access must work before enabling that configuration. No alternate provider or canned response is substituted.
- The owner selects thresholds before learned escalation affects customers. Historical model metrics alone cannot validate consent or semantic compliance.
- Real cardholder data requires a separate privacy/retention assessment. During the hackathon, use the supplied fictional data and minimize provider inputs.
- A plan or benchmark review does not authorize deployment, merging unrelated PRs, or scheduling background jobs.

## Sources

- Local base-pack definitions: `viseca-2026/data/README.md`, `data_dictionary.md` and `schemas/authorization_event.schema.json`.
- Local additional history: `viseca-2026/additional-data-history/README.md:63` and `metadata.json`.
- [Jev models and limits](https://docs.typesafe.ai/models.md), [known limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [confidence](https://docs.typesafe.ai/confidence), [API](https://docs.typesafe.ai/api.md).
- [LiteLLM routing benchmark](https://docs.litellm.ai/blog/jev-auto-router-benchmark). Task-specific latency evidence, not payment validation.
- [Independent Jev calibration study](https://github.com/scienthoon/jev-ood-calibration). Different tasks and model output types require local validation.
- [CatBoost feature handling](https://catboost.ai/docs/en/features/categorical-features).
- [Chronological transaction-model validation](https://fraud-detection-handbook.github.io/fraud-detection-handbook/Chapter_5_ModelValidationAndSelection/Introduction.html).
- [AP2 specification](https://ap2-protocol.org/ap2/specification/) and [Verifiable Intent security model](https://verifiableintent.dev/spec/security-model/). Authorization binding and stateful limits remain separate responsibilities from text classification.

## Log

2026-09-24 david_orch: wrote proposal from source research, measured dataset counts and current policy/extract contracts at e7e2b0e. No model fitted, no provider inference called and no implementation changed.

2026-09-24 david_orch: independent review blocked initial SHA-256 c464d919c58a1543b897727f7130c011befb2de46c3b8503e64483a076d3b835 on composite provenance, policy-mutation ordering and unenforced end-to-end deadlines. Verified the cited extractor and simulator documentation; revised those requirements and added calibration/cold-start/parity checks plus a proposed dated release cutoff. Revision submitted to the same reviewer; verdicts are recorded separately in 02-classifier-review.md so this plan's reviewed fingerprint stays stable.
