# Classifier M1a Review Report (Round r1)

- Reviewer: classifier_review_gemini (role: default)
- Date: 2026-09-25
- Space: zurichbuchegg
- Worktree: /private/tmp/classifier-m1a-r1-gemini
- Report path: /private/tmp/classifier-review-reports/M1a/r1/gemini/report.md

---

## 1. Verdict

APPROVE classifier M1a r1 at commit 1f5a45da0d0b12d53ec4268de1f683052ce65fba (base 6cd4340316c0ebc546a2c0f8ff6b147ef1688db8).

The M1a cut delivers a self-contained, pre-event personal history feature pipeline and deterministic model-off replay. It adheres to all contract boundaries, pre-event ordering guarantees, familiarity scopes, support and missing-value conventions, cryptographic policy and digest bindings, and fail-loud error requirements.

This approval covers M1a as a self-contained history extraction and model-off replay cut. It does not approve engine-owned P1/P2 contract integration or runner hookup, which remain absent from main and are scheduled for later integration.

---

## 2. Target Identification and Hash Verification

- Target HEAD commit: 1f5a45da0d0b12d53ec4268de1f683052ce65fba
- Base commit: 6cd4340316c0ebc546a2c0f8ff6b147ef1688db8
- Manifest file: docs/reviews/classifier/M1a/r1/MANIFEST.sha256
- Manifest SHA-256: 76e824a8d3003146836880d5e519654793338156703eb0fe593d57d7abd050cd
- Target status: Clean worktree; detached HEAD at 1f5a45da0d0b12d53ec4268de1f683052ce65fba. All 13 manifest entries verified with shasum -a 256 -c before and after review.

---

## 3. Actual Model Pin and Effort Verification

- Persona specification: .cotal/agents/classifier_review_gemini.md declares agent jcode, model gemini-3.8-flash, variant high.
- Recorded model pin: cotal_orientation confirmed Model pin: gemini-3.8-flash.
- Connector route: launch.log records model gemini-3.8-flash is served by provider cliproxy via openai-compatible:cliproxy.
- Effort verification: Requested variant high was submitted and accepted by the launcher without rejection. The upstream cliproxy / OpenRouter chat completions interface does not expose or activate an explicit thinking tier for gemini-3.8-flash. Requested effort high was accepted, but is not observable as active provider deliberation from the seat.

---

## 4. Findings by Review Lens

### 4.1 Current Contracts and Interface Boundaries
- File: src/leash/contracts/, src/leash/engine/classifier/types.py:1-5
- Observation: The shared models in src/leash/contracts/ remain untouched by this commit. The classifier lane types (HistoryFeatures, BehaviorAssessment, JevAnswer, SemanticAssessment, AssessmentBundle) are placed in src/leash/engine/classifier/types.py local to the lane.
- Assessment: Clean separation. Proposal P1/P2 (introducing optional assessments to evaluate()) has not been merged into the foundation contracts. M1a respects this boundary.

### 4.2 Strict (timestamp, authorization_id) Pre-event Ordering
- File: src/leash/engine/classifier/history.py:31-33, 54-55, 153-170
- Observation: History rows are sorted by key (record.when, record.row["authorization_id"]). In _prior(), bisect_left(keys, purchase.key) slices rows strictly before the evaluated purchase.
- Assessment: Pre-event ordering is strictly enforced. The current event and any future events are excluded from historical feature derivation.

### 4.3 Same-Customer and Same-Card Authorization
- File: src/leash/engine/classifier/history.py:108-128, 135-139, 260-266
- Observation: Cross-pack card duplication is rejected. Account, card, and customer relationships are validated during index load. for_event() verifies that auth.card_id == mandate.card_id, auth.mandate_id == mandate.mandate_id, and mandate.card_id belongs to mandate.customer_id.
- Assessment: Any mismatch raises ValueError immediately. A simulated customer ID mutation on AU0035 raised ValueError: AU0035: mandate card does not belong to customer.

### 4.4 Approved-Purchase-Only Familiarity
- File: src/leash/engine/classifier/history.py:190-218
- Observation: In _features(), prior rows are filtered by transaction_type == "purchase" and status == "approved". Familiarity counts for merchant, device, country, channel, and category match against this approved subset only.
- Assessment: Only approved purchases create familiarity. Declines, refunds, and non-purchase transactions do not increment familiarity counts.

### 4.5 Declines in Velocity
- File: src/leash/engine/classifier/history.py:191, 194, 233-240
- Observation: attempt_count_{10m,1h,24h} counts all purchase attempts (approved or declined) within the trailing duration. declined_attempt_count_{10m,1h,24h} explicitly counts attempts with status == "declined".
- Assessment: Prior declines are counted in attempt velocity as required.

