# Classifier M0 Review Report (Round r1)

- **Reviewer:** `classifier_review_gemini` (role: `default`)
- **Lens:** Current contracts, category-agnostic semantic matching, engine/extract/runner/app integration, customer step-up, cancellation claims, and deadline behaviour.
- **Date:** 2026-09-24
- **Working Tree:** `/private/tmp/classifier-m0-r1-gemini` (detached grading worktree)
- **External Report Path:** `/private/tmp/classifier-review-reports/M0/r1/gemini/report.md`

---

## 1. Verdict

**APPROVE** M0 contract proposal, scope re-anchoring, and ownership map.

The proposal in `docs/plans/02-classifier-m0.md` is thorough, meticulously grounded in the current codebase, verified against empirical runs on scenario data, and correctly addresses earlier review feedback (R1, R2, R3). It exposes existing race conditions, fallback paths, and lock desynchronizations across `engine`, `runner`, `extract`, and `app`, providing sound architectural proposals (P1–P5) and identifying necessary owner rulings (O1–O4) prior to implementation.

---

## 2. Target Identification & Hash Verification

- **Target Commit:** `d651ef85920925d36ece77fc5eaa4d13fff0bd8f` (on `lane/classifier`)
- **Base Commit:** `origin/main` at `ed2bc3cf0115419f46412536ba2d4e9524bbf7aa` (merged as `635398246e7f1ff3fae3ba1580f0c05561a3d93b`)
- **Primary Document:** `docs/plans/02-classifier-m0.md` (SHA-256: `acbad9174f6532d5a1e9283261c2ea7087c99dd8cd582d18ddfbd6dc8359e323`)
- **Manifest Verification:** Verified with `shasum -a 256 -c /private/tmp/classifier-review-reports/M0/r1/MANIFEST.sha256` before and after inspection. All 10 manifest files matched their exact SHA-256 hashes without modification.

---

## 3. Actual Model Pin & Effort Verification

- **Persona Specification:** `.cotal/agents/classifier_review_gemini.md` requests `model: gemini-3.8-flash`, `variant: high`.
- **Spawn Invocation:** Launched with `cotal spawn --config ... --model gemini-3.8-flash --variant high ...` (PID 10043, child host PID 10212).
- **Connector Translation:** `@cotal-ai/connector-jcode` sent `set_reasoning_effort` with `effort: "high"` to the Jcode daemon.
- **Jcode Harness Handling:** Request #6 (`request_kind=set_reasoning_effort`) was acknowledged and handled with `ok` by the Jcode daemon (`jcode-2026-09-24.log:304-307`).
- **Observed Upstream Behaviour:** In `jcode-2026-09-24.log:332`, `PROVIDER_CANONICAL_INPUT` logged `model=gemini-3.8-flash format=chat_completions thinking_enabled=None provider_features=false`. As anticipated by `docs/models.md:26` (`"gemini-3.8-flash (no effort tier; jcode refuses one for Gemini)"`), the cliproxy/OpenRouter upstream bridge accepted the session reasoning effort setting without error, but upstream chat completions did not activate an active thinking/reasoning tier for `gemini-3.8-flash`. Requested effort `high` was verified and accepted by the harness, but per review instructions, this is not converted into an unsupported claim of provider deliberation.

---

## 4. Findings by Review Lens

### 4.1 Current Contracts & Contract Proposals (P1, P2)

- **F1.1: Missing model provenance in decision contracts (Severity: Low / Planned)**
  - *File/Line:* `src/leash/contracts/decision.py:31, 55`
  - *Observation:* `FactSource = Literal["agent_form", "structured", "merchant_text"]` and `Check.source: Literal["event", "history", "agent_form", "merchant_text", "state"]` have no enum member for model assessments.
  - *Proposal Assessment:* Proposal P1 correctly plans adding `"model"` to `Check.source` along with model ID and snapshot version in evidence. Proposal P1 also adds `line_no` to `PurchaseFacts` (currently keyed only by `item_id`, `decision.py:34-49`).
  - *Failure Scenario:* Without `"model"`, emitting checks from behavioural or Jev assessments would fail Pydantic model validation with a `ValidationError`.

