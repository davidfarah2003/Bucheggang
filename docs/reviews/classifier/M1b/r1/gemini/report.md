# Classifier M1b Review Report (Round r1)

- Reviewer: classifier_review_gemini_m2
- Role: default
- Space: zurichbuchegg
- Worktree: /private/tmp/classifier-m1b-r1-gemini
- External report path: /private/tmp/classifier-review-reports/M1b/r1/gemini/report.md
- Date: 2026-09-25

---

## 1. Verdict

**APPROVE** classifier M1b shared-contract model-off integration at commit `e4ba7ba1f0707164ddfd6071779501a880598b44` (base `49646be2cc3ed07486cabdebbac042d835eaf30c`).

This milestone cut completes the bridge from classifier-local definitions to shared repository contracts:
1. Removed lane-duplicate `src/leash/engine/classifier/types.py` and adopted shared contracts from `src/leash/contracts/classifier.py` (`AssessmentBundle`, `HistoryFeatures`, `BehaviorAssessment`, `JevAnswer`, `SemanticAssessment`, `assessment_purchase_digest`, `FEATURE_SCHEMA_VERSION`).
2. Integrated `history_bundle(event, policy, history)` and `validate_bundle(event, policy, bundle)` into `scripts/classifier_replay.py` to pass shared bundles directly to pure `evaluate(..., assessments=bundle)`.
3. Verified exact replay parity across all 45 public attempts (11 approve, 32 decline, 2 step-up) against `docs/eval/classifier/m1-all-45.csv`.
4. Verified that `validate_assessments` in `src/leash/engine/model_checks.py` rigorously validates authorization, mandate, customer, card, timestamp, policy hash, and purchase digest integrity, preventing cross-customer leakage or post-scoring tampering.
5. Confirmed that the evaluation-only behavioral model (`BehaviorModel`) hardcodes `escalation_fired=False` and cannot trigger customer step-up, and that model checks can never overturn a hard policy failure.
6. Confirmed that `JevAnswer` and `SemanticAssessment` fail closed on invalid probability distributions, non-matching argmax choices, model substitution, or missing questions.

Scope limit: Full M1 still requires runner integration (`src/leash/runner/`), which currently calls `evaluate` without assessments. No live model execution, operational threshold, customer answer, or live simulator interaction is claimed for M1b.

---

## 2. Target Identification and Hash Verification

