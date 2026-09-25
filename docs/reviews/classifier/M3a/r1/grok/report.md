# Classifier M3a r1 review

Verdict: APPROVE

Head: 886b4ba915827453981fd1a1ea378952ac49cfb8
Base: bfb4df53b023c4026807dc8c9d3c5669bb9ba67b
M2 evaluation-only clearance, not this cut: f5d27c80ed3862473852ae2ed3a802190ca13fc5
Observation SHA-256: 21a864aa9142e90b346b8310433965469acb85deec89bd3a3e82d2fc856bef3c
Manifest: docs/reviews/classifier/M3a/r1/MANIFEST.sha256, 20 of 20 OK before and after
Tree: detached grading checkout /private/tmp/classifier-m3a-r1-grok, porcelain empty before and after

Model pin: grok-4.7. Cotal orientation recorded that pin. Launch log says grok-4.7 is served by cliproxy via openai-compatible. Session session_cricket_1790293019223_d29f73c88f4fd15c has working_dir /private/tmp/classifier-m3a-r1-grok, provider_key cliproxy, model grok-4.7, reasoning_effort high. Snapshots: create at gpt-5.6-sol, set_model to grok-4.7, set_reasoning_effort, all at 2026-09-24T23:36:59Z before the prompt. Provider streams in the jcode log are model=grok-4.7. Requested effort: high (persona variant and session field). Accepted provider tier: not in provider usage. The set_reasoning_effort request was acked. Its log line does not echo the tier value.

Scope graded: src/leash/engine/classifier/assess.py, jev.py, types.py, history.py, behaviour.py, and docs/eval/classifier/m3-observation.md. This is the standalone history/Jev cut. It is not full M3. Shared P1/P2 types, the evaluator, and the runner/app path stay open. No paid provider or simulator request was made.

## Findings

No blocker.

N1. The published purchase-digest prefix is not recoverable, and it is not a defect in the binding. docs/eval/classifier/m3-observation.md:9 says the AU0035 bundle digest prefix was 5c0490bdce17 and the policy hash prefix was 3a8384040867. Rebuilt from public AU0035, docs/eval/replay-policies/SCEN0004.json, and scripts/replay.py build_event, the policy hash is 3a83840408674d175a5ace5a629983fd0f08e9162bdba814d6d17e36fc603870. The digest for a fixed mandate is stable across rebuilds, but scripts/replay.py:171 and scripts/classifier_replay.py:71 set mandate_id to offline-mandate-{uuid4().hex}. purchase_digest includes that mandate_id (assess.py:21-29), so the recorded prefix cannot be recomputed. A fixed mandate offline-mandate-fixed produced 7685d6471e892a80261e16de08ae34ae8b3b2102d1e2abb7c4948afc329e259a. The same run reproduced the other stated local facts: 50 hist-1 values, CatBoost score 0.09738242403508872, model id catboost, artifact prefix e4815c567707, escalation_fired False, and validate_bundle accepted the model-off bundle.

N2. validate_bundle does not constrain behaviour. assess.py:43-54 checks authorization, digest, policy hash, event time, and customer/card. types.py:35-44 types BehaviorAssessment.score as float and escalation_fired as bool. A local stub server and a caller-supplied model returned score nan, feature schema other, and escalation_fired True. assess() then passed validate_bundle. The shipped BehaviorModel.score path rejects a non-finite model distribution and always returns escalation_fired False (behaviour.py:81-99). Nothing in src or scripts calls assess() except its definition. This is a limit of the standalone type, not a live decision path.

N3. The post-response two-second recheck cannot fire on a normal clock. jev.py:117-119 refuses a call unless more than 2.25 seconds remain before the deadline. jev.py:133 bounds both the asyncio timeout and the httpx timeout to that same remaining budget. jev.py:152-153 then requires 2.0 seconds after the call. A call that stays inside the timeout still has more than 2.25 seconds left. The check can fire only if wall time jumps ahead of the monotonic loop clock. Deadline exhaustion, a slow body, HTTP 500, and an unfollowed 302 all raised on a local server. No OpenRouter call.

## Checks

Authorization and isolation. history.for_event uses the mandate card and customer. A foreign customer on AU0035's card raised ValueError AU0035: mandate card does not belong to customer. An authorization card different from the mandate raised ValueError AU0035: authorization and mandate identity differ. assess() with a different MandateState.mandate_id raised ValueError AU0035: assessment state mandate differs (assess.py:61-62). Prior rows are bisect_left on (timestamp, authorization_id), so the current key is excluded (history.py:165-172). AU0035 at 2026-08-12T09:40:00+00:00 had card_approved_purchase_count 128 and customer_approved_purchase_count 201 from the customer's own rows. Both packs load. A customer in both packs is rejected at index build (history.py:114-116).

