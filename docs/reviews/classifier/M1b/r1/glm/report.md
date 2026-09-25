# M1b review (GLM, r1) — shared-contract model-off integration

Verdict: **APPROVE**

- Head: `e4ba7ba1f0707164ddfd6071779501a880598b44` (verified before and after; unchanged)
- Base: `49646be` (merge of main with shared P1/P2 and runner P4; head is a direct child)
- Model pin: `glm-5.3` (from orientation, COTAL_MODEL / agent file). Requested effort: max. Accepted: this review ran at full available effort; nothing was omitted.

## What was verified

The 22-path `docs/reviews/classifier/M1b/r1/MANIFEST.sha256` checked clean before and after the review (`shasum -a 256 -c`, all OK, both passes). The head tree equals the manifest's graded set: the diff from base is import moves, the `types.py` deletion, one `evaluate(..., assessments=bundle)` call, the report and the manifest itself. `model_checks.py` is byte-identical to base, so this cut adds no new decision logic.

Scope, isolation and leakage in `src/leash/engine/classifier/history.py`:

- `for_event` (258-279) takes identity from the mandate, and rejects an authorization whose card or mandate differs (262-263) and a mandate card that does not belong to the customer (264-265). Limits are read per card (266-269).
- `_prior` (163-170) uses `bisect_left` over sorted `(timestamp, authorization_id)` keys, so features are built only from rows strictly before the current purchase. An equal-timestamp earlier attempt is excluded, not leaked. Feature time equals the authorization timestamp; a same-moment history row can never be an input.
- The customer-scope profile (168-169) is keyed on customer_id; cards of the same customer feed it, but the constructor (112-114) refuses a customer that appears in two packs, and duplicate cards and authorization IDs are refused (108-109, 130-132). A cross-customer substitution is structurally impossible through `for_event`; a hand-built foreign bundle is rejected by both `validate_bundle` (`assess.py:31-40`) and `validate_assessments` (`model_checks.py:23-32`).
- Cold starts are represented, not hidden: undefined features are `None` with an explicit reason in `missing` and zero support, and the contract (`contracts/classifier.py:34-42`) requires `missing` to cover exactly the `None` values. Zero-count cold start yields a valid bundle.

Digest provenance: `assessment_purchase_digest` (`contracts/classifier.py:108-118`) canonicalizes authorization, mandate identity and the full feature map with sorted keys, `allow_nan=False` and finite-float annotations (16-17), and binds the policy hash beside it. It is integrity checking, and the docstring says so; it is not sold as authentication.

Decision precedence: with `behaviour=None`/`semantic=None`, `model_checks` produces no checks, so `evaluate` (`evaluate.py:79-90`) keeps rule failures as decline and uncertainty as the uncertainty-policy outcome. The evaluation-only model cannot escalate: `BehaviorModel.score` (`behaviour.py:99`) hard-codes `escalation_fired=False`, the loader (36-39) refuses any manifest that is not evaluation-only with proposals-only thresholds, and even a fired escalation composes only an `uncertain` check (`model_checks.py:46`), never a hard fail. The Jev adapter (`jev.py:63-107`) rejects non-JSON, duplicate keys, wrong model or provider, missing or extra questions, non-finite or out-of-range probabilities, sums off by more than 1e-6, and a provider choice that disagrees with the local argmax; ties stay `None`.

## Live checks actually run (all local, no provider or simulator request)

- `shasum -a 256 -c docs/reviews/classifier/M1b/r1/MANIFEST.sha256` — 22/22 OK, before and after.
- `git diff 49646be e4ba7ba -- <manifest paths>` — read the full cut; confirmed no stale `classifier.types` imports remain (`grep -rn "classifier.types\|from .types" src scripts` — none).
- `uv sync --frozen` and `uv sync --frozen --group classifier` — environment from the locked deps only.
- `PYTHONPATH=src .venv/bin/python scripts/classifier_replay.py` over SCEN0000/1/2/3/4 with the five supplied drafts — 45 attempts, 11 approve, 32 decline, 2 step_up. Row-by-row comparison against `docs/eval/classifier/m1-all-45.csv` on scenario, authorization, decision, reason codes, all four history counts, missing count and schema: **0 differing rows**. (Reported CSV hash `d8903bba...` cannot be reproduced bit-for-bit because `elapsed_ms` is per-run; stripping that column from my run gives `bf427ca31ba207be6d92e1a07d9276c352956742ff9fc6207c346312d3c1e290`. This is an explanation, not a discrepancy in the claim.)
- One-off Python checks on a real SCEN0002 event: `validate_bundle` accepts the genuine bundle; a bundle replayed against a different authorization_id raises `assessment authorization differs`; a deep-copied bundle with one feature value changed raises `assessment purchase digest differs`; `evaluate` with the model-off bundle and without it returns identical decision and reason codes (`approve`, `within_policy`).

## Findings

No blocking findings. Non-blocking observations:

1. `scripts/classifier_replay.py:112` writes the output with mode `"x"` and refuses an existing file, so a re-run needs a new path. Intentional immutability; no action needed.
2. `docs/eval/classifier/m1b-report.md:7` reports the full-CSV SHA-256 including `elapsed_ms`, which is not reproducible across runs. The decision-content parity is what matters and it holds; future reports would be easier to check with a content-only hash.
3. `assess.py:50-51`: when `assess()` runs live, behaviour scoring is synchronous before the awaited Jev call; if the behaviour scorer ever became slow, the deadline reserve in `jev.py:117-119` only bounds the Jev call. Not reachable in this model-off cut and no threshold exists yet, so it cannot produce a wrong decision today. Worth revisiting when M1 runner hookup lands.

Failure scenarios considered and rejected: a history row at the exact event timestamp leaking into features (excluded by `bisect_left` on the composite key); a bundle from another customer or card being accepted (four independent identity checks); a tampered feature map passing validation (digest recomputation); a decline being upgraded by the model (models can only add `uncertain`, and this cut sends both models as `None`); an invalid provider response entering a decision (strict parse raises `JevResponseError`); cross-pack identity confusion (pack-consistency checks at load).

## Limitations

- The live runner does not call `assess()` yet, as the report states; runner hookup, customer answers, locks and deadline behavior are out of scope for this cut and unverified here.
- The behavioural artifact and threshold claims were accepted from the manifest and loader code; the artifact was not re-scored in this round beyond the replay, which passes `behaviour=None`.
- No test suite or linter was run, per the round rules.

## Observed outcome

The 45-attempt replay through shared contracts and pure `evaluate(..., assessments=...)` reproduces the M1 baseline exactly at head `e4ba7ba`, the manifest held before and after, and the isolation, digest, precedence and escalation constraints hold in code and in the live negative checks. The milestone claims match what the code does, and nothing claimed is overstated.
