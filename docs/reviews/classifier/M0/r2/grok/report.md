# Classifier M0 r2, grok security review

Verdict: APPROVE

Target head: `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`
Target base: `b4c77f2f529d4872a9672bf960f8f687e9c89601` (ancestor of HEAD)
Preceding r1 target: `d651ef85920925d36ece77fc5eaa4d13fff0bd8f`
Correction commit parent: `6d30f986f5c0caa682e6421fef06e63e2a8e4409`
Primary document: `docs/plans/02-classifier-m0.md` SHA-256 `79e0af72e725574389abc7a9ad193722708164d058b75a7a105c302aeb0d53fb`
Approved design: `docs/plans/02-classifier-design.md` SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9` (unchanged from r1)
Probe: `scripts/classifier_m0_jev_probe.py` SHA-256 `a12299f0821b25ef09fe6a49d0750e2c7db7420f8760eb1f4b6836c4464aecc7`
Manifest: `docs/reviews/classifier/M0/r2/MANIFEST.sha256`, all 10 files OK before and after review.
Working tree at both checks: clean, detached HEAD. No source edit, stage, commit, checkout, reset, clean, stash, or worktree removal.

Model pin observed in this seat: `grok-4.7` (`cotal_orientation`: "Model pin: grok-4.7 (from COTAL_MODEL / the agent file)"). Persona `.cotal/agents/classifier_review_grok.md` sets `model: grok-4.7` and `variant: high`.
Requested effort: `high` (persona variant and kickoff brief).
Accepted effort: not observable from inside the seat. No session control reports the applied reasoning tier. This review does not treat the request as proof that the provider ran at high. The tier was not omitted from the brief or the persona.

Lens: authorization, prompt injection, evidence provenance, user isolation, policy/state races, fail-closed handling. Graded the correction from `d651ef8` to `6cd4340` in `docs/plans/02-classifier-m0.md`, `docs/plans/02-classifier-progress.md` and `scripts/classifier_m0_jev_probe.py`. The design file has an empty diff against the r1 target.

## Findings

No blocking finding. The correction does not add a high, security, or correctness blocker.

### Closed from r1

Grok N1 is closed in the script. `scripts/classifier_m0_jev_probe.py:45` now sets `provider: {"only": ["typesafe"], "allow_fallbacks": False}` inside `BODY`. `main` posts `json=BODY | {"model": model}` at line 68, so the model override does not drop the provider object. M0 section 9 (`docs/plans/02-classifier-m0.md:164-176`) now says the earlier calls did not send the restriction and cites one later call that did.

That later call was not repeated here. The retained log `/private/tmp/classifier-m0-r2-jev-probe.log` (342 bytes, SHA-256 `860e60e3378c1e9c67bc470e1ec80511d297322fe3dbadcb563e8988b3b1d70d`) reads:

```
requested=typesafe/jev-1.13-20260917 http=200 latency_ms=478
model typesafe/jev-1.13-20260917, provider TypeSafe, input 379, output 40, cost 1.5918e-05
```

No credential value is in that file. This matches the brief and M0 lines 172-174. It is retained evidence, not a new paid call.

GLM G1 variant 3 is recorded at `docs/plans/02-classifier-m0.md:187`. May selection then a through-May refit stays. July and the reserved 20% of customers stay out of selection, fitting, calibration and threshold choice. Seen-customer July is labeled selection-informed. Reserved-customer July leads the generalization table. The two populations are separate. The same paragraph covers GLM N1 (lead with the deterministic-pass subset), N2 (agent and human calibration and escalation rates separately) and N3 (zero-history outcome metrics unavailable). N4 is unchanged: M1 and M2 keep separate historical and live derivations. N5 is corrected at `docs/plans/02-classifier-progress.md:95`: the 21:28 freeze names a commit and document hash, and the manifest arrived later in `acb5763`.

P1 and P2 no longer say the contract was already agreed at the r1 freeze. `docs/plans/02-classifier-m0.md:78` and `:88` date the boundary confirmation after r1 and say the contract change is unmerged. Line 95 restricts a model check to `pass` or `uncertain`, forbids `fail`, and says it cannot decline alone or overturn a deterministic failure. `None` still means the model configuration is off, not that a call failed. A failure still raises before `evaluate`.

M3 history-only scope holds. O1 at line 209 blocks only an optional line-input extension. Section 13 line 218 says M3 uses the customer's own history until O1 is answered and assumes no catalogue line input.

### N1, non-blocking: several file:line anchors drifted after the base move

The r2 commit does not retarget citations that main moved. The behaviors the security claims depend on are still present.

| M0 citation | Now |
| --- | --- |
| `checks.py:100, 113, 138, 200` (`02-classifier-m0.md:98`) | `merchant_count(auth.card_id, ...)` is still line 100. The other card-scoped calls are `checks.py:117`, `:145` and `:207`. Lines 113 and 138 are the `no_card_history` branch and a blank line. |
| `data.py:78` base-pack approved purchases (`:98`) | Line 78 is the docstring of `known_merchants`. The base-pack load is `HISTORY = History(PACK / "authorization_history.csv")` at `data.py:85`. `PACK` is `viseca-2026/data` at line 13. Approved purchases are still filtered at `data.py:44`. |
| `rules.py:260` maps uncertain `facts.product_type` to `item_mismatch` (`:64`) | Line 260 is blank. `REASON_BY_FIELD` starts at `rules.py:261`. `facts.product_type` is still `item_mismatch` at line 272. `reason_code` at line 285 still returns that code for any non-pass result. |
| `stepups.py:40, 59-60` and `answer()` at `162-181` (`:143-144`) | Expiry margin is `stepups.py:41` and `expires_at` is `:60-61`. `human_window_s` is `:52`. `answer()` is `:206-225`. It still checks `expires_at` at `:215` and sends the customer decision through `_finish` with no budget or state recheck. |
| `docs/contracts.md:177` (`:141`, P4 at `:148`) | That line is a code fence. The `facts=None` timeout sentence is `docs/contracts.md:179`. |
| `api.py:3, 33` "one 30 s timeout" (`:142`) | Line 3 still says 30 s. Line 33 uses `timeout=s.timeout_s`. `settings.py:12` sets `REQUEST_TIMEOUT_S = 30.0` and line 23 uses it as the field default. |

Failure scenario: an implementer opens the printed line and edits the wrong statement, or treats the old `answer()` span as the whole function and misses the expiry check now at line 215. The races themselves are unchanged and still assigned. P3 and P4 remain open cross-lane work for M4 (`02-classifier-m0.md:127-150` and `:219`). Approving M0 does not approve an implementation of either.

Not a blocker because none of these drifts opens a model path, accepts merchant text, or claims the races are fixed. The card and customer split in section 4 and section 5 is still the isolation rule, and current checks still key history with `event.authorization.card_id`.

### Still open, unchanged, not M0 code

N2 from r1: `stepups.py:206-225` can approve after another purchase has spent the period cap. P4 still assigns the recheck to `runner_builder`.

N3 from r1: `loop.py:215-216` holds `records.mandate_lock` only to load state. Extract and evaluate run unlocked (`loop.py:227-239`). `submit()` at line 239 takes no lock. The lock returns at `:241-245` to record. `mandates.py:87-93`, `:180` and `:206` still use `mandate_edits/<mandate_id>.lock`. O3 and P3 still own that window.

## Commands actually run

```
git rev-parse HEAD
git status --porcelain=v1
git rev-parse --abbrev-ref HEAD
git log -1 --format='%H %s'
shasum -a 256 -c docs/reviews/classifier/M0/r2/MANIFEST.sha256
git diff --stat d651ef85920925d36ece77fc5eaa4d13fff0bd8f..6cd4340316c0ebc546a2c0f8ff6b147ef1688db8
git log --oneline d651ef85920925d36ece77fc5eaa4d13fff0bd8f..6cd4340316c0ebc546a2c0f8ff6b147ef1688db8
git merge-base HEAD origin/main
git rev-parse b4c77f2
git show HEAD:.cotal/agents/classifier_review_grok.md
git diff d651ef8 6cd4340 -- docs/plans/02-classifier-m0.md docs/plans/02-classifier-progress.md scripts/classifier_m0_jev_probe.py
git diff --name-only d651ef8 6cd4340 -- docs/plans/02-classifier-design.md docs/plans/02-classifier-handoff.md docs/plans/02-classifier-review.md scripts/classifier_m0_exact_name.py .cotal/agents/
git show --stat --format='%H%n%P%n%s' 6cd4340
git show 6cd4340 -- scripts/classifier_m0_jev_probe.py
git merge-base --is-ancestor b4c77f2f529d4872a9672bf960f8f687e9c89601 HEAD
```

The manifest check was run before reading the correction and again immediately before this report. HEAD stayed `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`. All 10 manifest files stayed OK. The tree stayed clean.

Read-only Python parsed `BODY` and checked the probe log for the claimed status, latency, served model, provider name and token counts, and for credential markers. None were present. No `uv sync`, no test suite, no linter, no simulator call, no rerun of `classifier_m0_jev_probe.py`.

## Limitations

The r2 HTTP 200 row was checked against the retained log only. The paid call was not repeated.

Accepted reasoning effort is not visible in-seat. Orientation shows `grok-4.7` only.

Peer r2 reports were not read. The preserved own r1 report at `docs/reviews/classifier/M0/r1/grok/report.md` and `docs/reviews/classifier/M0/r1/findings.md` were read after the correction diff.

`OPENROUTER_API` and `.env` were not opened.

## Outcome

APPROVE `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`. The probe now sends the TypeSafe-only pin with fallbacks off, and the retained response names that provider and model. The split protocol matches GLM variant 3. Model checks stay pass-or-uncertain and fail closed. M3 stays on the customer's own history until O1. Stale line numbers and the assigned P3/P4 races remain non-blocking.
