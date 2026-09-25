# Classifier M1 Review Report (Round r1) — Gemini

## 1. Verdict
**APPROVE** classifier full M1 integration @ `04cc78c8f70c425b17d5ded022cc45f77520a1c0` (base `b14a56aef191775eb89e8820e70d23c3a6c8464a`).

---

## 2. Target Identification & Hash Verification

- **Target Head Commit**: `04cc78c8f70c425b17d5ded022cc45f77520a1c0`
- **Base Commit**: `b14a56aef191775eb89e8820e70d23c3a6c8464a`
- **Working Tree**: `/private/tmp/classifier-m1-full-r1-gemini` (clean detached grading checkout, verified before and after review).
- **Commit Subject**: `Merge pull request #126 from davidfarah2003/lane/runner-history-only` (commit `32a4dd0`: `feat(runner): bind personal history in model-off evaluation`).
- **Diffstat**: 2 files changed, 9 insertions(+), 2 deletions(-):
  - `docs/plans/05-simulator-runner.md` (+3 lines)
  - `src/leash/runner/evaluation.py` (+6 lines, -2 lines)

---

## 3. Actual Model Pin & Effort Verification

- **Persona**: `.cotal/agents/classifier_review_gemini.md`
- **Configured Model**: `gemini-3.8-flash`
- **Reported Model Pin**: `gemini-3.8-flash` (confirmed via `cotal_orientation` and `gemini.launch.log`).
- **Requested Effort**: `high` (verified in `gemini-brief.txt` and persona definition; explicitly requested and not omitted).
- **Accepted Effort Tier**: Served by provider `cliproxy` via `openai-compatible:cliproxy`. The exact accepted internal reasoning tier is unobservable in-seat from provider response headers or seat metadata. High effort was requested and not silently omitted.

---

## 4. Findings by Review Lens

### 4.1 Shared Assessment Contracts
- **Files**: `src/leash/contracts/classifier.py:15-118`, `src/leash/contracts/__init__.py:32, 44`
- **Finding**: 
  - Contracts (`HistoryFeatures`, `BehaviorAssessment`, `JevAnswer`, `SemanticAssessment`, `AssessmentBundle`) adhere strictly to the shared schema standard (`FEATURE_SCHEMA_VERSION = "hist-1"`).
  - `HistoryFeatures` validates timezone presence on `as_of`, enforces exact coverage of `values` by `support`, and requires exact coverage of `None` values by `missing` reasons.
  - `JevAnswer` enforces the required question set (`spend_pattern`, `activity_pattern`), probability distribution validity (finite range $[0, 1]$, sum $= 1.0 \pm 10^{-6}$), argmax agreement, and tie handling (`selected = None`).
  - `SemanticAssessment` enforces exact match between `requested_model` and `served_model`.
  - `AssessmentBundle` enforces consistent `as_of` timestamps with timezone, matching schema version, and local binding integrity via `assessment_purchase_digest(event, features)` (SHA-256 over authorization, mandate ID, customer ID, card ID, and feature dictionary).

### 4.2 HistoryOnlyEvaluator Selection in Runner Startup
- **Files**: `src/leash/runner/evaluation.py:110-119`, `src/leash/runner/settings.py:53-67`
- **Finding**:
  - `load_evaluator()` calls `load_evaluation()`. When `LEASH_ENABLE_MODELS` is unset or `"0"` (default), `configuration.models_enabled` is `False`.
  - Under `models_enabled = False`, `load_evaluator()` lazily imports `HistoryOnlyEvaluator` and `HistoryIndex`, instantiating and returning `HistoryOnlyEvaluator(HistoryIndex())`.
  - An invalid flag value (e.g. `"2"`) immediately raises `SettingsError("LEASH_ENABLE_MODELS must be 0 or 1")`.
  - When models are disabled, `ModelEvaluator` is not instantiated, `load_openrouter()` is not called, and neither provider credentials nor learned model manifests are accessed.

### 4.3 Evaluator and Replay Integration
- **Files**: `src/leash/engine/classifier/bridge.py:12-22`, `src/leash/engine/evaluate.py:66-137`, `src/leash/runner/stepups.py:98-106, 175-195`, `src/leash/runner/cli.py:64, 78`
- **Finding**:
  - `HistoryOnlyEvaluator` satisfies the `Evaluate` callable protocol: `__call__(event, policy, state, facts) -> Decision`.
  - Runner startup (`StepUpBook.__init__` in `stepups.py:100`) binds `self.evaluator = load_evaluator()`, which is passed to `loop.run_loop`.
  - Pending step-up rechecks (`StepUpBook._evaluate_pending` in `stepups.py:194`) evaluate using the same `self.evaluator`.
  - Under `HistoryOnlyEvaluator`, `bundle = history_bundle(event, policy, self.history)` creates an `AssessmentBundle` with pre-event `features` and `behaviour=None, semantic=None`.
  - In `evaluate()`, `validate_assessments(event, policy, state, assessments)` verifies authorization, mandate, customer, card, policy hash, and purchase digest integrity.
  - Because `bundle.behaviour` and `bundle.semantic` are `None`, `model_checks(assessments)` returns `[]`, adding zero synthetic or uncertain checks to evidence.

