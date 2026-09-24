# Classifier M0 review, round r2 (correction round), reviewer GLM

- Verdict: **APPROVE** the r2 target `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`, base `b4c77f2` (merged into the lane as `3d52fc5`), preceding r1 target `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`.
- M0 document `docs/plans/02-classifier-m0.md`, SHA-256 `79e0af72e725574389abc7a9ad193722708164d058b75a7a105c302aeb0d53fb`, matching `docs/reviews/classifier/M0/r2/MANIFEST.sha256`. HEAD, clean tree and the full ten-file manifest verified identical before and after review. A changed target voids this verdict.
- Frozen design `docs/plans/02-classifier-design.md` unchanged at `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`; `02-classifier-handoff.md` and `02-classifier-review.md` also unchanged (verified in the r1→r2 diff and by hash). "Keep the original reviewed design untouched" holds.
- Reviewer seat `classifier_review_glm_r2fresh`, harness jcode. Model pin from `cotal_orientation`: `glm-5.3`. Requested effort: `max` (persona `variant: max`); the max-tier pass was performed in full, not silently omitted. Accepted tier is not observable from inside the seat; the harness surfaced no rejection.
- Scope: the correction diff `d651ef8..6cd4340` against the r1 findings, with every corrected M0 claim re-verified at the new head, including citations the base merge (`origin/main` `b4c77f2`, PRs #30-#33 plus engine/runner work) could have shifted. No code approval beyond the documentation and one probe-script line this round actually changes; no merge authorization; no model-performance validation.

## Verified corrections (all r1 dispositions)

1. **G1, variant 3 recorded exactly** (`02-classifier-m0.md:187`). Selection stays on May, refit through May, seen-customer July labeled selection-informed, reserved-customer July leads the generalization table, split manifest records protocol, fixed seed and customer membership before fitting, July cannot change candidate or operating point. This is the correction I set out in r1, with the reserved 20% and July untouched. The paragraph also folds in N1 (deterministic-passes subset leads), N2 (agent and human calibration and escalation separated) and N3 (zero-history slice handling). The N3 sentence is over-broad; see finding F1.
2. **P1/P2 ownership corrected** (`:78`, `:88`, `:197-198`). No unverified "agreed with engine_builder" claim remains. P1 defers `line_no` until O1 allows line inputs. P2 records the conditional `assessments: AssessmentBundle | None = None` interface, the pass-or-uncertain model check ("never `fail`; cannot decline alone or overturn a deterministic failure"), the `AssessmentBundle` move into `src/leash/contracts/` as a separate engine-reviewed PR, and integration held on main until after the 12:00 freeze. The engine owner's agreement is recorded in the progress ledger (23:3x Log line, commit `658a059`). Verified in git: no classifier commit in the window touched `src/leash/engine/**` (existing files) or `src/leash/contracts/**`; the only engine-file changes arrived through merged main (`f5c1fb3`, `9ef68ba`).
3. **M3 history-only scope** (`:209`, `:218`). O1 now blocks only the optional line-input extension; history-only M3 proceeds, the provider adapter and standalone assessment run without P1, and no catalogue line input is assumed. Consistent with the frozen design and with main's rulings quoted in M0 section 1.
4. **Probe provider restriction fixed** (`scripts/classifier_m0_jev_probe.py:45`). One line: `provider: {"only": ["typesafe"], "allow_fallbacks": false}`. The r2 paid call (manager-run, not repeated by me) is recorded at M0 `:172` and its log at `/private/tmp/classifier-m0-r2-jev-probe.log` verified: exists, names `typesafe/jev-1.13-20260917` and provider TypeSafe, and contains no credential value (zero matches for key, token or header patterns). M0 section 9 now separates the unpinned r1 calls (served-model evidence only) from the pinned r2 call.
5. **N5 ledger chronology fixed** (`02-classifier-progress.md:52` and the 21:28 Log line). The manifest's actual provenance (added later in `acb5763`) is now stated. Preserved r1 reports all match their ledger hashes (`f10f1a62...`, `61ca79a6...`, `18cb257d...`).
6. **Citations re-verified at the new head.** `decision.py:31,34,55`, `evaluate.py:28-33,42`, `loop.py:43-44,104,120,136-142,170-175,215-216,232-247`, `records.py:51-59`, `api.py:3,33`, `mandates.py:64-93,177-212`, `docs/contracts.md:177`, `facts.py:125-133` all still exact. `rules.py:260` (`REASON_BY_FIELD`) and the `stepups.py` family drifted by one line (`41/52/60-61`, `answer()` now at `206-225`); substance verified unchanged, including that `answer()` still resolves an approve without the budget/state recheck M0 P4 correctly leaves open with runner_builder.

## Remaining findings

### F1: zero-history sentence over-broad, low, one-sentence correction

`02-classifier-m0.md:187`: "The zero-history slice has no examples in either supplied pack, so its outcome metrics are unavailable."

Independently computed from the packs (stdlib, read-only): the additional pack has 542 customer-scope purchases with no earlier approved purchase (482 with no earlier purchase row at all; 902 card-scope), and the base pack 23 (46 card-scope). All fall in 2025-09-01..2025-09-09; June and July contain zero. The July-unavailability conclusion stands, and the error direction is conservative, so this cannot inflate any performance claim. The correction matters for M2 honesty in the other direction: those September rows sit inside the April-or-earlier fitting window, so the missingness-encoding path (design `:90`, `:110`) has real training support, and the M2 report should say the zero-history slice is train-time-supported but evaluation-empty rather than absent from the packs. My r1 N3 said "structurally empty offline"; the manager's narrower reading is the correct one and I adopt it. Owner: classifier lane, one sentence at the next M0 touch or in the M2 split manifest.

### F2: stale base line and minor citation drift, editorial

M0 `:5` still names the r1 base (`origin/main` `ed2bc3c`); the r2 target's base is `b4c77f2`. The drifted line numbers above belong to the same stale-anchor class. No substantive claim is affected; every one was re-verified at `6cd4340`. Owner: classifier manager, next M0 touch.

### F3: lane-local type scaffolding landed during the review window, note

`src/leash/engine/classifier/types.py` (commit `2c7f168`) defines the design section 9 types inside the lane-owned new package, with `escalation_fired=False` until O4, matching the frozen design. It touches no engine-owned file and does not affect the M0 document. The ledger's gate note ("no dependent milestone source work begins until the M0 panel clears") reads this as non-dependent scaffolding; if the manager wants a stricter reading, one ledger line saying so closes it. Not a defect in the target. Half-line for the future P2 PR: `BehaviorAssessment.score` says "[0, 1]" only in a comment; take the bound into the contract validation when the type moves.

## No new blocker

The corrections are documentation plus one probe line. Classifier commits in the window touched only classifier-owned paths. The design stayed frozen. The G1 disposition is the accepted variant, recorded in the document that governs M2. Nothing introduced by the r2 diff creates a high, security or correctness blocker.

## Commands actually run

All read-only; no source edit, stage, commit, push, checkout, reset, clean, stash or worktree change; no provider or simulator call; no `uv sync`; no tests or linter.

- `git rev-parse HEAD`; `git status --porcelain`; `shasum -a 256 -c docs/reviews/classifier/M0/r2/MANIFEST.sha256` before and after review.
- `git diff --stat` and full diff `d651ef8..6cd4340` over the M0 doc, probe script, design/handoff/review plans, progress ledger, `pyproject.toml`; `git log` attribution for every engine/contract file touched in the window; `git show` of the classifier commits `8711109`, `658a059`, `8bdc87c`, `6d30f98`, `6cd4340`.
- Full read of `02-classifier-m0.md` at the target; `grep`/`sed`/`awk` reads re-pinning every cited line in `decision.py`, `evaluate.py`, `rules.py`, `data.py`, `checks.py`, `loop.py`, `records.py`, `api.py`, `stepups.py`, `mandates.py`, `docs/contracts.md`.
- `python3` stdlib (no repository imports): zero-history purchase decomposition over both packs, customer and card scope, with month attribution; this is the independent verification behind F1.
- Reads of `src/leash/engine/classifier/types.py`, the corrected probe script, and `/private/tmp/classifier-m0-r2-jev-probe.log` (credential-pattern scan included).
- `shasum -a 256` of the three preserved r1 reports against the ledger hashes.

## Limitations

- Single reviewer, one lens; authorization, injection and integration coverage belong to the other seats.
- The r2 probe call is the manager's recorded observation; I verified its log and script but did not repeat the paid call, per the brief.
- Accepted effort tier remains unobservable in-seat (see header).
- The provisional split profile in the ledger (seed 20260924, counts by window) was recorded as unfitted and unpersisted; I checked its consistency with the G1 disposition but did not re-derive the counts, since no split membership has been used.

## Observed outcome

APPROVE. Every r1 disposition is correctly implemented in the frozen r2 target: G1 by the accepted variant 3, P1/P2 ownership by the recorded engine agreement, M3 by history-only scoping, the probe by the provider restriction with one pinned call, N5 by the ledger chronology fix. The design is untouched at its approved hash. One low factual correction (F1, zero-history wording, conservative direction, owner named) and two editorial notes remain; none blocks M1 or M2. A changed target hash voids this verdict.
