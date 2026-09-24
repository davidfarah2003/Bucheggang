# Classifier M0 Review Report (Round r2)

- **Reviewer:** `classifier_review_gemini` (role: `default`)
- **Lens:** Current contracts, category-agnostic semantic matching, engine/extract/runner/app integration, customer step-up, cancellation claims, and deadline behaviour.
- **Date:** 2026-09-24
- **Working Tree:** `/private/tmp/classifier-m0-r2-gemini` (detached grading worktree)
- **External Report Path:** `/private/tmp/classifier-review-reports/M0/r2/gemini/report.md`

---

## 1. Verdict

**APPROVE** M0 correction round r2.

The correction diff from `d651ef85920925d36ece77fc5eaa4d13fff0bd8f` to `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8` faithfully incorporates all consensus findings from round r1 without modifying the core reviewed architecture:
1. **GLM G1 (Variant 3):** Fully adopted. Candidate selection is locked on May with through-May refit. July data and the 20% reserved customer set remain untouched by selection, fitting, calibration, and threshold choice. Reserved-customer July metrics lead as the primary generalization estimate, seen-customer July metrics are labeled selection-informed and reported separately, and zero-history outcomes are properly documented as unavailable.
2. **Grok N1:** The OpenRouter System One probe (`scripts/classifier_m0_jev_probe.py`) was corrected to enforce `provider: {"only": ["typesafe"], "allow_fallbacks": false}`. The manager verified this with a live HTTP 200 call returning served model `typesafe/jev-1.13-20260917` from provider `TypeSafe` in 478 ms (logged at `/private/tmp/classifier-m0-r2-jev-probe.log`).
3. **P1/P2 Ownership & Contract Boundary:** Ownership lines were cleanly re-anchored. Contract changes to `src/leash/contracts/` and `evaluate()` remain engine-owned and will be drafted as a separate PR by the classifier lane under engine owner review. The model check contract is explicitly bounded to return `pass` or `uncertain` (never `fail`), precluding any model check from declining alone or overturning a deterministic failure.
4. **M3 Scope:** History-only scope is decoupled from catalogue line inputs (O1), allowing M3 to proceed independently while preserving deterministic extraction boundaries.
5. **No Regressions or Fallbacks:** The additions of `src/leash/engine/classifier/types.py` and `.cotal/agents/classifier_builder.md`, along with merging `origin/main` (incorporating app UI improvements), introduce no fallbacks or synthetic failure responses.

---

## 2. Target Identification & Hash Verification

- **Target Commit:** `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8` (on `lane/classifier`)
- **Base Commit:** `origin/main` at `b4c77f28ba2432eb8d0b2713f019fa107f9185a0`
- **Preceding r1 Target:** `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`
- **Primary Document:** `docs/plans/02-classifier-m0.md` (SHA-256: `79e0af72e725574389abc7a9ad193722708164d058b75a7a105c302aeb0d53fb`)
- **Manifest Verification:** Verified with `shasum -a 256 -c docs/reviews/classifier/M0/r2/MANIFEST.sha256` before and after inspection. All 10 manifest files matched their exact SHA-256 hashes without modification.
- **Working Tree State:** Clean; detached HEAD at `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`.

---

## 3. Actual Model Pin & Effort Verification

- **Persona Specification:** `.cotal/agents/classifier_review_gemini.md` specifies `agent: jcode`, `model: gemini-3.8-flash`, `variant: high`.
- **Spawn Invocation:** Spawned via `cotal spawn ... --model gemini-3.8-flash --variant high` (PID 41200 / node connector).
- **Connector & Route Translation:** Logged in `/private/tmp/classifier-review-reports/M0/r2/gemini/launch-retry.log`: `model gemini-3.8-flash is served by provider cliproxy via openai-compatible:cliproxy`.
- **Observed Upstream Behaviour:** In the Jcode session log (`/private/tmp/jc-42308d2e4536/home/logs/jcode-2026-09-24.log`), `PROVIDER_CANONICAL_INPUT` logged:
  `provider=openai-compatible model=gemini-3.8-flash format=chat_completions thinking_enabled=None provider_features=false`
  As noted in `docs/models.md:26` (`"gemini-3.8-flash (no effort tier; jcode refuses one for Gemini)"`), the cliproxy/OpenRouter upstream bridge accepted the `high` variant request without error, but upstream chat completions does not expose or activate a thinking/reasoning tier for `gemini-3.8-flash`. Requested effort `high` was verified and accepted by the harness, but per review instructions, this is not converted into an unsupported claim of provider deliberation.

---

## 4. Verification of Round r2 Corrections

### 4.1 GLM G1 Resolution (Split Protocol & Generalization Guarantees)
- *Document Reference:* `docs/plans/02-classifier-m0.md:187-191`
- *Observation:* Section 10 explicitly documents GLM G1 Variant 3. May candidate selection is followed by refitting through May. July rows and the reserved 20% customer population are completely isolated from selection, fitting, calibration, and threshold tuning.
- *Reporting Guarantees:* Reserved-customer July metrics will lead as the primary generalization estimate. Seen-customer July metrics will be reported separately and labeled selection-informed. Slices with zero support (e.g. zero-history cold start) will be explicitly reported as unavailable rather than masked.

