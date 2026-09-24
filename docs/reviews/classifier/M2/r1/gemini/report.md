# Classifier M2 Review Report (Round r1)

- Reviewer: classifier_review_gemini_m2
- Role: default
- Space: zurichbuchegg
- Lens: Current contracts, category-agnostic semantic matching, engine/extract/runner/app integration, customer step-up, cancellation claims, and deadline behaviour.
- Verdict: APPROVE

## 1. Target Identification and Verification

- Frozen target commit: f5d27c80ed3862473852ae2ed3a802190ca13fc5 on lane/classifier
- Base commit: 0b7c2c1d1b4021a835a237e92f8491e33c6d5e25 (origin/main)
- Cleared M1a history baseline: e9974121fc47320dc7fabb9ddb280a517d1116cc
- Detached checkout: /private/tmp/classifier-m2-r1-gemini
- External report path: /private/tmp/classifier-review-reports/M2/r1/gemini/report.md
- Manifest check: `shasum -a 256 -c docs/reviews/classifier/M2/r1/MANIFEST.sha256` verified all 19 paths OK before review.
- Git working tree: clean, zero untracked or staged files.

Key document and artifact SHA-256 digests:
- docs/eval/classifier/model-evaluation-only.joblib: e4815c5677073c4e985c56f09f045be3d72c4e3ae624b75f9d06870630c828cf
- docs/eval/classifier/model-manifest.json: 3e9022aa98223d962e8beee29c0a5cbb0a10b093ff1a7fee916c6703b750ec0e
- docs/eval/classifier/split-manifest.json: 3292abbe5b9722642bfcd23fcc9f03002168364da2556daeeda65df0e270e51a
- docs/eval/classifier/m2-report.md: 871823fc962a1efa9ce315c44bf0e0cc205b93d77f7d2b9fa2e2e55c0d193a34
- docs/eval/classifier/feature-schema.md: 91fab4bf5951054e034d2c51354342bd42c47bba8c10e2d212002925fc6b3314
- docs/plans/02-classifier-contract-draft.patch: bef92c5feecf437137d01fc7085fbccd67784998fe12480c44ae74eb30b13a93

## 2. Model Pin and Effort Verification

- Requested persona model: gemini-3.8-flash (.cotal/agents/classifier_review_gemini.md:6)
- Requested persona effort variant: high (.cotal/agents/classifier_review_gemini.md:7)
- Recorded Cotal orientation pin: gemini-3.8-flash (cotal_orientation: "Model pin: gemini-3.8-flash (from COTAL_MODEL / the agent file)")
- Harness runtime environment observation: JCODE_OPENROUTER_MODEL=gpt-5.6-sol was set in the local cliproxy environment profile, while Cotal session identity and orientation record the gemini-3.8-flash pin with variant high.

## 3. Findings by Review Lens

### 3.1 Current Contracts

- Source reference: src/leash/contracts/, docs/contracts.md, docs/plans/02-classifier-contract-draft.patch
- Observation: Base contracts in src/leash/contracts/ and docs/contracts.md remain completely untouched compared to origin/main (git diff 0b7c2c1d1b4021a835a237e92f8491e33c6d5e25..HEAD -- src/leash/contracts/ docs/contracts.md returned no output).
- Observation: Proposal P1/P2 (Check.source="model", AssessmentBundle, BehaviorAssessment, SemanticAssessment, HistoryFeatures) is preserved as an unapplied patch in docs/plans/02-classifier-contract-draft.patch.
- Observation: Classifier-specific types used in M2 are defined strictly in src/leash/engine/classifier/types.py, keeping lane-specific types decoupled from main contracts.

### 3.2 Category-Agnostic Semantic Matching

- Source reference: src/leash/engine/classifier/history.py:203-233, src/leash/extract/facts.py:40-49, scripts/classifier_fit.py:117-118
- Observation: History feature derivation matches category by exact string equality against row["merchant_category"] without hardcoded category names or branch heuristics.
- Observation: In scripts/classifier_fit.py, only numeric values from HistoryFeatures enter the feature matrix. No category strings, merchant text, or IDs are used as predictors.
- Observation: In src/leash/extract/facts.py:40-49, _product_type normalizes structured item names across all product categories without special handling for specific categories like shoes or electronics.

### 3.3 Engine, Extract, Runner, and App Integration

- Source reference: src/leash/engine/evaluate.py, src/leash/runner/, src/leash/api/
- Observation: Core decision evaluation (src/leash/engine/evaluate.py), simulator runner (src/leash/runner/), and API/app routes (src/leash/api/) have no imports of src/leash/engine/classifier/ modules.
- Observation: Pyproject dependencies keep ML packages (numpy, scikit-learn, catboost) in an optional dependency group [dependency-groups] classifier in pyproject.toml:17-22. Core modules import cleanly without requiring classifier dependencies.
- Observation: M2 makes no P1/P2 engine integration claims and no live runner claims.

### 3.4 Customer Step-Up

- Source reference: src/leash/engine/classifier/behaviour.py:95-100, docs/eval/classifier/m2-report.md:55-66
- Observation: In BehaviorModel.score(), escalation_fired is hardcoded to False. The evaluation model cannot trigger customer step-up.
- Observation: The June 16-30 threshold proposals in m2-report.md and model-manifest.json are explicit evaluation proposals for owner decision O4. No operational threshold is active.
- Observation: No customer answers or step-up resolution flows are simulated or altered in M2.

### 3.5 Cancellation Claims

