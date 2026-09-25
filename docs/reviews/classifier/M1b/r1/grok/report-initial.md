# Classifier M1b r1 review

Verdict: BLOCK

Target head: `e4ba7ba1f0707164ddfd6071779501a880598b44`
Base: `76363be7ce299856fb2073684a91aeb80b6559a1` (`classifier: use shared assessment contracts in replay`)
Manifest: `docs/reviews/classifier/M1b/r1/MANIFEST.sha256`, 22/22 OK before review and 22/22 OK after review. Working tree clean both times. A changed head voids this verdict.

Scope of this verdict: the frozen shared-evaluator integration cut named by `docs/eval/classifier/m1b-report.md`. It is not an approval of live model effects, runner hookup, or M4.

Model pin: grok-4.7, from `cotal_orientation` (`COTAL_MODEL` / the agent file) and from the launch log (`model grok-4.7 is served by provider cliproxy via openai-compatible:cliproxy`). Requested effort: high (persona `variant: high`). Accepted provider tier: not observable in this seat. The requested tier was not omitted or replaced.

Lens: authorization, prompt injection, evidence provenance, policy and state races, user isolation, failure handling.

## Blocker

### B1. Caller-supplied behaviour and semantic outputs are not bound, and a forged escalation changes an approve into a step-up

`assessment_purchase_digest` hashes the authorization, mandate id, customer id, card id, and history features. It does not hash `behaviour` or `semantic`.

```108:118:src/leash/contracts/classifier.py
def assessment_purchase_digest(event: Event, features: HistoryFeatures) -> str:
    """Bind purchase and feature content locally; this is integrity checking, not authentication."""
    payload = {
        "authorization": event.authorization.model_dump(mode="json"),
        "mandate_id": event.mandate.mandate_id,
        "customer_id": event.mandate.customer_id,
        "card_id": event.mandate.card_id,
        "features": features.model_dump(mode="json"),
    }
```

`validate_assessments` checks that digest, then `model_checks` trusts `escalation_fired`, `score`, `support`, and the Jev selection as decision inputs. `BehaviorAssessment` has no validator that the flag was set by an approved operating rule. `docs/contracts.md:195` says `escalation_fired` is set only by a separately approved operating rule. The evaluator does not enforce that.

`assess` scores features and then reuses the feature-only digest, so a later edit of the score is still valid:

```49:57:src/leash/engine/classifier/assess.py
    base = history_bundle(event, policy, history)
    behaviour = behaviour_model.score(base.features) if behaviour_model is not None else None
    semantic = await assess_jev(base.features, event.deadline_at, api_key=api_key)
    result = AssessmentBundle(
        authorization_id=base.authorization_id, purchase_digest=base.purchase_digest,
        policy_hash=base.policy_hash, as_of=base.as_of, features=base.features,
        behaviour=behaviour, semantic=semantic,
    )
```

Contracts are `frozen=False` (`src/leash/contracts/_base.py:18`), so `model_copy` can set the flag after a real score.

Observed on AU0001 (SCEN0000, customer CU0001, card CA0001), using the checked-in evaluation-only artifact:

- `BehaviorModel.score` returned score `0.029953`, `escalation_fired=False`.
- `evaluate` with the model-off history bundle returned `approve` / `within_policy`.
- The same bundle with that score copied and `escalation_fired=True` kept the same `purchase_digest` and passed `validate_assessments`.
- `evaluate` then returned `step_up` / `model_history_uncertain`.
- Replacing `support` with `{"not_a_real_feature": 9}` and `score` with `0.99` was also accepted. The model check value contained `not_a_real_feature` and `0.99`. The decision was again `step_up`.

Cross-customer: the real CU0001 score object (`0.029953`, artifact `e4815c567707`) was attached to AU0012 (CU0006). AU0012's digest did not change. `validate_bundle` and `validate_assessments` both accepted it. The decision evidence quoted CU0001's score.

On AU0012, forging `escalation_fired=True` added `model_history_uncertain` to the existing `item_mismatch` and `return_terms_missing` step-up. On AU0004, a model pass (`escalation_fired=False`, both Jev answers `ordinary`) left the hard `amount_over_limit` decline in place. A model pass therefore does not clear a hard fail. The hole is the other direction: an unbound flag creates uncertainty, and under the ask policy that uncertainty changes approve to step-up.

Failure scenario: any caller that can pass `assessments` to `evaluate` (today `scripts/classifier_replay.py` and `assess`) can copy a behaviour object from another customer, or set `escalation_fired` without the O4 rule, and force `model_history_uncertain`. The purchase digest still matches. The live runner does not pass assessments yet (`src/leash/runner/loop.py:158` submits `evaluate(event, policy, state, facts)`), so this is not a live decision today. It is already on the integration surface this cut asks to be reviewed, and `docs/contracts.md:222` states the evaluator compares the digest before composing a decision. That comparison does not cover the fields that change the outcome.

Required fix: include behaviour and semantic in the binding the evaluator recomputes, or reject non-null behaviour and semantic in this model-off cut. `escalation_fired=True` must be rejected until an approved operating rule sets it. Behaviour `support` must match the feature-map keys. A score produced for one customer must not validate on another customer's bundle.

## Checked, not blocking