### 4.4 Decision and Reason Parity
- **Files**: `src/leash/engine/evaluate.py`, `scripts/replay.py`
- **Finding**:
  - Evaluated across all 45 public scenario attempts across SCEN0000, SCEN0001, SCEN0002, SCEN0003, and SCEN0004 under sequential replay with state accumulation.
  - Both baseline pure `evaluate` and `HistoryOnlyEvaluator` produce exactly:
    - 11 `approve`
    - 32 `decline`
    - 2 `step_up` (SCEN0003 AU0026 with `['new_device']`, and SCEN0004 AU0040 with `['item_mismatch', 'injected_instructions']`).
  - Every single decision outcome and reason code array matches row-for-row with 100% parity against the committed baseline replay dataset.
  - Execution is fast and bounded: average `HistoryOnlyEvaluator` invocation latency across the 45 events is 0.820 ms (maximum 1.778 ms).

### 4.5 Missing Facts Failure
- **Files**: `src/leash/engine/classifier/bridge.py:18-19`, `src/leash/runner/evaluation.py:51-52`
- **Finding**:
  - `HistoryOnlyEvaluator` enforces the requirement that merchant-text extraction must be performed: calling `evaluator(event, policy, state, facts=None)` immediately raises `ValueError(f"{event.authorization.authorization_id}: extraction facts are missing")`.
  - Verified by independent probe.

### 4.6 No Heavy Model or Key Load When Models Are Off
- **Files**: `src/leash/runner/evaluation.py:110-119`, `src/leash/runner/settings.py:53-80`
- **Finding**:
  - Verified `sys.modules`: none of `numpy`, `catboost`, `sklearn`, `anthropic`, `torch`, or `transformers` are loaded when `load_evaluator()` runs with `LEASH_ENABLE_MODELS=0` or unset.
  - Verified `load_openrouter.cache_info()`: `hits=0, misses=0, maxsize=1, currsize=0`.
  - Verified `load.cache_info()`: `hits=0, misses=0, maxsize=1, currsize=0`.
  - Zero credential reads or network calls occur during model-off evaluation startup and execution.

### 4.7 Customer and Card Data Ownership
- **Files**: `src/leash/engine/classifier/history.py:89-137, 258-279`, `src/leash/engine/model_checks.py:11-33`
- **Finding**:
  - `HistoryIndex` loads accounts and cards from both organizer packs (`viseca-2026/data` and `viseca-2026/additional-data-history`), asserting customer and account card ownership consistency.
  - `HistoryIndex.for_event(event)` verifies:
    - `auth.card_id == mandate.card_id` and `auth.mandate_id == mandate.mandate_id` (mismatch raises `ValueError`).
    - `self._owners.get(card_id) == customer_id` (card belonging to another customer raises `ValueError`).
    - Account limits exist for the card (missing limits raises `ValueError`).
  - `validate_assessments` additionally checks customer ID and card ID consistency before evaluation.

### 4.8 Distinction Between Offline Evidence and Live Wallet Answers
- **Files**: `scripts/replay.py:193-214`, `src/leash/runner/stepups.py:152-211`
- **Finding**:
  - Offline replay (`scripts/replay.py`) projects approvals into memory and leaves step-up decisions pending in `state.pending_step_ups`. It does not invent or simulate customer approvals, does not write persistent step-up records to disk, and makes no API calls to `/v1/authorizations/{id}/resolve`.
  - Live runner execution (`StepUpBook`) records pending step-ups atomically on disk. Resolution requires a real human response via the Wallet UI within the human window (`human_window_s()`), or expiration to decline (`step_up_timeout`) by the background sweeper.

### 4.9 Category-Agnostic Semantic Matching & Prompt Injection Isolation
- **Files**: `src/leash/extract/facts.py:46-55, 103-111`, `src/leash/engine/classifier/jev.py:22-47`
- **Finding**:
  - Extraction normalizes product types across categories without domain-specific branching.
  - Classifier questions (`spend_pattern`, `activity_pattern`) operate exclusively on numeric aggregate features from `HistoryFeatures` (`hist-1`).
  - Unstructured merchant text and item strings are never passed to the risk classification prompts, ensuring full category agnosticism and prompt injection resilience.