- **F1.2: Residual fallback in cross-lane contract document (Severity: Medium)**
  - *File/Line:* `docs/contracts.md:177`
  - *Observation:* The contract specifies: `` `facts=None` means the extract lane did not answer in time; every `facts.*` field is then unknown. ``
  - *Proposal Assessment:* This is a legacy fallback specification directly conflicting with AGENTS.md Section 6 ("No fallback code paths"). Proposal P4 correctly demands the removal of line 177 and requiring errors to raise.

- **F1.3: Clean evaluation decoupling in Proposal P2 (Severity: Low / Compliant)**
  - *File/Line:* `docs/plans/02-classifier-m0.md:86-96`, citing `src/leash/engine/evaluate.py:42`
  - *Observation:* Proposal P2 preserves `evaluate()` as a pure function. `assess(...) -> AssessmentBundle` executes externally. `evaluate(..., assessments=None)` treats `None` strictly as a startup-level feature toggle, not a runtime fallback (runtime assessment failures raise before `evaluate` is invoked).

### 4.2 Category-Agnostic Semantic Matching & Exact-Name Inequality

- **F2.1: Observable failure of exact-name comparison on SCEN0004 (Severity: High / Observable Failure)**
  - *File/Line:* `src/leash/extract/facts.py:40-47, 120-130`, `src/leash/runner/loop.py:136-142`
  - *Observation:* In `extract/facts.py:125`, `matches_request = product_type == target`. `_product_type()` merely collapses whitespace and lowercases.
  - *Empirical Execution:* Running `scripts/classifier_m0_exact_name.py "27-inch monitor"` caused all 5 legitimate monitor purchase attempts (AU0035, AU0036, AU0038, AU0042, AU0045) to decline with `item_mismatch` (`matches_request=[('IT0017', False, 'structured')]`). Running with `"27-inch computer monitor"` approved all 5 within policy.
  - *Failure Scenario:* Any discrepancy in wording between user instructions ("27-inch monitor") and catalogue entries ("27-inch computer monitor") causes 100% false declines on valid purchases.

- **F2.2: Semantic matching limits vs deterministic checks (Severity: Medium / Architectural)**
  - *File/Line:* `docs/plans/02-classifier-m0.md:19-23, 66-67`, `docs/idea/viseca-agent-control-layer.md:155`
  - *Observation:* M0 notes that under the main-branch ruling ("no language model reads merchant text... model in step 8 never overrides a deterministic check"), Jev output can only generate a risk signal leading to `step_up` under uncertainty policy `ask`. It cannot turn a deterministic `decline` into an `approve`.
  - *Clarification for Implementation:* M0 states in Section 2 that the fix belongs in the policy lane by having drafts store confirmed catalogue names (Owner Ruling O2). While this works for single-item scenarios, for multi-item baskets (SCEN0001 "household groceries", SCEN0003 "clothing"), the policy lane must use category-level matching (`items.category in [...]`, already supported in `src/leash/engine/rules.py:129-130`) rather than a single `facts.product_type = <catalogue_name>` equality rule.

### 4.3 Engine / Extract / Runner / App Integration & Mutation Races (R1, Proposal P3, O3)

- **F3.1: Complete lock isolation between App and Runner (Severity: High / Race Condition)**
  - *File/Line:* `src/leash/runner/records.py:51-59`, `src/leash/api/mandates.py:86-95`
  - *Observation:* The runner locks `data/locks/<mandate_id>.lock`. The app API locks `<store_root>/../mandate_edits/<mandate_id>.lock`. They operate on two distinct files in different directories.
  - *Failure Scenario:* A customer invoking `POST /mandates/{id}/tighten` or `POST /mandates/{id}/revoke` locks only the app lock, while the runner concurrently processes transactions using the runner lock.

