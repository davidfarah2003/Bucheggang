# Classifier M1a Review Report (Round r2)

- Reviewer: classifier_review_gemini (role: default)
- Date: 2026-09-25
- Space: zurichbuchegg
- Worktree: /private/tmp/classifier-m1a-r2-gemini
- Report path: /private/tmp/classifier-review-reports/M1a/r2/gemini/report.md

---

## 1. Verdict

APPROVE classifier M1a r2 at commit e9974121fc47320dc7fabb9ddb280a517d1116cc (base 498898155272e17b9907c364d723a503541ad6fc, preceding r1 target 1f5a45da0d0b12d53ec4268de1f683052ce65fba).

The round r2 corrections resolve all reviewer findings from round r1. Feature maps are bound cryptographically into the purchase digest, missing account limits produce descriptive ValueErrors, purchase rows enforce the human and agent initiator domain, scenario replay enforces strict tuple key progression, and full 45-attempt replay reproduces base replay results across current policy drafts.

This approval covers the self-contained M1a history extraction and model-off replay cut. It does not approve engine-owned P1/P2 integration or live runner execution.

---

## 2. Target Identification and Hash Verification

- Target HEAD commit: e9974121fc47320dc7fabb9ddb280a517d1116cc
- Base commit: 498898155272e17b9907c364d723a503541ad6fc
- Preceding r1 target: 1f5a45da0d0b12d53ec4268de1f683052ce65fba
- Manifest file: docs/reviews/classifier/M1a/r2/MANIFEST.sha256
- Manifest SHA-256: c3c06aea01e7f2d5fdd1850998261cec61995d0765c3487bbce59017fc53af33
- Target status: Clean worktree; detached HEAD at e9974121fc47320dc7fabb9ddb280a517d1116cc. All 25 manifest files verified with shasum -a 256 -c before and after inspection.
- Preceding r1 report: Preserved intact at /private/tmp/classifier-review-reports/M1a/r1/gemini/report.md with SHA-256 68e01cbc704f1da33e8a2d4fe9852aae777c5f4f0738abfa37a6c65e2105ecc1.

---

## 3. Actual Model Pin and Effort Verification

- Persona specification: .cotal/agents/classifier_review_gemini.md declares agent jcode, model gemini-3.8-flash, variant high.
- Recorded model pin: cotal_orientation confirmed Model pin: gemini-3.8-flash.
- Effort verification: Requested variant high was submitted and accepted by the launcher. Upstream provider cliproxy via openai-compatible does not expose an active reasoning tier for gemini-3.8-flash. Requested high effort was accepted by the connector, but is not observable as an active thinking tier in-seat.

---

## 4. Verification of Round r2 Corrections

### 4.1 Resolution of Grok r1 Finding N1: Full Feature Map Binding
- File: src/leash/engine/classifier/assess.py:14-48
- Observation: purchase_digest() takes both event and features, serializing features.model_dump(mode="json") into the hashed payload. validate_bundle() recomputes purchase_digest(event, bundle.features) and raises ValueError if mismatched.
- Verification: Mutating customer_merchant_approved_count in bundle.features raised ValueError: AU0035: assessment purchase digest differs.

### 4.2 Resolution of Grok r1 Finding N2: Descriptive ValueError on Missing Account Limits
- File: src/leash/engine/classifier/history.py:268-271
- Observation: for_event() looks up limits with self._limits.get(card_id). If absent, it raises ValueError(f"{auth.authorization_id}: account limits unavailable for mandate card").
- Verification: Simulating an absent card limit raised ValueError: AU0035: account limits unavailable for mandate card.

### 4.3 Resolution of GLM r1 Finding G2: Explicit Initiator Domain
- File: src/leash/engine/classifier/history.py:141-142, docs/eval/classifier/feature-schema.md
- Observation: During historical index construction, rows with transaction_type == "purchase" must have initiator_type in {"agent", "human"}. Non-conforming rows raise ValueError. Merchant-initiated rows in the pack are refunds.
- Verification: All purchase rows across base and additional packs were verified to have initiator_type in {"agent", "human"}. Any other initiator raises immediately.

### 4.4 Resolution of GLM r1 Finding G3: Strict Key Progression in Replay
- File: scripts/classifier_replay.py:78-81
- Observation: Scenario rows are verified against current_key = (event.authorization.timestamp, auth_id). If current_key <= previous_key, classifier_replay.py raises ValueError(f"{scenario_id}/{auth_id}: scenario event-time key did not advance").
- Verification: Enforces strict monotonically advancing (timestamp, authorization_id) tuple ordering.

### 4.5 Full 45-Attempt Decision Replay
- File: scripts/classifier_replay.py, docs/eval/classifier/m1-all-45.csv
- Observation: Replay across all five scenarios (SCEN0000 to SCEN0004) produced 45 attempts: 11 approve, 32 decline, 2 step_up.
- Verification: Re-running scripts/classifier_replay.py on all 5 policy drafts generated identical decisions and reason codes matching docs/eval/classifier/m1-all-45.csv and the base scripts/replay.py run.

### 4.6 Optional Classifier Dependency Group
- File: pyproject.toml:17-22, uv.lock
- Observation: Optional ML dependencies (numpy, scikit-learn, catboost) are declared under [dependency-groups] classifier, keeping main runtime dependencies clean. No models are fitted or called in live code.

---

## 5. Commands Actually Run and Observed Outputs

1. Pre-review git verification in /private/tmp/classifier-m1a-r2-gemini:
   - Command: git rev-parse HEAD && git status --porcelain && shasum -a 256 -c docs/reviews/classifier/M1a/r2/MANIFEST.sha256
   - Output: HEAD e9974121fc47320dc7fabb9ddb280a517d1116cc, clean working tree, all 25 manifest files OK.

2. One-off classifier replay over all 45 public attempts:
   - Command: PYTHONPATH=src python3 scripts/classifier_replay.py with 5 scenario policy drafts into /private/tmp/classifier-gemini-all45-test.csv
   - Output: 45 attempts executed (11 approve, 32 decline, 2 step_up).

3. Comparison of replay output against committed evidence:
   - Command: Python script comparing /private/tmp/classifier-gemini-all45-test.csv with docs/eval/classifier/m1-all-45.csv excluding elapsed_ms.
   - Output: All 45 rows matched identically across all columns.

4. Verification of feature map mutation detection:
   - Command: Python execution mutating bundle.features.values["customer_merchant_approved_count"] before validate_bundle().
   - Output: Caught expected ValueError: AU0035: assessment purchase digest differs.

5. Verification of descriptive error on missing account limits:
   - Command: Python execution simulating missing limit in self._limits.
   - Output: Caught expected ValueError: AU0035: account limits unavailable for mandate card.

6. Verification of purchase initiator domain:
   - Command: Python execution checking initiator_type of all purchase rows across base and additional packs.
   - Output: All historical purchase rows verified to have initiator_type in {agent, human}.

7. Post-review git verification:
   - Command: git rev-parse HEAD && git status --porcelain && shasum -a 256 -c docs/reviews/classifier/M1a/r2/MANIFEST.sha256
   - Output: Clean tree at e9974121fc47320dc7fabb9ddb280a517d1116cc, all 25 manifest files OK.

---

## 6. Limitations

- Scope boundary: This review approves only the self-contained M1a cut. Shared contract changes and runner integration remain engine-owned and unmerged.
- Model effects: Replay operates strictly with model effects off.
- Provider calls: No paid model or simulator calls were executed during review.