- Source reference: docs/eval/classifier/m2-report.md:73-74, docs/plans/02-classifier-design.md:50
- Observation: M2 involves offline model fitting and historical evaluation. No platform-confirmed cancellation or local cancellation is claimed.

### 3.6 Deadline Behaviour

- Source reference: src/leash/engine/classifier/behaviour.py:72-100, scripts/classifier_fit.py:253-255
- Observation: BehaviorModel.score() performs in-memory NumPy vector transformations and CatBoost/calibrator inferences without network calls or blocking IO, completing in sub-millisecond time.
- Observation: Data loading and feature generation over 140,096 historical transactions completed in 26.74 seconds.

### 3.7 M2 ML Methodology, Splits, Calibration, and Integrity

- Source reference: docs/eval/classifier/split-manifest.json, scripts/classifier_fit.py, docs/eval/classifier/m2-report.md
- Strict pre-event features: Computed via HistoryIndex._prior using bisect_left over (timestamp, authorization_id) tuples, strictly excluding current and future transactions.
- Additional-pack-only fitting: Only viseca-2026/additional-data-history/ purchases were used for fitting, selection, calibration, and July evaluation. Base-pack customers (20 customers) are completely excluded from fitting.
- Customer split: Fixed 400 fitting customers and 100 reserved customers with 0 overlap (split-manifest.json).
- Time windows: Fit (through April 30, 2026), Selection (May 2026), Refit (through May 31, 2026), Calibration (June 1-15, 2026), Threshold proposals (June 16-30, 2026), Evaluation (July 2026).
- Candidate selection: Logistic Regression vs CatBoost evaluated on May PR-AUC. CatBoost scored 0.5042 vs LR 0.4722 and was selected.
- Seen / held-out separation: In July evaluation, reserved-customer rows (held-out) lead as the primary generalization estimate; seen-customer rows are explicitly labeled selection-informed per G1 disposition.
- Deterministic-pass proxy honesty: The issuer-rule-pass proxy accurately models card status, online/international switches, transaction limits, and calendar month spend from history, openly disclaiming full mandate evaluation.
- Small-slice handling: Metric calculations suppress PR-AUC and ROC-AUC for slices with fewer than 30 rows or fewer than 5 positive/negative outcomes, marking them unavailable.
- Model artifact integrity: model-evaluation-only.joblib (SHA-256 e4815c5677073c4e985c56f09f045be3d72c4e3ae624b75f9d06870630c828cf) and model-manifest.json (SHA-256 3e9022aa98223d962e8beee29c0a5cbb0a10b093ff1a7fee916c6703b750ec0e) match the manifest and report.
- Absence of runtime fallbacks: If inputs have incorrect schema versions, invalid distributions, non-finite values, or checksum mismatches, BehaviorModel raises ValueError directly without default score substitution.

## 4. Commands Actually Run and Observed Outcomes

1. `git rev-parse HEAD`: returned f5d27c80ed3862473852ae2ed3a802190ca13fc5.
2. `git status --porcelain`: clean, no output.
3. `shasum -a 256 -c docs/reviews/classifier/M2/r1/MANIFEST.sha256`: all 19 paths OK.
4. `git log --oneline 0b7c2c1d1b4021a835a237e92f8491e33c6d5e25..HEAD`: inspected all intermediate commits on lane/classifier.
5. `git diff --stat 0b7c2c1d1b4021a835a237e92f8491e33c6d5e25..HEAD -- src/`: verified changes under src/ are isolated to src/leash/engine/classifier/.
6. `git diff 0b7c2c1d1b4021a835a237e92f8491e33c6d5e25..HEAD -- src/leash/contracts/ docs/contracts.md`: confirmed zero contract modifications.
7. Verification of customer split via python: 400 fitting customers, 100 reserved customers, 0 overlap.
8. Verification of core leash module imports without classifier: leash.contracts, leash.engine.evaluate, leash.policy, leash.runner, leash.api all imported successfully.
9. Verification of BehaviorModel: loaded catboost model, verified 50 features, scored historical purchase with score 0.0581, escalation_fired=False.
10. Verification of observable errors: scoring with hist-0 schema raised "purchase feature schema differs from model"; scoring with mismatched feature names raised "purchase feature names differ from model".
11. Verification of 45 public attempt scoring: all 45 public attempts scored with min 0.0300, median 0.0499, max 0.2364, and escalation_fired=False.
12. Verification of AU0035 score: scored 0.097382 with escalation_fired=False.
13. Verification of no-device historical row TR100011: scored 0.027787 with escalation_fired=False.
14. Final manifest check: `shasum -a 256 -c docs/reviews/classifier/M2/r1/MANIFEST.sha256` verified all 19 paths OK after review.

## 5. Limitations

- CatBoost serialization non-determinism: The artifact hash differed between two fit runs despite numerical equivalence on 1,000 raw probabilities and calibrator coefficients. The initial run is preserved outside the tree at /private/tmp/classifier-m2-initial-20260925/, and this report checks the second, committed artifact.
- Merchant distribution shift: Public evaluation scenarios show higher merchant novelty (missing customer_merchant_last_approved_days on 17.8% of attempts) than July historical agent purchases (2.5% missing), indicating that offline July calibration cannot be assumed to apply directly to the public test set.
- Reserved agent score band underprediction: In July evaluation, the reserved agent 0.0-0.1 band underpredicts observed declines (mean score 0.0285 vs observed rate 0.0487), and sparse sample sizes preclude calibration claims in higher score bands.

## 6. Verdict

APPROVE classifier M2 target f5d27c80ed3862473852ae2ed3a802190ca13fc5 on lane/classifier.
