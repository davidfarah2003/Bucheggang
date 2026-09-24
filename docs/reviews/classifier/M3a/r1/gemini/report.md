# Classifier M3a Review Report (Round r1) — Gemini

## 1. Verdict
**APPROVE** classifier M3a r1 @`886b4ba915827453981fd1a1ea378952ac49cfb8`

---

## 2. Target Identification & Hash Verification

- **Target Head Commit**: `886b4ba915827453981fd1a1ea378952ac49cfb8`
- **Base Commit**: `bfb4df53b023c4026807dc8c9d3c5669bb9ba67b`
- **Manifest Path**: `docs/reviews/classifier/M3a/r1/MANIFEST.sha256`
- **Manifest SHA-256**: `7e630023ebdd1ba45812623c242bde63a8e5e45db128f92d93467d30b995a38f`
- **Integrity Check**: Verified before and after grading. All 20 files in `MANIFEST.sha256` match exactly (`OK`). Working tree is clean on detached HEAD `886b4ba915827453981fd1a1ea378952ac49cfb8`.

---

## 3. Actual Model Pin & Effort Verification

- **Persona**: `.cotal/agents/classifier_review_gemini.md`
- **Configured Model**: `gemini-3.8-flash`
- **Reported Model Pin**: `gemini-3.8-flash` (confirmed via `cotal_orientation` and `launch.log`)
- **Requested Effort / Variant**: `high` (`variant: high` in persona)
- **Accepted Effort Tier**: Served by provider `cliproxy` via `openai-compatible:cliproxy`; exact served internal reasoning tier is unobservable from seat metadata. High effort was requested and not omitted.

---

## 4. Findings by Review Lens

### 4.1 Current Contracts & Boundary Honesty
- **Scope**: Standalone cut covers `src/leash/engine/classifier/assess.py`, `jev.py`, `types.py`, `history.py`, `behaviour.py`, and `docs/eval/classifier/m3-observation.md`.
- **Finding**: Interfaces imported in `assess.py:9` (`Event`, `MandateState`, `PolicyDraft`) adhere to main contracts. Lane types in `types.py` remain local pending P1/P2 harmonization. The interface conflict against engine-owned `lane/engine-assessments` @`f02ad09` is explicitly documented in `docs/plans/02-classifier-progress.md:148` as an unmerged limit rather than an unearned integration claim.

### 4.2 Category-Agnostic Semantic Matching & Numeric-History Isolation
- **File / Lines**: `src/leash/engine/classifier/jev.py:22-47, 120-131`
- **Finding**: The Jev payload `state` contains strictly `feature_schema_version`, `values`, `missing`, and `support` from `HistoryFeatures` (`hist-1`, 50 numeric features). No raw customer identifiers (`customer_id`, `card_id`), merchant identifiers, device identifiers, item descriptions, or merchant-authored strings are forwarded. The two semantic questions (`spend_pattern` and `activity_pattern`) operate purely over the numeric history distribution. The classification path is category-agnostic and robust against merchant text prompt injection.

### 4.3 Key Provenance & Parameter Scoping
- **File / Lines**: `src/leash/engine/classifier/assess.py:57-65`, `src/leash/engine/classifier/jev.py:110-116`
- **Finding**: `assess_jev()` and `assess()` require `api_key: str` as an explicit keyword-only argument. Shipped code never accesses `.env`, disk configs, or shared files. A missing or empty key raises `RuntimeError("Jev API key is missing")` immediately.

### 4.4 Full-Response Validation, JSON Integrity, & Tie-Break Handling
- **File / Lines**: `src/leash/engine/classifier/jev.py:54-108, 137-151`
- **Finding**: 
  - Stream reception is bounded at `MAX_RESPONSE_BYTES = 64_000` (`jev.py:144`), raising `JevResponseError` mid-stream if exceeded.
  - Non-UTF-8 bytes raise `JevResponseError("Jev response is not UTF-8")`.
  - JSON decoding utilizes `_unique_pairs` as `object_pairs_hook` to strictly reject duplicate JSON keys at any nesting level.
  - Pin verification rejects unexpected models or providers (`model != REQUESTED_MODEL or provider != SERVED_PROVIDER`).
  - Probability distributions are validated for numeric types, finite range $[0, 1]$, and exact summation to $1.0$ within $10^{-6}$.
  - Winner resolution enforces argmax agreement: unique winners must match `choice`; exact ties allow `choice` to be `None` or one of the tied options, setting `selected = None` locally. Choice outside tied winners raises `JevResponseError`.

