# M3a r1 review report (GLM)

Verdict: APPROVE (the standalone M3a history/Jev assessment cut only)

- Head: 886b4ba915827453981fd1a1ea378952ac49cfb8
- Base: bfb4df53b023c4026807dc8c9d3c5669bb9ba67b
- M2 evaluation-only model cleared separately at f5d27c80ed3862473852ae2ed3a802190ca13fc5 (context only)
- Manifest: docs/reviews/classifier/M3a/r1/MANIFEST.sha256 verified 20/20 OK before review and after review; working tree clean (only git-ignored __pycache__ from imports); HEAD unchanged before and after.
- Observed model pin: glm-5.3 (cotal_orientation). Requested effort: max. Max effort was performed, not silently omitted: full static read of the five scope files and the observation doc, diff against base, plus four one-off local runs (event+bundle composition, response-validation matrix, cold-start scoring, local hang-server propagation). No provider or simulator request was made, per the brief.

## Blocking findings

None.

## Verified claims (each reproduced offline except where noted)

1. Numeric-history isolation. The provider request state is exactly feature_schema_version, values, missing, support (jev.py:120-125). I serialized the state for the reproduced AU0035 event: no customer_id or card_id value, no merchant/device/description/instruction text, no long digit runs. Matches the doc claim (m3-observation.md:3).
2. Source and key provenance. No environ/getenv/.env access anywhere in src/leash/engine/classifier/ (grep). assess_jev takes a keyword-only api_key (jev.py:110-116); empty key raises RuntimeError, verified. The doc honestly states the live runner still needs a settings-owned scoped accessor (m3-observation.md:5). The bearer is sent only to the pinned URL, follow_redirects=False (jev.py:134-136), so a redirect cannot carry the key elsewhere.
3. Full-response validation. Verified by a 15-case matrix against _parse_response: wrong model, wrong provider, choice differing from local argmax, probabilities not summing to one, negative probability, missing answers, extra question, non-JSON, duplicate JSON keys, tie-choice outside tied maxima all raise JevResponseError; well-formed responses parse; exact ties return selected=None with a provider null or a tied pick accepted (jev.py:54-107), matching the tightened rule the doc describes (m3-observation.md:7).
4. Provider/model pin. Request pins model typesafe/jev-1.13-20260917 with provider.only ["typesafe"] and allow_fallbacks False (jev.py:126-131); the response must echo the same model and provider "TypeSafe" (jev.py:70-72). No alternative-model or fallback path exists in the file.
5. Deadline and failure behavior. Past-deadline raises TimeoutError before the reserve (jev.py:117-119), naive timezone raises ValueError (jev.py:113-114), a local hanging server produced a propagated builtins.TimeoutError with no substituted decision (asyncio.timeout_at plus httpx timeout, jev.py:133-134), HTTP != 200 raises (jev.py:137-138), over-64,000-byte responses raise mid-stream (jev.py:141-144), non-UTF-8 raises (jev.py:146-149), and a result leaving under 2 s for the state recheck raises (jev.py:152-153). No try/except anywhere in the classifier package swallows a failure; assess() composes without catching (assess.py:57-72).
6. Composition reproduces. Built the SCEN0004/AU0035 event with scripts/replay.py's own build_event and the supplied draft docs/eval/replay-policies/SCEN0004.json: 50 features, 0 missing, card/customer prior rows 132/214, card/customer merchant familiarity 6/8, as_of equal to the event timestamp, validate_bundle accepted. CatBoost score 0.09738242403508872 matches the doc's 0.097382; artifact hash prefix e4815c567707 matches the manifest; policy hash prefix 3a8384040867 matches (m3-observation.md:9). Tampering one feature value raises "assessment purchase digest differs", and a wrong state mandate_id raises (assess.py:61-62, 47-48).
7. M1a digest parity. purchase_digest in assess.py is unchanged from the M1a-cleared base bfb4df5 (git show compared); it still binds authorization, mandate identity and the full feature map.
8. History scope and leakage window. Strictly pre-event rows only, (timestamp, authorization_id) ordered (history.py:165-172); the base pack ends 2026-07-31 and the event is 2026-08-12, so no row at or after the event timestamp exists for card CA0039; AU0035 itself is absent from the base pack. Card and customer scopes are both populated and mutually consistent.
9. Honesty of standalone claims. The observation doc lists exactly what did not happen: no evaluate(assessments=...), no model-driven step-up, no customer answer, no simulator request, three provider requests spent (m3-observation.md:11). Nothing in the cut contradicts it: assess.py imports behaviour only under TYPE_CHECKING, so the Jev path does not even require the optional model dependencies, and the lane-local types are untouched by the unmerged shared-contract draft.