- Model-off parity. For all 45 public attempts, with the five supplied drafts and real `extract_event` facts, `evaluate(..., assessments=history_bundle)` matched `evaluate(..., assessments=None)` on decision and reason codes. Zero mismatches. No model-sourced check appeared. The saved comparison file `/private/tmp/classifier-shared-replay-20260925.csv` has SHA-256 `d8903bba8ddc57270b691ae878048f0b145a8f2c3822340cc7131fa353f9be6f`, matching `m1b-report.md`. Its stable fields match `docs/eval/classifier/m1-all-45.csv` (11 approve, 32 decline, 2 step-up). I did not rerun `scripts/classifier_replay.py` because it writes a new CSV.
- Identity binding that is enforced. Cross-customer features, a foreign customer id, a stale policy hash, a shifted `as_of`, a wrong authorization id, an amount changed after the digest, a lookalike object, a dict, a state mandate mismatch, and an authorization card that differs from the mandate all raise in `validate_assessments`. `history.for_event` refuses an authorization card that differs from the mandate (`history.py:262-265`).
- History isolation. CU0001's 238 index rows and CA0001's 122 rows contain no foreign customer or card. On 300 additional-pack purchases, `customer_approved_purchase_count` matched a strict key `< (timestamp, authorization_id)` count. Card and customer scopes stay separate: AU0004 is 119 card versus 229 customer, and the extra 110 are the customer's other card CA0002, which is the declared customer scope.
- Injection. With a `contains_instructions` fact whose `item_id` matches the cart line, quarantine clears the extracted fields (`evaluate.py:29-36`) and the injection check stays `uncertain` (`checks.py:220-225`). An ordinary Jev pass does not remove `injected_instructions`. AU0001 stays `step_up`. A fact with a non-matching item id does not trip the check. That matching rule is pre-existing and is not introduced by this cut.
- Hard fail versus model pass. AU0004 stays `decline` / `amount_over_limit` when behaviour escalation is false and both Jev answers are `ordinary`.
- Contract revalidation. `validate_assessments` copies through `model_validate` (`model_checks.py:17`). A `model_copy` that plants a negative support count, a missing support key, or a missing-reason on a present value is rejected there. NaN cannot be digested (`allow_nan=False`). Lookalike types raise `TypeError`.
- Jev response checks, not called. The adapter rejects a non-200, a body over 64_000 bytes, a model or provider other than the pin, duplicate JSON keys, a bad probability map, a choice that disagrees with the local argmax, and a tie that is not left uncertain (`jev.py:63-107`). No provider call was made. `assess_jev` still sends only numeric history (`jev.py:120-130`).
- Behaviour artifact gate. `BehaviorModel` refuses a non-evaluation release status, a non-proposal threshold status, a path outside the repo, a hash mismatch, and a feature-name mismatch (`behaviour.py:32-65`). `score` returns `escalation_fired=False` (`behaviour.py:99`). The manifest hash of `model-evaluation-only.joblib` matches. The hole is not the loader. It is that `evaluate` accepts a behaviour object the loader did not produce.
- Replay does not call `assess` and does not invent a customer answer. The live runner still has no classifier reference.

## Non-blocking

N1. `PolicyDraft.hash` is a stored field (`src/leash/contracts/policy.py:91`). `model_copy` of the rules or `uncertainty_policy` keeps the old hash. On the AU0004 policy, copying the amount limit to `0.01` left the hash unchanged, `validate_assessments` accepted the original bundle, and `evaluate` applied the copied rules (`period_limit_exceeded` appeared). The store's `draft_hash` would have differed. This is a general contract property, not introduced by the classifier digest. The runner still does not recompute `draft_hash` at evaluation time. Owner: policy or engine, before M4 treats `policy.hash` as proof that the rule objects were not replaced in memory.

N2. `handle` loads state under `mandate_lock`, then calls `evaluate` outside the lock (`src/leash/runner/loop.py:206-222`). A concurrent approval can be missed, and the same authorization can be submitted twice before `record_accepted`. The M1b report already says the model-off replay does not exercise runner locks. Not a new M1b defect. Owner: runner, before live assessment.

N3. `state.load(mandate_id, customer_mandates)` trusts the caller to name only that customer's other mandates (`state.py:40-60`). A wrong id would import another customer's approvals into period rules. The M1b path does not call `load`. Owner: runner, when it fills `customer_approvals`.

## Commands actually run

- `git rev-parse HEAD`, `git status --porcelain`, `git log -1`, `git rev-parse HEAD^`, before and after.
- `shasum -a 256 -c docs/reviews/classifier/M1b/r1/MANIFEST.sha256` before and after. 22/22 OK both times.
- `cotal_orientation`, `cotal_inbox`, `cotal_channels`, `cotal_leave` on announce and the spine, `cotal_join` on `team.zurichbuchegg.classifier.review`.
- Read-only Python 3.13.5 from `/Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python` with `PYTHONPATH=src:scripts`. Probes constructed events from the public pack and the five supplied drafts, called `HistoryIndex`, `history_bundle`, `BehaviorModel.score`, `validate_assessments`, and `evaluate`. No `assess_jev`, no HTTP, no simulator, no `uv sync`, no writes in the grading tree.

## Limitations

- Accepted reasoning effort is not visible from the seat. The pin and the requested high tier are.
- The 45-row parity check called `evaluate` in-process. It did not execute `scripts/classifier_replay.py`, because that script writes a CSV.
- No live runner, no provider, and no second process for the lock race. Those limits are the ones the M1b report states.
- Peer verdicts on the review channel were not used as evidence.

## Observed outcome

HEAD stayed `e4ba7ba1f0707164ddfd6071779501a880598b44`. Manifest stayed 22/22. The model-off history bundle does not change the 45 decisions. The evaluator still accepts an unbound behaviour object, and setting `escalation_fired` on a real score changes AU0001 from approve to step-up without a digest change.