### 4.5 Deadline Enforcement & Loud Failure Behavior
- **File / Lines**: `src/leash/engine/classifier/jev.py:19-21, 113-119, 133-136, 152-154`
- **Finding**:
  - Requires timezone-aware deadline (`deadline_at.tzinfo is not None`).
  - Enforces `DEADLINE_RESERVE_SECONDS = 2.25` before outbound network dispatch; raises `TimeoutError` if insufficient time remains.
  - Applies dual timeout via `asyncio.timeout_at` and `httpx.AsyncClient(timeout=remaining)`.
  - Enforces `MINIMUM_RECHECK_SECONDS = 2.0` post-response parsing; raises `TimeoutError("Jev result left too little time for state recheck")` if late decoding/parsing leaves inadequate time for mandate state rechecks.
  - Strictly adheres to AGENTS.md Section 6: zero fallbacks, no error-swallowing try/except blocks, no synthetic mock returns. All failures propagate loudly.

### 4.6 Standalone Real-Call Claims Honesty
- **File / Lines**: `docs/eval/classifier/m3-observation.md:1-11`
- **Finding**: Documentation accurately specifies the 3 standalone runs conducted on SCEN0004 AU0035 with a fresh 8-second offline deadline. Confirms no live evaluator check, no customer step-up, no customer answer, and no simulator interaction occurred. The CatBoost evaluation score ($0.097382$) and artifact hash prefix (`e4815c567707`) reproduced exactly under independent execution.

### 4.7 M1a Purchase Digest Integrity & Bundle Validation
- **File / Lines**: `src/leash/engine/classifier/assess.py:19-30, 43-55`
- **Finding**: `purchase_digest()` computes a canonical SHA-256 over authorization, mandate ID, customer ID, card ID, and the entire 50-feature dictionary. `validate_bundle()` recomputes and validates the digest, authorization ID, policy hash, timestamps, and customer/card consistency. State mandate mismatch raises `ValueError`.

---

## 5. Commands Actually Run and Observed Outputs

1. **Manifest and Git tree verification before review**:
   - `shasum -a 256 -c docs/reviews/classifier/M3a/r1/MANIFEST.sha256` -> All 20 files `OK`.
   - `git status --porcelain` -> Clean working tree.
   - `git rev-parse HEAD` -> `886b4ba915827453981fd1a1ea378952ac49cfb8`.

2. **Module imports verification**:
   - `uv run --group classifier python3 -c "import leash.engine.classifier.assess, leash.engine.classifier.jev, leash.engine.classifier.behaviour, leash.engine.classifier.history, leash.engine.classifier.types; print('OK')"` -> `OK`.

3. **Jev response parser edge-case probe**:
   - Tested: valid payload, duplicate keys, model mismatch, provider mismatch, missing question, invalid probability sums, non-finite values, argmax mismatch, tie-break choices (`None`, tied winner, invalid winner).
   - Output: All 10 edge cases caught and handled as specified with `JevResponseError` or valid `SemanticAssessment`.

4. **Jev network streaming, bounds, and deadline probe (local mock transport)**:
   - Tested: missing timezone, missing API key, tight deadline reserve ($< 2.25$ s), HTTP 500 error, payload $> 64,000$ bytes, non-UTF-8 payload, post-parse deadline reserve check ($< 2.0$ s).
   - Output: All failure modes raised corresponding `TimeoutError`, `ValueError`, `RuntimeError`, or `JevResponseError` loudly.

5. **Historical feature generation and CatBoost scoring replication on SCEN0004 AU0035**:
   - Loaded `HistoryIndex`, built AU0035 event with SCEN0004 policy draft (`3a8384040867...`).
   - Feature count: 50 numeric features.
   - `BehaviorModel().score(features)`: returned score $0.097382$, `model_id='catboost'`, artifact hash prefix `e4815c567707...`, `escalation_fired=False`.
   - `validate_bundle()` accepted completed bundle.

6. **Manifest and Git tree verification after review**:
   - `shasum -a 256 -c docs/reviews/classifier/M3a/r1/MANIFEST.sha256` -> All 20 files `OK`.
   - `git status --porcelain` -> Clean working tree.

---

## 6. Limitations

- **Standalone Cut Boundary**: This review assesses standalone history/Jev assessment only. Live runner settings accessors, shared P1/P2 contract unification, and full end-to-end evaluator wiring remain open pending cross-lane alignment.
- **Provider Spending**: In accordance with review rules, no paid provider requests or simulator interactions were executed during this grading session; all functional checks were conducted via static inspection and deterministic local mock runs.

---

## 7. Observed Outcome

Target commit `886b4ba915827453981fd1a1ea378952ac49cfb8` cleanly and faithfully implements standalone M3a history and Jev assessment. Numeric history is fully isolated from merchant text, response validation is strict and robust, key handling is explicit in memory, deadline constraints fail loudly with no fallbacks, and claims in documentation are accurate.