## Non-blocking observations

- jev.py:88: the 1e-6 sum tolerance accepts a total of 1 + 1e-7 (observed). This is the documented boundary, not a bug.
- assess.py:21-27: purchase_digest binds mandate_id, which replay.py randomizes per run, so the doc's digest prefix 5c0490bdce17 is evidence of that run only and cannot be reproduced by a third party. The doc already labels it local integrity evidence (m3-observation.md:9); every other reproducible quantity matched.
- behaviour.py:10-14 imports numpy/sklearn/catboost at module import; assess.py guards it with TYPE_CHECKING (assess.py:15-16), so the standalone Jev path stays importable without the optional dependency group. Verified statically, not by uninstalling the group.
- Cold start: an all-missing 50-feature vector scores 0.0442 with escalation_fired False; schema or feature-name mismatch is rejected. A brand-new customer therefore gets a benign numeric profile plus a Jev prompt whose "unclear" criterion covers thin history; no crash, no silent fallback.
- The doc's provider latencies (471/482/476 ms) and both-ordinary answers are taken as reported observations; they are not reproducible without spending a provider call, which the brief forbids me.

## Commands actually run

In /private/tmp/classifier-m3a-r1-glm (read-only except imports):
- git status; git rev-parse HEAD; git log --oneline -5; git diff --stat bfb4df5..886b4ba; git show bfb4df5:src/leash/engine/classifier/assess.py
- shasum -a 256 -c docs/reviews/classifier/M3a/r1/MANIFEST.sha256 (before and after; 20/20 OK both times)
- grep for environ/getenv/.env/print/httpx/api_key/open(/write/subprocess across src/leash/engine/classifier/
- Reads of assess.py, jev.py, types.py, history.py, behaviour.py, contracts (event/decision/policy/_base), model-manifest.json, m3-observation.md, scripts/replay.py, src/leash/runner/settings.py, progress log

In external scratch (/tmp/jc-9d3504c5775e/home/scratch/m3a-glm, uv venv 3.13 with numpy 2.5.3, scikit-learn 1.9.1, catboost 1.2.10, matching the manifest), PYTHONPATH=src against the frozen tree:
- harness_m3a.py: event build, HistoryIndex load 0.77 s, bundle+validate, BehaviourModel score, digest tamper, state-mandate mismatch, deadline/key/tz failures, 15-case _parse_response matrix, state-privacy serialization
- coldstart_check.py: base/additional pack windows, CA0039 row audit, cold-start scoring, schema/feature-name rejection
- hang_test.py: local 127.0.0.1 socket that accepts and never answers; assess_jev raised builtins.TimeoutError

## Limitations

- No provider or simulator request was made from this review, per the brief; provider-side claims in m3-observation.md are accepted as reported observations with their reproducible offline artifacts verified.
- Runner/app integration, shared P1/P2 contracts and evaluator wiring are outside this cut and were not reviewed beyond confirming the doc does not claim them.
- Peer reports were not read before this verdict, per instruction.

## Observed outcome

The standalone M3a cut does what the observation doc says, fails loudly everywhere I probed, isolates numeric history from the provider request, pins the model and provider on both request and response, and makes no integration claim beyond the standalone runs. Three provider calls remain the author's spend, not mine.