### 4.6 Refunds and Non-Purchase Transactions
- File: src/leash/engine/classifier/history.py:191, 282
- Observation: Attempts are filtered strictly by row["transaction_type"] == "purchase". Non-purchase transactions such as refunds are excluded from attempts and approved subsets.
- Assessment: Refunds never add familiarity or increase purchase-attempt velocity counts.

### 4.7 Device Absence versus Unseen Device Distinction
- File: src/leash/engine/classifier/history.py:204-218
- Observation: When purchase.device_id is empty or None, device_approved_count is set to None with missing reason no_device and support 0. When purchase.device_id is present but not previously seen, device_approved_count is set to 0.0 with support equal to the approved purchase count, and device_last_approved_days is set to None with missing reason no_prior_in_device.
- Assessment: Matches the feature schema hist-1 specification.

### 4.8 Real Empty History and Missingness/Support Conventions
- File: src/leash/engine/classifier/history.py:183-188, 215-231, 241-246, docs/eval/classifier/feature-schema.md
- Observation: An empty approved history produces approved_purchase_count = 0.0 with support 0. Recency features yield None with missing reason empty_history and support 0. Support counts accurately track evaluated rows.
- Assessment: Fully conformant with hist-1. Valid empty history is represented as structured numeric data rather than an error or fallback.

### 4.9 Row-Time Card Status
- File: src/leash/engine/classifier/history.py:173-174, 251, 274, 296
- Observation: Historical rows use row["card_status"] as recorded at transaction time. Live events use auth.card_status_at_attempt. The status from cards.csv is not referenced for lifecycle status.
- Assessment: Avoids lookahead bias.

### 4.10 Predictor Isolation
- File: src/leash/engine/classifier/history.py:179-252, src/leash/engine/classifier/types.py:26-32
- Observation: The values dictionary in HistoryFeatures contains only 50 numeric floats or None values. Customer IDs, card IDs, merchant IDs, device IDs, transaction IDs, scenario IDs, and replay positions are kept outside values.
- Assessment: Learner input features are isolated from identifiers and persona strings.

### 4.11 Live versus Historical Semantic Parity
- File: src/leash/engine/classifier/history.py:258-298
- Observation: Both for_event() and historical_purchases() construct a _Purchase dataclass and invoke the identical private _features() derivation.
- Assessment: Feature computations for live events and historical records are structurally identical.

### 4.12 Cryptographic Purchase Digest and Policy Binding
- File: src/leash/engine/classifier/assess.py:14-48
- Observation: purchase_digest() computes the SHA-256 hash of the canonical JSON representation of authorization and mandate identifiers. history_bundle() packages this digest with policy.hash and timestamp. validate_bundle() checks authorization_id, purchase_digest, policy_hash, timestamp, customer_id, and card_id before evaluation.
- Assessment: Tamper-resistant binding prevents reuse of assessments across different purchases or policies.

### 4.13 Category-Agnostic Semantic Matching and Extraction Boundaries
- File: src/leash/engine/classifier/history.py:196-221, src/leash/engine/classifier/jev.py:133-144
- Observation: History matching operates on exact categorical identifier equality. No merchant text or category heuristics are embedded in history derivation. Jev receives only the 50 numeric values, support counts, and missing reasons in its state payload.
- Assessment: The classifier feature does not parse merchant text or make item-level inferences, respecting the extract lane boundary and David's ruling.

### 4.14 Engine, Extract, Runner, and App Integration
- File: scripts/classifier_replay.py:83-93
- Observation: In classifier replay, extract_event() is called, history_bundle() is generated, validate_bundle() validates consistency, evaluate() performs deterministic evaluation, and apply() advances state.
- Assessment: Integration with existing extract and engine components operates as designed. Live runner hookup remains unmerged as planned for later milestones.

### 4.15 Customer Step-Up Handling
- File: scripts/classifier_replay.py:7-8, docs/eval/classifier/m1-report.md:17
- Observation: Offline replay invents no customer answers and sends no simulator requests. Pending step-ups remain pending.
- Assessment: Complies with the rule against fabricated customer decisions.

### 4.16 Cancellation Claims and Deadline Behaviour
- File: scripts/classifier_replay.py:90-91, src/leash/engine/classifier/jev.py:21, 130-132, docs/plans/02-classifier-design.md:86
- Observation: classifier_replay.py verifies datetime.now(UTC) < event.deadline_at and raises TimeoutError if exceeded. jev.py defines DEADLINE_RESERVE_SECONDS = 2.25 and raises TimeoutError if the remaining time budget is insufficient. Refunds never restore mandate budgets.
- Assessment: Absolute deadlines are respected and cancellation claims are accurate.