### 4.10 Cancellation Claims & Deadline Behaviour
- **Files**: `src/leash/runner/loop.py:147-177, 213-245`, `src/leash/runner/intents.py:23, 56, 186-187`, `src/leash/runner/evaluation.py:23-26, 53-64`
- **Finding**:
  - Mandate revocation (`DELETE`) is tracked through the `Coordinator` and reconciled in `intents.py`.
  - Deadline guards enforce strict timeout margins (`GUARD_MARGIN_S = 1.0`, `EXTRACT_RESERVE_S = 2.0`, `MODEL_RESERVE_S = 2.0`). If an operation exceeds its allowance, a timeout exception is raised. In accordance with AGENTS.md Section 6, no fallback or substitute decision is ever generated.

---

## 5. Commands Actually Run and Observed Outputs

1. **Git target and status checks**:
   - `git rev-parse HEAD` -> `04cc78c8f70c425b17d5ded022cc45f77520a1c0`
   - `git rev-parse b14a56aef191775eb89e8820e70d23c3a6c8464a` -> `b14a56aef191775eb89e8820e70d23c3a6c8464a`
   - `git status --porcelain` -> clean (no output)
   - `git diff --stat b14a56aef191775eb89e8820e70d23c3a6c8464a..HEAD` -> 2 files changed, 9 insertions(+), 2 deletions(-)

2. **Evaluator selection and module isolation probe**:
   - Command: `uv run python -c "from leash.runner.evaluation import load_evaluator; from leash.engine.classifier.bridge import HistoryOnlyEvaluator; assert isinstance(load_evaluator(), HistoryOnlyEvaluator)"`
   - Output: `HistoryOnlyEvaluator selected successfully!`
   - Prohibited modules check (`numpy`, `catboost`, `sklearn`, `anthropic`, `torch`, `transformers`): `Loaded prohibited modules: []`.
   - Credential cache check: `load_openrouter` hits=0/misses=0; `load` hits=0/misses=0.

3. **Missing facts failure check**:
   - Command: `evaluator(event, policy, state, facts=None)`
   - Output: Successfully raised `ValueError: AU0012: extraction facts are missing`.

4. **Card and customer ownership mismatch probe**:
   - Command: Altered `card_id` to `card_wrong_12345` on event authorization.
   - Output: Successfully raised `ValueError: AU0012: authorization and mandate identity differ`.
   - Command: Altered `customer_id` to `cust_wrong_99999` on event mandate.
   - Output: Successfully raised `ValueError: AU0012: mandate card does not belong to customer`.

5. **Invalid enable flag check**:
   - Command: `LEASH_ENABLE_MODELS=2 load_evaluation()`
   - Output: Successfully raised `SettingsError: LEASH_ENABLE_MODELS must be 0 or 1`.

6. **Missing history pack check**:
   - Command: `HistoryIndex(packs={"base": Path("/nonexistent/pack")})`
   - Output: Successfully raised `FileNotFoundError: [Errno 2] No such file or directory: '/nonexistent/pack/accounts.csv'`.

7. **45-attempt sequential replay parity check**:
   - Command: Iterated all 45 public scenario attempts across SCEN0000 through SCEN0004 comparing baseline pure `evaluate` with `HistoryOnlyEvaluator`.
   - Output:
     - Total rows tested: 45
     - Decisions breakdown: `{'approve': 11, 'decline': 32, 'step_up': 2}`
     - Parity: 45 / 45 exact decision and reason codes match.
     - Latencies: max 1.778 ms, avg 0.820 ms, min 0.550 ms.

8. **StepUpBook pending recheck probe**:
   - Command: Initialized `StepUpBook` in temporary directory, added pending step-up for `SCEN0003 AU0026` (`['new_device']`), and executed `_evaluate_pending` with human budget.
   - Output: Successfully produced step_up with reason code `['new_device']`.

9. **Git tree re-verification**:
   - `git rev-parse HEAD` -> `04cc78c8f70c425b17d5ded022cc45f77520a1c0`
   - `git status --porcelain` -> clean.

---

## 6. Limitations

- Replay verification covered the 45 supplied public scenario attempts; private simulator scenarios were not available offline.
- No live network requests to the simulator API or live customer Wallet interactions were performed, in strict compliance with the review rules.

---

## 7. Observed Outcome

The full M1 integration cleanly connects `HistoryOnlyEvaluator` to the model-off runner startup path. It strictly adheres to all contracts, enforces customer/card ownership boundaries, raises loudly on missing facts or corrupted bindings, avoids loading heavy model dependencies or credentials, and demonstrates 100% row-for-row decision and reason parity across all 45 public attempts. Zero blockers observed.
