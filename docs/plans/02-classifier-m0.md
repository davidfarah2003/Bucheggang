# Classifier M0: re-anchor on main, scoped contract proposal, ownership map

Milestone M0 of `docs/plans/02-classifier-handoff.md`. Written by classifier_manager_live on 2026-09-24.

Base: `lane/classifier` at the merge of `origin/main` `ed2bc3c` (runner PR #25 merged). The approved design `docs/plans/02-classifier-design.md` is unchanged at SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`. This file adapts that design to what has landed on main since its review. Where they differ, this file says which one wins and who has to rule.

Nothing in this file is implemented. Items marked "owner ruling" are open until the named person answers.

## 1. What main now says about models in the decision path

Main carries two rulings that postdate the design review.

- `docs/idea/viseca-agent-control-layer.md:155`: "No language model reads merchant text or fills the form on the backend's behalf. [...] A bounded classifier over the customer's own purchase history (the Jev decision classifier [...]) may add a risk signal in step 8; it never overrides a deterministic check and never reads merchant text." Step 8 (line 151) is "Evaluate merchant, device, session, and behavioural risk."
- `docs/idea/viseca-agent-control-layer.md:170`: "No model call over untrusted content in the decision path. A model that fails or times out raises and is logged; there are no fallback paths."
- `docs/models.md:30`: "The one model in the decision path is the Jev history classifier [...], which reads the customer's own history and adds a risk signal."

Consequences for the design:

1. The design's section 6 question table (purpose, extra item, substitution, justification) assumes Jev reads cart lines. Under the ruling, `item_details`, `purchase_description` and any other merchant-authored text never reach Jev. This is settled by main and needs no further ruling.
2. Catalogue fields are a separate case. `item_name` and `item_category` on the event are equal to the catalogue values on all 56 public attempt lines (checked against `viseca-2026/data/items.csv`), and `extract/facts.py` already records them as source `structured`. Whether Jev may read catalogue `item_name` and `item_category` next to the confirmed requirement is **owner ruling O1** (David, with Oskar for extraction). Until O1 is answered, M3 designs Jev inputs from history only.
3. Jev output is a risk signal in step 8. It never flips a deterministic `decline` to `approve`, and it never satisfies a required fact (design section 8 rules 1, 3 and 6 already say this). Under the current ruling it cannot count toward satisfaction at all, so the design's "customer-confirmed evidence-reliance rule" (section 6, last paragraphs) is out of scope for the first release. A model result can only move a decision toward `step_up` under the mandate's uncertainty policy.
4. The behavioural model of design section 5 (LR vs CatBoost over history, M2) is unaffected. It reads history only.

## 2. Exact-name inequality versus semantic mismatch

The extractor's `matches_request` is an exact compare of normalized names. `_product_type` (`src/leash/extract/facts.py:40-47`) collapses whitespace and lowercases, and line 125 sets `matches_request = product_type == target`. The runner builds the target from the confirmed draft's `=` rules on `facts.product_type` and `facts.size` (`src/leash/runner/loop.py:136-142`).

The scenario instructions do not use catalogue names:

| Scenario | Instruction wording | Catalogue names in the carts |
| --- | --- | --- |
| SCEN0000 | "ordinary grocery item" | Fresh produce selection |
| SCEN0001 | "household groceries" | Fresh produce selection, Breakfast supplies, Weekly grocery basket, Pantry staples, Fragrance and beauty gift |
| SCEN0002 | "road-running shoes" | Road-running shoes, Trail-running shoes, Extended protection plan, Cycling helmet |
| SCEN0003 | "clothing" | Everyday jacket, Seasonal clothing order, Everyday waterproof jacket, Rain coat |
| SCEN0004 | "27-inch monitor" | 27-inch computer monitor, Extended protection plan, Digital gift voucher |

Run on this base with `scripts/classifier_m0_exact_name.py`, which drafts the SCEN0004 rules (amount <= CHF 400, `facts.product_type = <name>`, `history.merchant_seen_on_card = true`, uncertainty policy `ask`) and calls the merged `extract_event` and `evaluate` on an empty mandate state:

```
uv run python scripts/classifier_m0_exact_name.py "27-inch monitor"
AU0035 decline item_mismatch | matches_request [('IT0017', False, 'structured')]
AU0036 decline item_mismatch | ...
AU0038 decline item_mismatch | ...
AU0042 decline item_mismatch | ...
AU0045 decline item_mismatch | ...
AU0039 decline item_mismatch,unfamiliar_merchant,lookalike_merchant
AU0044 decline item_mismatch,unfamiliar_merchant
(AU0037, AU0040, AU0041, AU0043 unchanged between the two runs)

uv run python scripts/classifier_m0_exact_name.py "27-inch computer monitor"
AU0035 approve within_policy | matches_request [('IT0017', True, 'structured')]
AU0036, AU0038, AU0042, AU0045 approve within_policy
AU0039 decline unfamiliar_merchant,lookalike_merchant
AU0044 decline unfamiliar_merchant
AU0037 decline amount_over_limit
AU0040 step_up item_mismatch,injected_instructions (matches_request True)
AU0041 decline amount_over_limit,item_mismatch,unrequested_item,subscription,protection_plan
AU0043 decline item_mismatch,gift_card
```

With the instruction's own words, all five ordinary monitor purchases decline `item_mismatch`. With the catalogue name they approve. The mismatch is a wording gap between the instruction and the catalogue. The cart is the requested product.

AU0040 steps up with `item_mismatch` even when `matches_request` is True. `evaluate.py:28-33` quarantines every fact on a line that `contains_instructions`, so the `facts.product_type` rule is uncertain, and `rules.py:260` maps that rule to the `item_mismatch` code whether it failed or was uncertain. The decision is correct under `ask`; the reason label overstates it. This is an engine observation for engine_builder, not classifier work.

Proposal. The fix belongs in the policy lane, and it needs no model: at confirmation the customer picks or confirms the catalogue product name, and the draft stores that exact name in the `facts.product_type` rule. A semantic assessment (a model deciding "27-inch monitor" means "27-inch computer monitor") would need O1 and a reliance rule, and it would still sit behind the deterministic `decline`. **Owner ruling O2** (Oskar, policy): drafts carry catalogue names confirmed by the customer. The classifier does not own this change and will not make it.

B1 is still open on main: `facts.py:130` sets `sources["matches_request"] = sources["product_type"]` while size also contributes at lines 126-128. Extraction owner is Oskar. The classifier depends on it only if O1 lets a model read line facts.

## 3. Dependency provenance

`src/leash/contracts/decision.py`:

- `FactSource = Literal["agent_form", "structured", "merchant_text"]` (line 31).
- `Check.source: Literal["event", "history", "agent_form", "merchant_text", "state"]` (line 55). There is no value for a model assessment.
- `PurchaseFacts` (line 34) keys a line by `item_id` only. There is no `line_no`, so two lines with the same item are not distinguishable in facts.

Proposal P1, an engine-owned contract change that the classifier lane may draft as a separate PR under the engine owner's review. The boundary was confirmed on `contracts` after r1 froze:

- Add `"model"` to `Check.source`. A check built from a behavioural or Jev assessment carries it, plus the model id and artifact or snapshot version in its evidence.
- Defer `line_no` on `PurchaseFacts` until O1 allows line inputs. The history classifier does not need it.
- Per-field dependency lists for derived facts (design section 6) wait on O1. If Jev never reads line facts, the classifier has no need for them and the item stays with extraction as B1.

## 4. Where the classifier plugs in

`evaluate(event, policy, state, facts)` (`src/leash/engine/evaluate.py:42`) is pure: no network, no model call. The design keeps it that way (section 9): `assess(...) -> AssessmentBundle` runs first, outside it, then the evaluator composes.

Proposal P2. The engine owner confirmed the module boundary and conditional interface on `team.zurichbuchegg.contracts` after the r1 target was frozen. The proposed contract change remains unmerged:

- New subpackage `src/leash/engine/classifier/`, owned and written only by the classifier lane:
  - `history.py`: `HistoryFeatures` built from pre-event rows, with separate card and customer scopes.
  - `behaviour.py`: loads one versioned artifact and scores `HistoryFeatures`. Loading fails at startup when the artifact is missing or its schema differs.
  - `jev.py`: the provider adapter (section 7).
  - `assess.py`: `assess(event, state, as_of) -> AssessmentBundle`.
- `evaluate()` gains one optional argument, `assessments: AssessmentBundle | None = None`. `None` means the model-enabled configuration is off, a release setting fixed at startup. It never means a model failed; a failure raises before `evaluate` is called. The classifier lane drafts the engine-owned edits in `evaluate.py` and `checks.py` as a separate PR for the engine owner to review and merge. A model check returns `pass` or `uncertain`, never `fail`; it cannot decline alone or overturn a deterministic failure. `AssessmentBundle` moves into `src/leash/contracts/` with a matching `docs/contracts.md` entry in that PR. The engine owner has held integration on main until after the 12:00 submission freeze.
- Offline scripts are `scripts/classifier_*.py`. Split manifests, artifacts and reports go under `docs/eval/classifier/`.

Engine history today (`src/leash/engine/data.py:32-57`) holds approved purchases per card, from the base pack only (line 78). Checks call it with `auth.card_id` (`checks.py:100, 113, 138, 200`). The classifier reads the same CSVs through its own module and does not change `History`.

## 5. History scopes and data

Design section 4 keeps card, customer and mandate scopes apart. Live identity comes from the mandate (`event.mandate.customer_id`, `event.mandate.card_id`), never from an agent-supplied field.

The scenario customers hold two cards each (from `cards.csv` joined to `accounts.csv`): AUTH0001 and AUTH0002 are CU0001 on CA0001 (also holds CA0002), AUTH0003 CU0006 on CA0011 (CA0012), AUTH0004 CU0012 on CA0023 (CA0024), AUTH0005 CU0019 on CA0039 (CA0038). Customer scope therefore differs from card scope for every scenario.

| Pack | Rows | Customers | Cards | Span | Purchases | Declined purchases |
| --- | --- | --- | --- | --- | --- | --- |
| base `viseca-2026/data` | 4701 | 20 | 41 | 2025-09-01 to 2026-07-31 | 4565 (4112 human, 453 agent) | 258 |
| additional `viseca-2026/additional-data-history` | 144674 | 500 | 832 | 2025-09-01 to 2026-07-31 | 140096 (121059 human, 19037 agent) | 8154 |

The 45 public attempts run 2026-08-09 to 2026-08-22, after both history spans. The two packs share no customer or authorization ID. Per design section 5, the model is fitted on the additional pack only, and the 20 base customers serve only as profile history at inference.

## 6. Mutation coordination and the local overlay (R1)

What landed:

- Runner (#25, on main): one flock per mandate at `data/locks/<mandate_id>.lock` (`src/leash/runner/records.py:51-59`). `handle()` takes it to load state (`loop.py:215-216`), releases it, runs extract and evaluate, calls `submit()` with no lock held (`loop.py:239`), then takes it again to record (`loop.py:241-245`). `StepUpBook.answer` and `sweep` hold it across `/resolve` and the record.
- App (#26, on main): `MandateEdits` keeps its own flock at `<draft store root>/../mandate_edits/<mandate_id>.lock` (`src/leash/api/mandates.py:64-93`). `tighten_mandate` and `revoke_mandate` PATCH or revoke on the simulator under that lock (`mandates.py:177-212`). Nothing in `src/leash/runner` reads `mandate_edits`.
- Neither path writes an intent record before its remote write. The runner Log for task 6 names the gap: a crash between an accepted submit and `record_accepted` leaves the ID out of state, and a restart resubmits it.

Gaps against design section 3 and R1:

1. Two locks guard one mandate. A tighten or revoke can run while `handle()` is between its evaluate and its submit, so an approval computed under the old policy can go out after the customer's tightening was acknowledged.
2. The runner evaluates against the confirmed draft it was started with (`--draft`). App-side edits never reach it.
3. No submission or mutation intent is persisted, so a timed-out write cannot be marked unresolved.

Proposal P3, owned by runner_builder and the app lane (Rishabh), with David ruling on semantics (**owner ruling O3**):

- One lock per mandate for every write path: the runner's `records.mandate_lock`. The app's tighten and revoke take it too.
- `handle()` holds it from the final policy and state recheck through `submit()` and `record_accepted()`.
- An intent file is written under the lock before each submit, `/resolve`, PATCH or revoke, and marked done after the recorded outcome. On restart an open intent blocks approvals for that mandate until reconciled through `GET /v1/authorizations` for decisions, or `GET` mandate plus the overlay revision for mutations.
- The runner reads the effective policy (draft plus `mandate_edits`) at the recheck.

O3 is the design's open question: does a later tightening apply locally to runs already started, whose simulator snapshot is frozen? The classifier needs the answer, since assessments bind to a policy version. It will not implement P3; those files belong to runner_builder and the app lane.

## 7. Deadlines (R2)

On main:

- `EXTRACT_CAP_S = 1.5` and `EXTRACT_RESERVE_S = 2.0` (`src/leash/runner/loop.py:43-44`). A missed extract budget declines with `engine_timeout` (`_extract_timeout_decision`, `loop.py:120`, used at 232-234). A missed evaluate budget submits `step_up` with `engine_timeout` (`_engine_timeout_decision`, `loop.py:104`, used at 170-175 and logged at 246-247). Both are substitute decisions after an execution failure. Design section 8 and AGENTS.md section 6 say a failure raises.
- `docs/contracts.md:177` still reads "`facts=None` means the extract lane did not answer in time". The design asks for it to be removed.
- Budgets use `future.result(timeout=...)` on a thread pool, and the runner Log records that the worker keeps running after the guard fires. The simulator client uses one 30 s timeout per call (`src/leash/runner/api.py:3, 33`), with no absolute deadline.
- Step-ups: `expires_at = accepted_at + step_up_timeout_seconds - 5 s` (`src/leash/runner/stepups.py:40, 59-60`), read from bootstrap (`human_window_s`, line 51). The window follows `technical_details.md:350` (default 120 s, read from `/v1/bootstrap`). `answer()` checks expiry against `expires_at` (line 172), so an automated `deadline_at` never rejects a timely human answer. This half of R2 holds on main.
- `answer()` resolves an approve without re-evaluating budget or state (`stepups.py:162-181`). Design section 3 step 7 requires that re-evaluation, since another purchase may have spent the budget while the customer decided.

Proposal P4, owned by runner_builder:

- Replace the two `engine_timeout` substitute decisions: a missed budget raises and is logged, and the simulator records its own timeout. Remove `docs/contracts.md:177`.
- One absolute budget from `deadline_at` minus 250 ms, with a 2 s reserve for recheck, submit and record, as in design section 3. Jev and extraction get their slices from it. A nonpositive slice raises a named error before dispatch.
- On a customer approve, re-run the budget and state checks under the mandate lock before `/resolve`. If they now fail, `/resolve` sends `decline` with the failing reason.

The classifier's own calls (Jev in M3) will use `httpx.AsyncClient` under `asyncio.timeout_at` with the slice P4 hands it, so it can land before P4. The behavioural model is local and bounded by its own measured latency.

## 8. R3: provider-selected option versus probabilities

The Jev response carries both a `choice` and a probability map. Rule for the adapter, in `jev.py`:

- Validate full coverage of the requested questions, exact option keys, no duplicates, finite probabilities in [0, 1], and a sum within 1e-6 of 1. Anything else raises `JevResponseError`. Nothing is renormalized.
- The selected option is the local argmax. If the provider's `choice` differs from it, raise `JevResponseError`. A malformed response is an execution failure, so it never reaches `uncertainty_policy=approve`.
- An exact tie at the top is a valid response. It yields an uncertain check.

## 9. Provider and model pin

The first live calls used `scripts/classifier_m0_jev_probe.py` with one small catalogue-field question per call, no history and no merchant text. That version of the script did not send a provider restriction, so those calls establish served model names only. Grok's r1 report found the gap. The script now sends `provider: {"only": ["typesafe"], "allow_fallbacks": false}`. A new call exercised the restriction. The key is `OPENROUTER_API` in the main checkout `.env` and was not printed:

| Requested model | HTTP | Latency | Served model |
| --- | --- | --- | --- |
| `typesafe/jev-1.13-20260917` | 200 | 348 ms, 501 ms | `typesafe/jev-1.13-20260917`, provider TypeSafe |
| `typesafe/jev-1.13` | 200 | 684 ms | `typesafe/jev-1.13-20260917` |
| `~typesafe/jev-latest` | 200 | 334 ms | `typesafe/jev-1.13-20260917` |
| `jev-1.13.0` (design section 6 name) | 400 | | "Model typesafe/jev-1.13.0 does not exist" |
| `typesafe/jev-1.13-20260917`, provider pinned, fallbacks off (r2) | 200 | 478 ms | `typesafe/jev-1.13-20260917`, provider TypeSafe |

The 501 ms call used 379 input and 40 output tokens at a cost of 1.5918e-05. The r2 call used the corrected script and produced HTTP 200, served model `typesafe/jev-1.13-20260917` and provider `TypeSafe`. Its response is retained outside the repository at `/private/tmp/classifier-m0-r2-jev-probe.log`; no credential value appears there.

Pin: `POST https://openrouter.ai/api/v1/systemone` with `model: "typesafe/jev-1.13-20260917"` and `provider: {"only": ["typesafe"], "allow_fallbacks": false}`. If the response names a different model, the adapter raises. The design's `jev-1.13.0` does not exist on this route. The dated snapshot is the same release, so M3 treats this as a name correction. These calls are not a latency measurement; M3 measures under the real deadline.

## 10. Dependencies for M2

`pyproject.toml` lists fastapi, httpx, mcp and pydantic. M2 needs numpy, scikit-learn and catboost for offline fitting. Proposal P5: add them as a `classifier` dependency group (`uv sync --group classifier`), so the runtime service does not import them. The deployed behavioural model then needs one of:

- (a) LR exported as coefficients plus the fitted preprocessing, scored in pure Python at inference, or
- (b) the chosen library in the runtime dependencies.

M2 picks after the comparison. The `pyproject.toml` change is a shared-file edit and goes by PR with a line on `contracts`. `uv.lock` in this worktree was created by `uv run`, is untracked, and stays out of commits until P5.

M2 split disposition for GLM G1: keep the design's fixed candidate selection on May, then refit the selected configuration through May. The July rows and the reserved 20% of customers do not enter selection, fitting, calibration or threshold choice. May selection and refitting reuse outcomes from the same customers, so the seen-customer July metrics are labeled selection-informed. Lead the generalization table with reserved-customer July metrics and show seen-customer July metrics separately. The split manifest records this protocol, the fixed seed and customer membership before fitting. July cannot change the candidate or operating point. The report also leads with the subset that passes deterministic checks and separates agent and human calibration and escalation rates. The zero-history slice has no examples in either supplied pack, so its outcome metrics are unavailable.

## 11. Ownership map

| Path or item | Owner | Classifier lane role |
| --- | --- | --- |
| `src/leash/engine/classifier/**` (new) | classifier lane | sole writer |
| `scripts/classifier_*.py` | classifier lane | sole writer |
| `docs/eval/classifier/**` (new) | classifier lane | sole writer |
| `docs/plans/02-classifier-*.md`, `docs/reviews/classifier/**` | classifier lane | sole writer; design file frozen at its reviewed hash |
| `src/leash/contracts/**`, `docs/contracts.md` | engine lane, coordinated by david_main | drafts only the agreed `AssessmentBundle` and `Check.source` edits in a separate classifier PR; engine owner reviews and merges |
| `src/leash/engine/evaluate.py`, `checks.py`, `state.py`, `data.py`, `rules.py` | engine lane, coordinated by david_main | drafts only the agreed `evaluate()` argument and pass-or-uncertain model check in that PR; leaves other engine code unchanged |
| `src/leash/runner/**` | runner_builder | proposes P3 and P4; does not edit |
| `scripts/replay.py` | david_orch | uses it; does not duplicate it |
| `src/leash/extract/**`, `src/leash/policy/**` | Oskar | B1 and O2 are Oskar's |
| `src/leash/api/**`, `app/**` | Rishabh | app half of P3 |
| `pyproject.toml` | shared, by PR | P5 |

## 12. Owner rulings needed

| Id | Question | Who rules | Blocks |
| --- | --- | --- | --- |
| O1 | May Jev read catalogue `item_name` and `item_category` beside the confirmed requirement? `item_details` stays excluded either way. | David, with Oskar | Optional M3 line-input extension only; history-only M3 proceeds |
| O2 | Do drafts store the customer-confirmed catalogue product name in `facts.product_type`? | Oskar (policy) | nothing in the classifier; SCEN0000 to SCEN0004 approvals |
| O3 | Does a local tightening or revocation apply to runs already started? | David | M4 policy binding |
| O4 | Operating threshold and escalation budget for the behavioural model (design section 5). | David, after the M2 June table | enabling a live effect in M4 |

## 13. Milestone sequence after M0

- M1 builds `history.py` over both packs with card and customer scopes and pre-event cutoffs; mandate state stays in the evaluator. It runs the history path once with the model effect disabled. P2's module boundary is agreed with the engine owner. Engine contract integration remains a separate PR.
- M2 is offline and needs P5. Its split and reporting follow the G1 disposition above.
- M3 uses only the customer's own history until O1 is answered. Its provider adapter and standalone assessment can run without P1; model checks in `evaluate` need the separate engine contract PR. No catalogue line input is assumed.
- M4 needs the runner/app changes P3 and P4 from their owners, an O3 policy-binding ruling, and O4 before any live behavioural-score effect. An isolated replay may exercise the off configuration without those release gates.