- **F3.2: Critical un-locked window during runner purchase processing (Severity: High / Consistency Defect)**
  - *File/Line:* `src/leash/runner/loop.py:215-245`
  - *Observation:* The runner acquires `mandate_lock` at line 215 only to load state, immediately releases it, performs extraction and evaluation, executes HTTP `submit(decision)` over the network with NO lock held (line 239), and only re-acquires the lock at line 241 to record the decision.
  - *Failure Scenario:* While `loop.py` is waiting on HTTP submission, the customer revokes or tightens the mandate via the app. An approval based on the pre-revocation policy is submitted to the simulator, violating the customer's revocation.

- **F3.3: Runner completely ignores App policy overlay (Severity: High / Functional Disconnect)**
  - *File/Line:* `src/leash/runner/loop.py:213-214`, `src/leash/api/mandates.py:65-84`
  - *Observation:* The runner evaluates against the initial static `--draft` provided on the CLI. It has no import or reference to `MandateEdits` or effective policy overlays. App tightenings have zero effect on runner evaluations.

- **F3.4: Absence of intent journaling (Severity: High / Crash & Timeout Recovery)**
  - *File/Line:* `src/leash/runner/loop.py:239-245`, `src/leash/api/mandates.py:196-200, 212-213`
  - *Observation:* Neither path records intent to disk prior to making remote network calls (`submit`, `/resolve`, `PATCH`, `DELETE`).
  - *Failure Scenario:* If the process crashes or an HTTP request times out after the simulator has processed the mutation, restarting the service leaves local state out of sync with no record that a mutation was in flight.
  - *Proposal Assessment:* Proposal P3 accurately resolves F3.1–F3.4 by unifying the mandate lock under `records.mandate_lock`, holding the lock continuously across recheck, submit, and state recording, persisting intent journals before external calls, and having the runner read the effective policy overlay.

### 4.4 Customer Step-Up Handling (R2, Proposal P4)

- **F4.1: Missing budget and state re-validation upon customer approval (Severity: High / Financial Policy Violation)**
  - *File/Line:* `src/leash/runner/stepups.py:162-181`
  - *Observation:* When a customer answers a step-up with `approve`, `answer()` calls `self._finish()` and sends `/resolve` directly to the simulator without checking if intervening transactions have consumed the remaining budget or exceeded purchase counts.
  - *Failure Scenario:* Mandate has a CHF 100 limit. Step-up A is triggered for CHF 80. While Step-up A is pending customer review, Transaction B for CHF 50 arrives and is approved. The customer then approves Step-up A. `answer()` submits `approve` to `/resolve`, pushing cumulative spend to CHF 130 and exceeding the authorized budget.
  - *Proposal Assessment:* Proposal P4 correctly requires re-evaluating state and budget under the mandate lock before `/resolve`. If limits are exceeded, `/resolve` sends `decline` with the failing reason code.

### 4.5 Cancellation Claims & Simulator Semantics (O3)

- **F5.1: Divergence between simulator frozen snapshots and local overlay enforcement (Severity: Medium / Operational)**
  - *File/Line:* `viseca-2026/technical_details.md:380, 395-397`
  - *Observation:* The simulator documentation specifies: *"Changes affect later runs. An existing run keeps its original snapshot."* and *"Show cancellation only when the platform confirms it."*
  - *Proposal Assessment:* M0 correctly highlights that external simulator mutations do not retroactively modify running simulator runs. Owner Ruling O3 is required to formalize that the local control layer enforces the customer's revocation/tightening immediately by declining subsequent transactions locally, regardless of the simulator's frozen snapshot.

### 4.6 Deadline Behaviour & No-Fallback Compliance (R2, Proposal P4)