### 4.17 Fail-Loud Error Handling without Fallbacks
- File: src/leash/engine/classifier/history.py, src/leash/engine/classifier/assess.py, src/leash/engine/classifier/jev.py
- Observation: Disagreeing customer or card records, non-positive amounts, malformed CSV rows, missing timezones, duplicate authorizations, and HTTP or JSON errors raise ValueError, RuntimeError, TimeoutError, or JevResponseError. There are no try/except blocks swallowing exceptions or substituting default scores.
- Assessment: Fully complies with AGENTS.md section 6.

### 4.18 Independent Preparations: Split Manifest and Jev Adapter
- File: scripts/classifier_split.py, docs/eval/classifier/split-manifest.json, src/leash/engine/classifier/jev.py
- Observation: classifier_split.py builds customer and time partitions with seed 20260924 and 20% reserved fraction. Re-running build() produces an exact match with the committed split-manifest.json. jev.py enforces TypeSafe-only provider routing, dated model pin typesafe/jev-1.13-20260917, JSON schema validation, and local argmax selection with None on ties.
- Assessment: Verified as clean independent preparation. No security or blocking issues detected.

---

## 5. Commands Actually Run and Observed Outputs

1. Pre-review git verification:
   - Command: git rev-parse HEAD && git status --porcelain && shasum -a 256 -c docs/reviews/classifier/M1a/r1/MANIFEST.sha256
   - Output: HEAD 1f5a45da0d0b12d53ec4268de1f683052ce65fba, working tree clean, all 13 files in MANIFEST.sha256 reported OK.

2. One-off classifier replay execution on SCEN0002:
   - Command: PYTHONPATH=src python3 scripts/classifier_replay.py --policy SCEN0002=docs/samples/scen0002_draft.json --output /private/tmp/classifier-gemini-scen0002-test.csv
   - Output: 12 attempts executed, 1 approve, 11 decline, 0 step-up. Output CSV generated at /private/tmp/classifier-gemini-scen0002-test.csv.

3. Replay output verification against committed evidence:
   - Command: Compared /private/tmp/classifier-gemini-scen0002-test.csv against docs/eval/classifier/m1-scen0002.csv.
   - Output: All 12 rows matched identically across scenario_id, authorization_id, decision, reason_codes, card_merchant_approved_count, customer_merchant_approved_count, card_approved_purchase_count, customer_approved_purchase_count, missing_feature_count, and history_schema.

4. Baseline replay parity check:
   - Command: PYTHONPATH=src python3 scripts/replay.py --policy SCEN0002=docs/samples/scen0002_draft.json --output /private/tmp/base-replay-scen0002-test.csv
   - Output: Base replay generated 12 attempts. Decisions and reason codes across all 12 rows matched the classifier replay results exactly.

5. Verification of 45 public attempts and AU0035 mutation:
   - Command: Python execution over 45 public attempts via HistoryIndex.for_event().
   - Output: All 45 produced 50 features. Customer merchant familiarity exceeded card familiarity on exactly 36 attempts. AU0035 gave card count 6.0 and customer count 8.0. Mutating customer ID on AU0035 raised ValueError: AU0035: mandate card does not belong to customer.

6. Historical purchase count verification:
   - Command: Python execution over HistoryIndex.historical_purchases("additional").
   - Output: Exactly 140,096 purchases evaluated. Exactly 500 approved and 42 declined purchases had zero earlier approved customer purchases (total 542).

7. Absent device verification:
   - Command: Python check for historical purchase without customer_device_id.
   - Output: Both card_device_approved_count and customer_device_approved_count yielded None with missing reason no_device.

8. Split manifest reproducibility verification:
   - Command: Python check comparing classifier_split.build() with docs/eval/classifier/split-manifest.json.
   - Output: Build output matched the committed manifest byte-for-byte.

9. Post-review git verification:
   - Command: git rev-parse HEAD && git status --porcelain && shasum -a 256 -c docs/reviews/classifier/M1a/r1/MANIFEST.sha256
   - Output: Clean working tree at 1f5a45da0d0b12d53ec4268de1f683052ce65fba; all 13 manifest files verified OK.

---

## 6. Limitations

- Replay scope: Only SCEN0002 has a confirmed policy draft in docs/samples/; whole-pack 45-attempt replay is not part of this cut.
- Model effects: The classifier replay operates with model effect off. The behavioural model and Jev semantic assessments are not active in decision logic.
- Contract status: Proposals P1 and P2 remain unmerged on engine foundation branches. Live runner integration is deferred to later milestones.
- Paid calls: No paid model API calls or simulator requests were executed during this review.