### 4.2 Grok N1 Resolution (Provider Restriction & Live Pin Evidence)
- *File/Line:* `scripts/classifier_m0_jev_probe.py:45`, `docs/plans/02-classifier-m0.md:164-177`
- *Observation:* `scripts/classifier_m0_jev_probe.py` now includes `"provider": {"only": ["typesafe"], "allow_fallbacks": False}` in the request body.
- *Evidence:* The manager executed one live paid probe on this configuration. Output at `/private/tmp/classifier-m0-r2-jev-probe.log` confirms:
  - HTTP status: 200
  - Latency: 478 ms
  - Model served: `typesafe/jev-1.13-20260917`
  - Provider: `TypeSafe`
  - Cost: 1.5918e-05 (379 input tokens, 40 output tokens)
- *Finding:* The probe verified that the TypeSafe pin and disabled fallbacks function as intended on OpenRouter System One without leaking credentials.

### 4.3 P1 & P2 Ownership, Contract Boundaries, and Model Check Semantics
- *Document Reference:* `docs/plans/02-classifier-m0.md:78-83, 88-100, 197-200`
- *Observation:*
  - P1 clarifies that contract edits to `src/leash/contracts/` (`Check.source: "model"` and `AssessmentBundle`) remain engine-owned. The classifier lane will draft these in a dedicated PR for the engine owner to review and merge.
  - P2 bounds the model check strictly: a model check returns `pass` or `uncertain`, never `fail`. It cannot decline a purchase alone and cannot overturn a deterministic failure.
  - `evaluate()` gains optional `assessments: AssessmentBundle | None = None`. `None` is strictly a startup feature flag, never an error fallback.
  - Adding `line_no` to `PurchaseFacts` is deferred until owner ruling O1 permits line-item inputs.

### 4.4 M3 History-Only Scope & Decoupling from O1
- *Document Reference:* `docs/plans/02-classifier-m0.md:209, 219-220`
- *Observation:* Owner ruling O1 (whether Jev may read catalogue `item_name` and `item_category`) is now scoped as an optional extension only. M3 proceeds with customer history only and does not assume catalogue line inputs, preserving deterministic boundaries.

### 4.5 Lane Types & Builder Infrastructure
- *File/Line:* `src/leash/engine/classifier/types.py:1-69`, `.cotal/agents/classifier_builder.md`
- *Observation:* Added clean, strongly typed Pydantic models for `HistoryFeatures`, `BehaviorAssessment`, `JevAnswer`, `SemanticAssessment`, and `AssessmentBundle`. They are strictly internal to the lane until P1/P2 integrate them into `contracts`. The builder persona enforces no fallbacks, no tests, and strict boundary discipline.

---

## 5. Review Lenses & Remaining Cross-Lane Trackers

The underlying architectural defects in upstream components identified during r1 remain correctly catalogued in M0 as cross-lane release blockers:
1. **Current Contracts & Fallback Removal (F1.2):** Removal of `facts=None` fallback in `docs/contracts.md:177` is tracked under P4.
2. **Category-Agnostic Semantic Matching vs Exact-Name Comparison (F2.1, F2.2):** SCEN0004 exact-name mismatch is properly assigned to policy/extraction lanes (B1, O2). The classifier does not attempt to override deterministic extraction.
3. **App & Runner Lock Isolation / Overlay Sync (F3.1–F3.4):** Unified lock `records.mandate_lock`, intent journaling, and runner overlay application are tracked as P3/P4 release gates for M4.
4. **Customer Step-Up Re-Check (F4.1):** Pre-`/resolve` state and budget re-evaluation under lock is tracked under P4.
5. **Cancellation & Revocation Semantics (F5.1):** Local enforcement across runs is assigned to owner ruling O3.
6. **Deadline Behaviour & Synthetic Fallback Removal (F6.1):** Removal of `_extract_timeout_decision` and `_engine_timeout_decision` in `loop.py` is tracked under P4.

None of these trackers block M0 approval, as M0 is the scoping, contract proposal, and ownership milestone designed specifically to surface and allocate these requirements.

---

## 6. Commands Actually Run

1. `git -C /private/tmp/classifier-m0-r2-gemini rev-parse HEAD` — confirmed `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`.
2. `shasum -a 256 -c docs/reviews/classifier/M0/r2/MANIFEST.sha256` — verified 10/10 files OK before and after inspection.
3. `git -C /private/tmp/classifier-m0-r2-gemini log -p d651ef8..6cd4340` and `diff` — inspected complete changeset between r1 and r2 targets.
4. `cat /private/tmp/classifier-m0-r2-jev-probe.log` — verified live provider restriction probe outcome (HTTP 200, 478 ms, served model `typesafe/jev-1.13-20260917`, provider `TypeSafe`).
5. Process and log inspection (`launch-retry.log`, `/private/tmp/jc-42308d2e4536/home/logs/jcode-2026-09-24.log`, `ps aux | grep jcode`) — verified spawn configuration, process identity, model pin, and harness effort handling.
6. `git -C /private/tmp/classifier-m0-r2-gemini status` — confirmed detached grading worktree is completely clean.

---

## 7. Limitations

- Review was performed strictly within detached grading worktree `/private/tmp/classifier-m0-r2-gemini`.
- No source files, branches, or shared repository refs were created, staged, modified, committed, or deleted.
- No unit tests, test suites, or linters were written or run.
- `scripts/classifier_m0_jev_probe.py` was inspected but not executed (prohibited per brief to prevent redundant paid calls; verified via retained evidence log).
- Simulator API was not called.

---

## 8. Observed Outcome

The M0 correction round r2 (`6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`) successfully addresses all findings from round r1 (GLM G1 Variant 3, Grok N1 provider pin, P1/P2 ownership clarifications, and pass/uncertain model check semantics) while maintaining full architectural fidelity and introducing no fallbacks.

Milestone M0 round r2 is **APPROVED**.