Prompt injection. assess_jev sends schema version, numeric values, missing reasons, and support counts (jev.py:120-131). It does not send customer, card, merchant, device, authorization, item name, or item_details. AU0035 purchase_description "27-inch computer monitor" and item_details "27-inch IPS panel, 2-year seller warranty; returns accepted within 14 days" were absent from that state and present in the authorization object that the local digest hashes. Across the 33 public attempts whose replay policy file exists, missing reasons were only no_prior_in_merchant, no_prior_in_device, and no_prior_in_country. A 300-row additional-pack sample had zero identifier hits. Reasons seen there were empty_history, no_device, and no_prior_in_{category,merchant,channel,device,country}. A crafted HistoryFeatures with free text in missing does get serialized. History construction does not put merchant text there. Questions tell the model to use only the numeric summary (jev.py:25-44). Extra answer fields are ignored by the parser. That is a residual instruction-injection surface only if a caller builds features outside this history code.

Provenance. The local digest binds authorization, mandate id, customer, card, and the full feature map (assess.py:19-29). The comment says it is an integrity check, not authentication. The observation repeats that. Committed lane/engine-assessments at f02ad0977ed19a6419abcad05f8d446df9938604 defines assessment_purchase_digest(event) without the feature map. That worktree was dirty at review time, so this comparison is the committed file only. The observation and progress log already call the shared contract unmerged and incompatible. No classifier module imports it. This cut does not claim shared integration.

Provider response. _parse_response rejects duplicate JSON keys, a non-object body, a model other than typesafe/jev-1.13-20260917, a provider other than TypeSafe, a question set other than the two requested questions, a non-choice answer, option keys other than ordinary/unusual/unclear, non-finite or out-of-range probabilities, and a sum outside 1e-6. A unique argmax must match the provider choice. A tie keeps selected None whether the provider sends null or one of the tied options (jev.py:90-100). Bool True is rejected. The stream stops above 64,000 bytes, requires UTF-8, and decode plus parse sit inside the timeout (jev.py:133-151). Redirects are not followed. HTTP status other than 200 raises JevResponseError before the body is parsed. An empty api_key raises RuntimeError. A naive deadline raises ValueError.

Failure handling. Malformed provider output raises JevResponseError. TimeoutError and network failures are not caught in assess(). There is no substitute decision in this cut. The observation says the same and says a live runner still needs a settings-owned key accessor, a mandate lock, and a policy/state recheck. Those are absent here and are not claimed as done.

Honesty of the real-call claims. Latencies 471 ms, 482 ms, and 476 ms, the 1,389 ms total, and 6,610 ms remaining were not rerun. The brief forbids a provider call. The local facts that can be rerun match, except the unreproducible digest prefix in N1. assess_jev does not read .env. Its only credential input is the api_key argument. No src or scripts caller invokes assess or assess_jev. classifier_replay.py calls history_bundle and validate_bundle, then engine.evaluate without assessments. The observation's claim of no evaluate(..., assessments=...) call, no simulator request, and no live decision path matches that static result.

## Commands

- git rev-parse HEAD; git status --porcelain=v1; git rev-parse bfb4df53b023c4026807dc8c9d3c5669bb9ba67b; shasum -a 256 -c docs/reviews/classifier/M3a/r1/MANIFEST.sha256, before and after. Head stayed 886b4ba915827453981fd1a1ea378952ac49cfb8. Porcelain empty. Manifest 20 OK.
- git diff --stat bfb4df53b023c4026807dc8c9d3c5669bb9ba67b..HEAD. Five files, 86 insertions, 10 deletions.
- uv sync --group classifier. Installed catboost 1.2.10, numpy 2.5.3, scikit-learn 1.9.1.
- uv run python one-off: AU0035 through build_event and HistoryIndex. 50 values, score 0.09738242403508872, policy prefix 3a8384040867, digest prefix 7685d6471e89 for mandate offline-mandate-fixed.
- uv run python one-off: parser cases for duplicate keys, ties, sum tolerance, NaN, extra questions, bool, and wrong provider. Outcomes recorded under Provider response.
- uv run python one-off: local ThreadingHTTPServer only. Slow body raised TimeoutError. Body over 64,000 bytes raised JevResponseError. HTTP 302 and 500 raised JevResponseError. No request left the machine.
- uv run python one-off: swapped customer, swapped card, and mismatched mandate state. All three raised ValueError.
- git show f02ad0977ed19a6419abcad05f8d446df9938604:src/leash/contracts/classifier.py on the engine-assessments worktree, read only.

## Limits

No OpenRouter call, so the three recorded latencies and the served-model response body were not independently observed. The random mandate id makes the published digest prefix unverifiable. Provider-accepted reasoning tier is not in usage. P1/P2, runner lock, and live recheck remain outside this cut, as the observation says. The grading checkout was not edited, committed, or cleaned.