- **F6.1: Active fallback paths synthesizing business decisions upon timeout (Severity: High / AGENTS.md Violation)**
  - *File/Line:* `src/leash/runner/loop.py:104-118, 120-134, 170-175, 232-234, 246-247`
  - *Observation:* `_extract_timeout_decision()` synthesizes a `decline (engine_timeout)` Decision when extraction exceeds 1.5s. `_engine_timeout_decision()` synthesizes a `step_up (engine_timeout)` Decision when evaluate times out.
  - *Violation:* AGENTS.md Section 6 explicitly forbids fallbacks: *"No fallback code paths. No try/except that swallows an error and carries on, no default value substituted for a failed call... A missing key, a timeout, a bad response or an unexpected input raises an error with a message that says what failed... A reviewer blocks any fallback it finds."*
  - *Proposal Assessment:* Proposal P4 properly mandates replacing synthetic fallback decisions: budget expiry must raise a named exception, and the simulator must record its own timeout. Bounded time slices allocated from `deadline_at - 250ms - 2s reserve` must be enforced with async transport timeouts.

### 4.7 Model Selection vs Probabilities (R3, Section 8) and Jev Model Pin (Section 9)

- **F7.1: Strict validation of model probabilities vs selected choice (Severity: Low / Compliant)**
  - *File/Line:* `docs/plans/02-classifier-m0.md:154-161`
  - *Observation:* R3 is resolved cleanly: provider `choice` must equal the local argmax of probabilities; any discrepancy raises `JevResponseError` as an execution failure. It never falls back to `approve`.
- **F7.2: Pinned provider and model configuration (Severity: Low / Compliant)**
  - *File/Line:* `docs/plans/02-classifier-m0.md:162-176`, `scripts/classifier_m0_jev_probe.py`
  - *Observation:* Model pin is established as OpenRouter System One `typesafe/jev-1.13-20260917` with `provider: {"only": ["typesafe"], "allow_fallbacks": false}`. Probe evidence confirmed HTTP 200 on this pin versus HTTP 400 on the outdated `jev-1.13.0` identifier.

---

## 5. Commands Actually Run

1. `git rev-parse HEAD` — confirmed `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`.
2. `shasum -a 256 -c /private/tmp/classifier-review-reports/M0/r1/MANIFEST.sha256` — verified 10/10 files OK before and after inspection.
3. `PYTHONPATH=src /Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python scripts/classifier_m0_exact_name.py "27-inch monitor"` — observed 5 declines on valid monitor attempts due to exact string comparison.
4. `PYTHONPATH=src /Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python scripts/classifier_m0_exact_name.py "27-inch computer monitor"` — observed 5 approvals within policy.
5. Python inspection of row counts and column headers for `viseca-2026/data/authorization_history.csv` and `viseca-2026/additional-data-history/authorization_history.csv` — confirmed all table metrics in M0 Section 5 are exact.
6. Connector and harness log inspection (`/tmp/jc-42308d2e4536/home/logs/` and `launch.log`) — verified spawn arguments, process tree, and `set_reasoning_effort` execution.

---

## 6. Limitations

- Per reviewer instructions, review was conducted in a detached grading worktree (`/private/tmp/classifier-m0-r1-gemini`).
- No source files, branches, or shared repository refs were created, staged, modified, committed, or deleted.
- No unit tests, test suites, or linters were written or run.
- `scripts/classifier_m0_jev_probe.py` was inspected but not executed (per brief instructions prohibiting paid calls; provider outcome was inspected from M0 Section 9).
- Simulator API was not called.

---

## 7. Observed Outcome

Proposal M0 (`docs/plans/02-classifier-m0.md`) accurately captures the state of the codebase at commit `d651ef8`, correctly reconciles post-review decisions on `main`, provides rigorous cross-lane interface designs (P1–P5), and identifies key integration flaws that must be addressed across lanes.

Milestone M0 is **APPROVED**.