- Target Head Commit: `e4ba7ba1f0707164ddfd6071779501a880598b44`
- Base Commit: `49646be2cc3ed07486cabdebbac042d835eaf30c` (merged origin/main baseline with shared PR #47 and PR #50)
- Preceding M1a History Target: `e9974121fc47320dc7fabb9ddb280a517d1116cc`
- Preceding M3a Jev Standalone Target: `886b4ba915827453981fd1a1ea378952ac49cfb8`
- Manifest Path: `docs/reviews/classifier/M1b/r1/MANIFEST.sha256`
- Manifest SHA-256: `54efe8034a154bdff5c424bca260349f90468fbcf296a754edf25c22a7503c56`
- Target Checkout: `/private/tmp/classifier-m1b-r1-gemini` (detached HEAD at `e4ba7ba1f0707164ddfd6071779501a880598b44`)
- Working Tree Status: Clean; 0 untracked files, 0 staged files.
- Manifest Verification: All 22 files in `docs/reviews/classifier/M1b/r1/MANIFEST.sha256` verified with `shasum -a 256 -c` before and after review (`OK`).

Key File SHA-256 Digests:
- `src/leash/contracts/classifier.py`: `b103333c868786f23d51aa85795f4514c5f3f900e82a8306829265d6f736380a`
- `src/leash/engine/classifier/assess.py`: `a3813081d27ca90c549c07631ee796f11545b58d8b3086d6cc7891d379858757`
- `src/leash/engine/classifier/behaviour.py`: `a36bc64320629eef42882b3ee9f76552a790de956d48aa9c8ca0d77b02bf5c3a`
- `src/leash/engine/classifier/history.py`: `533e6d3796f0e3f310105b21a42ed377eada3805c2fc8c85ac7dc450c6e3156e`
- `src/leash/engine/classifier/jev.py`: `5a3813311021a6f89127396403b4a0b123462f4e343f3ce68d63b5df3a73c06f`
- `src/leash/engine/evaluate.py`: `f8d073ee357e684ff843d9a171584ab9670e44dfda3195571e402ba2bc37c76c`
- `src/leash/engine/model_checks.py`: `e6607061204929e6931d60cb62a1cd92018d1a21dd4af6866194e0b61ce413f7`
- `scripts/classifier_replay.py`: `5ca79b9fae94d79cda03b611991c9e6cdbeef636e107e39fcb3a773c5e2fbd4d`
- `docs/eval/classifier/m1-all-45.csv`: `fd9ea6a52795969c96a571eb13ac470907746d9fcd253fdaa97612925f7df3ee`
- `docs/eval/classifier/m1b-report.md`: `bf01306edb0062593ab75ab4d02d676ce21c43daf6fc4b846762aa890a801d69`

---

## 3. Actual Model Pin and Effort Verification

- Persona: `.cotal/agents/classifier_review_gemini.md` (agent: `jcode`, model: `gemini-3.8-flash`, variant: `high`)
- Orientation Pin: `cotal_orientation` reports `Model pin: gemini-3.8-flash (from COTAL_MODEL / the agent file)`
- Harness / Provider: Jcode session served by provider `cliproxy` via `openai-compatible:cliproxy`
- Requested Effort / Tier: `high` (`variant: high` in persona). Upstream cliproxy accepts the connection request. High effort was explicitly specified and not omitted.

---

## 4. Findings by Review Lens

### 4.1 Current Contracts and Type Deduplication
- Files: `src/leash/contracts/classifier.py`, `src/leash/engine/classifier/assess.py`, `src/leash/engine/classifier/types.py` (deleted)
- Observation:
  1. `src/leash/engine/classifier/types.py` has been deleted in commit `76363be`. The lane no longer maintains local duplicate pydantic definitions.
  2. All classifier modules (`assess.py`, `behaviour.py`, `history.py`, `jev.py`) and scripts (`classifier_fit.py`) now directly import contracts from `leash.contracts`: `AssessmentBundle`, `HistoryFeatures`, `BehaviorAssessment`, `JevAnswer`, `SemanticAssessment`, `assessment_purchase_digest`, and `FEATURE_SCHEMA_VERSION`.
  3. Strict Pydantic model validators are enforced on the shared contracts:
     - `HistoryFeatures`: `schema_version` must be literal `"hist-1"`; `as_of` must have a timezone; `support` keys must cover exactly `values`; `missing` reasons must cover exactly `None` values in `values`.
     - `JevAnswer`: options must be exactly `{"ordinary", "unusual", "unclear"}`; probabilities must sum to 1.0 within $10^{-6}$; unique argmax must match `selected`; exact ties must set `selected=None`.
     - `SemanticAssessment`: `requested_model` must equal `served_model` (rejecting model substitution); answers must cover exactly `{"spend_pattern", "activity_pattern"}`.
     - `AssessmentBundle`: `as_of` must match `features.as_of`; `behaviour.feature_schema_version` must match `features.schema_version`.

### 4.2 Category-Agnostic Semantic Matching and Injection Isolation
- Files: `src/leash/engine/classifier/history.py`, `src/leash/engine/classifier/jev.py`, `src/leash/engine/evaluate.py:29-37`
- Observation:
  1. Feature derivation in `HistoryIndex` derives 50 strictly numerical features from historical purchase events without relying on hardcoded category branches.
  2. The Jev semantic assessment prompt (`jev.py:22-47`) receives only numerical features (`values`, `missing`, `support`) from `HistoryFeatures`. It never receives raw merchant text, product descriptions, or user instructions, providing complete isolation against merchant prompt injection attacks.
  3. Extraction pass 2 (merchant text LLM) remains removed per owner ruling; deterministic extraction pass 1 with quarantine on injected instructions (`_quarantine` in `evaluate.py:29-37`) is preserved.

### 4.3 Engine, Extract, Runner, and App Integration
- Files: `src/leash/engine/evaluate.py:43-105`, `src/leash/engine/model_checks.py:11-82`, `scripts/classifier_replay.py:84-90`
- Observation:
  1. `evaluate` accepts optional `assessments: AssessmentBundle | None = None`.
  2. When `assessments` is provided, `validate_assessments` revalidates the bundle against the active `Event`, `PolicyDraft`, and `MandateState`:
     - Checks `event.authorization.card_id == event.mandate.card_id` and `event.authorization.mandate_id == event.mandate.mandate_id`.
     - Checks `state.mandate_id == event.mandate.mandate_id`.
     - Checks `bundle.authorization_id == event.authorization.authorization_id`.
     - Checks `bundle.purchase_digest == assessment_purchase_digest(event, bundle.features)`.
     - Checks `bundle.policy_hash == policy.hash`.
     - Checks `bundle.as_of == event.authorization.timestamp`.
     - Checks `bundle.features.customer_id == event.mandate.customer_id` and `bundle.features.card_id == event.mandate.card_id`.
  3. `model_checks(bundle)` converts `bundle.behaviour` and `bundle.semantic` into `Check` objects with `source="model"` and `result in {"pass", "uncertain"}`.
  4. Decision precedence is strictly preserved:
     - Hard rule failures (`fails`) result in `decline`, regardless of model outputs.
     - Model checks never produce `result="fail"`, never satisfy required facts, and cannot overturn hard rule failures.
     - In the model-off replay (`bundle.behaviour=None`, `bundle.semantic=None`), `model_checks` yields `[]`, adding zero checks or decision side effects.
  5. Honest boundary: Runner integration (`src/leash/runner/`) still invokes `evaluate` without assessments. M1b does not claim live runner integration.

### 4.4 Customer Step-Up and Behavioral Escalation
- Files: `src/leash/engine/classifier/behaviour.py:95-100`, `src/leash/engine/model_checks.py:43-50`, `docs/eval/classifier/m1-all-45.csv`
- Observation:
  1. Replay over the 45 attempts produces 2 step-up outcomes (AU0026 and AU0040) resulting strictly from deterministic checks (`new_device` and `injected_instructions`).
  2. In `BehaviorModel.score()`, `escalation_fired=False` is hardcoded. `__init__` enforces that `artifact_release_status == "evaluation_only_no_operational_threshold"` and `threshold_status == "proposals_only_owner_O4_pending"`. The evaluation model cannot trigger step-up.
  3. When tested synthetically with `escalation_fired=True` on an approved attempt (e.g. AU0001 with policy uncertainty `ask`), `model_checks` outputs `Check(name="model.behaviour", result="uncertain")`, which `evaluate` maps to `step_up` with reason code `model_history_uncertain`.

### 4.5 Cancellation Claims and Deadline Behaviour
- Files: `scripts/classifier_replay.py:91-92`, `src/leash/engine/classifier/jev.py:19-21, 113-119`
- Observation:
  1. `classifier_replay.py` checks `datetime.now(UTC) >= event.deadline_at` after each attempt and raises `TimeoutError` if exceeded.
  2. Standalone Jev execution enforces strict deadline reserves (`DEADLINE_RESERVE_SECONDS = 2.25` and `MINIMUM_RECHECK_SECONDS = 2.0`).
  3. No network cancellation or live simulator cancellation is claimed.

### 4.6 Authorization and Per-Customer Isolation
- Files: `src/leash/engine/classifier/history.py:255-279`, `src/leash/engine/model_checks.py:18-33`
- Observation:
  1. `HistoryIndex` partitions transactions strictly by `customer_id` and `card_id`. Historical counts and sums are computed strictly pre-event using `bisect_left` over `(timestamp, authorization_id)`.
  2. `validate_assessments` validates that `bundle.features.customer_id == event.mandate.customer_id` and `bundle.features.card_id == event.mandate.card_id`, preventing any cross-customer feature injection.

### 4.7 Digest Provenance and Post-Scoring Integrity
- Files: `src/leash/contracts/classifier.py:108-118`, `src/leash/engine/model_checks.py:25-26`
- Observation:
  1. `assessment_purchase_digest(event, features)` canonicalizes `authorization`, `mandate_id`, `customer_id`, `card_id`, and all 50 `features` as sorted JSON (with `allow_nan=False`), computing its SHA-256 digest.
  2. If any feature value is modified after scoring, or if the bundle is attached to a different authorization, `validate_assessments` detects the mismatch and raises `ValueError: <auth_id>: assessment purchase digest differs`.

### 4.8 Jev Provider Validation and Fail-Closed Behavior
- Files: `src/leash/contracts/classifier.py:54-87`
- Observation:
  1. `JevAnswer` validates that probability options match `{"ordinary", "unusual", "unclear"}` and sum to 1.0 within $10^{-6}$.
  2. `SemanticAssessment` validates that `requested_model == served_model` and that both `spend_pattern` and `activity_pattern` questions are answered.
  3. Violations raise Pydantic `ValidationError` / `ValueError` loudly without fallbacks.

---

## 5. Commands Actually Run and Observed Outputs

All commands were executed in detached grading checkout `/private/tmp/classifier-m1b-r1-gemini`:

1. **Pre-review commit and working tree verification**:
   - Command: `git rev-parse HEAD && git status --porcelain`
   - Output: `e4ba7ba1f0707164ddfd6071779501a880598b44`, clean working tree.

2. **Pre-review 22-path manifest verification**:
   - Command: `shasum -a 256 -c docs/reviews/classifier/M1b/r1/MANIFEST.sha256`
   - Output: All 22 files returned `OK`.

3. **Git commit history and diff inspection**:
   - Command: `git log --oneline 49646be..HEAD && git diff --stat 49646be..HEAD`
   - Output: Exactly 2 commits (`e4ba7ba` freeze, `76363be` shared assessment contracts in replay); 10 files changed (47 insertions, 96 deletions), including deletion of `types.py`.

4. **Replay over 45 public attempts with shared assessment bundles**:
   - Command:
     ```bash
     PYTHONPATH=src /Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python scripts/classifier_replay.py \
       --policy SCEN0000=docs/eval/replay-policies/SCEN0000.json \
       --policy SCEN0001=docs/eval/replay-policies/SCEN0001.json \
       --policy SCEN0002=docs/samples/scen0002_draft.json \
       --policy SCEN0003=docs/eval/replay-policies/SCEN0003.json \
       --policy SCEN0004=docs/eval/replay-policies/SCEN0004.json \
       --output /private/tmp/gemini_m1b_replay.csv
     ```
   - Output: `classifier history replay: 45 attempts, model effect off`; 11 approve, 32 decline, 2 step-up.

5. **Parity check of replay results against baseline evidence**:
   - Command: Executed Python script comparing `/private/tmp/gemini_m1b_replay.csv` against `docs/eval/classifier/m1-all-45.csv` across all columns except `elapsed_ms`.
   - Output: `All 45 rows match perfectly across all non-timing fields!`.

6. **Offline composition and digest integrity check (AU0001)**:
   - Command: Python script constructing `AssessmentBundle` with real Jev response from `docs/eval/classifier-composition-2026-09-25.json` and `BehaviorAssessment` (score 0.029953).
   - Output:
     - Baseline and assessed evaluation both returned `approve` with `['within_policy']`.
     - Model evidence checks: 3 checks (`model.behaviour`, `model.jev.activity_pattern`, `model.jev.spend_pattern`).
     - Setting `escalation_fired=True` produced `step_up` with `['model_history_uncertain']`.
     - Mutating a feature value raised `ValueError: AU0001: assessment purchase digest differs`.

7. **Jev contract edge-case and fail-closed validation**:
   - Command: Python script testing `JevAnswer` and `SemanticAssessment` with:
     - Probabilities summing to 0.90 -> Caught `Value error, history answer probabilities do not sum to one`.
     - Incorrect argmax `selected` -> Caught `Value error, history answer selection differs from its unique argmax`.
     - Model substitution (`served_model='openai/gpt-4o'`) -> Caught `Value error, served assessment model differs from the requested model`.
     - Missing question -> Caught `Value error, history assessment must answer each requested question exactly once`.

8. **BehaviorModel verification**:
   - Command: Python script loading `BehaviorModel()` and scoring AU0001.
   - Output: Loaded candidate `catboost`, artifact version `e4815c567707...`. Score: `0.029953195661059726`, `escalation_fired: False`.

9. **HistoryIndex additional pack validation (140,096 transactions)**:
   - Command: Python script iterating `HistoryIndex().historical_purchases('additional')`.
   - Output: Processed 140,096 rows in 27.20s; 542 rows with zero customer approved purchases; 46,759 rows with at least one undefined feature. Zero validation errors.

10. **Schema version check in `scripts/classifier_fit.py`**:
    - Command: Python script verifying `classifier_fit.FEATURE_SCHEMA_VERSION == 'hist-1'`.
    - Output: Verified identical to shared contract `FEATURE_SCHEMA_VERSION`.

11. **Post-review manifest and git tree verification**:
    - Command: `shasum -a 256 -c docs/reviews/classifier/M1b/r1/MANIFEST.sha256 && git status --porcelain`
    - Output: All 22 files `OK`, working tree clean.

---

## 6. Limitations and Exclusions

1. **No Live Runner Hookup**: The runner (`src/leash/runner/`) does not yet pass assessments into `evaluate`. Full M1 remains dependent on runner integration.
2. **No Operational Threshold**: The CatBoost model artifact remains evaluation-only (`artifact_release_status == "evaluation_only_no_operational_threshold"`). It cannot escalate.
3. **No Live Network Calls**: AU0001 composition used pre-captured Jev responses. No live OpenRouter, provider, or simulator requests were made during this review.
4. **No Unit Test Suites**: In accordance with AGENTS.md Section 6, no test suites, test files, or linters were run. Verification was conducted through one-off read and execution checks.

---

## 7. Report File Integrity

- External Report Path: `/private/tmp/classifier-review-reports/M1b/r1/gemini/report.md`
- Target Commit: `e4ba7ba1f0707164ddfd6071779501a880598b44`
- Base Commit: `49646be2cc3ed07486cabdebbac042d835eaf30c`
