# M2 r1 GLM review report

## Verdict

**APPROVE** for exact head `f5d27c80ed3862473852ae2ed3a802190ca13fc5` on `lane/classifier`, base `origin/main` `0b7c2c1d1b4021a835a237e92f8491e33c6d5e25`.

- Report SHA-256 (this file): recorded by manager on receipt.
- Manifest `docs/reviews/classifier/M2/r1/MANIFEST.sha256`: all 19 paths OK before review and re-verified OK after review (23:26:14Z). Working tree clean at both checks; HEAD unchanged. `git status --porcelain` empty.
- Model pin: orientation reports `glm-5.3` (from COTAL_MODEL / agent file; harness default not knowable from the seat). No upstream effort tier is observable from this seat; the requested effort per the brief is max and this review ran at full depth: independent refit of both candidates, independent calibrator fit, full row recount, artifact reload and scoring, 45-attempt scoring, and static isolation analysis, all inside the 12-minute window.

## Scope confirmed

M2 offline comparison only. No P1/P2 engine integration, no live runner claim, no operational threshold. `grep` over `src/leash` and `scripts` shows no import of `BehaviorModel` or `escalation_fired` outside `src/leash/engine/classifier/`; `src/leash/engine/evaluate.py` imports nothing from the classifier lane.

## What I verified and how

Independent reproduction commands (all outputs written outside the checkout, under `/private/tmp/classifier-review-reports/M2/r1/glm/`; the classifier worktree venv `.venv/bin/python` with `PYTHONPATH=src` was used as permitted):

1. **Target integrity.** `git rev-parse HEAD` = `f5d27c8...` before and after; `shasum -a 256 -c docs/reviews/classifier/M2/r1/MANIFEST.sha256` passed 19/19 twice; `git status --porcelain` empty.
2. **Row counts and split membership.** Recounted all additional-pack purchases through `HistoryIndex.historical_purchases("additional")`: 140,096 rows; every (window, population) count matches `split-manifest.json` exactly (fit 80,771/20,483, select 10,480/2,757, calibrate 5,077/1,284, threshold 5,056/1,247, evaluate 10,345/2,596 seen/reserved). Base pack: 20 customers, zero overlap with fitting/reserved sets. First purchase of reserved CU1007 (TR100250) has 0 prior approvals and 0 prior attempts at both scopes, confirming strict pre-event cutoffs.
3. **May selection reproduced.** Refit LR and CatBoost on the fit window and scored May: LR PR-AUC 0.4722, CatBoost 0.5042 (ROC 0.7859/0.7844, Brier 0.0389/0.0363). Matches the report to four decimals; CatBoost selected by the fixed rule at `scripts/classifier_fit.py:277-278`.
4. **Refit, calibrator, July metrics reproduced.** Refit prevalence 0.0596; calibrator coefficients reproduced to full float precision (coef 1.18791695, intercept 0.16687105, identical to the persisted artifact). Reserved July issuer-pass: 2,551 rows, 91 declines, Brier 0.0347 vs constant 0.0350. Reserved all: 2,596/134, Brier 0.0354 vs 0.0490. Reserved agent 0.0-0.1 band: 411 rows, 20 declines, mean 0.0285 vs observed 0.0487. All match `docs/eval/classifier/m2-report.md` lines 25-29, 47-49.
5. **Artifact integrity.** `joblib.load` of `docs/eval/classifier/model-evaluation-only.joblib` (SHA-256 `e4815c56...` per manifest and file) succeeds; keys are exactly `calibrator, feature_names, feature_schema_version, model, selected_candidate`; pipeline is median SimpleImputer (`keep_empty_features=True`) then CatBoostClassifier(iterations=300, depth=5, lr=0.05, l2_leaf_reg=3.0, seed 20260924), matching `model-manifest.json` candidate_configurations. Calibrator is monotone (positive coefficient), endpoints sane (raw 0.001 -> 0.00032, raw 0.999 -> 0.99977).
6. **Escalation cannot fire without O4.** `behaviour.py:99` hardcodes `escalation_fired=False` in `score()`. The constructor rejects any manifest whose `artifact_release_status` differs from `evaluation_only_no_operational_threshold` or whose `threshold_status` differs from `proposals_only_owner_O4_pending` (`behaviour.py:36-39`). Artifact hash, split-manifest hash, library versions, feature names and candidate are all cross-checked at load with loud `ValueError`s. No score default or substitute model exists anywhere in the lane.
7. **Live-path scoring claims reproduced.** AU0035 scored through `HistoryIndex.for_event` + `BehaviorModel.score` with the real SCEN0004 policy draft: 0.097382, `escalation_fired=False` - exactly the report's claim (m2-report.md:70). All 45 public attempts scored (SCEN0002 via its evaluation policy, others via `docs/eval/replay-policies/`): min 0.0300, median 0.0499, max 0.2364, zero escalations - exactly m2-report.md:70. A `hist-0` schema is rejected with `purchase feature schema differs from model`. A base-pack customer row (CU0009/TR00001) scores 0.054185, confirming base history is available for profiles without entering fitting.
8. **Numeric predictor isolation.** Only the 50 numeric `HistoryFeatures.values` keys enter the estimators (`classifier_fit.py:117-118`, `behaviour.py:77-80`); IDs and persona fields are grouping metadata only. No identifier appears in `feature_names`.
9. **No runtime fallback / optional deps.** No module outside the classifier lane imports numpy, scikit-learn or catboost (grep across `src/`, `scripts/`). `pyproject.toml` keeps them in the optional `classifier` group, so a model-enabled runtime without the group fails at import rather than substituting anything.

## Lens findings (none blocking)

1. **Historical target meaning (reported honestly).** The target is historical `status == declined` propensity. On the reserved July issuer-rule-pass proxy, PR-AUC 0.0672 against a 3.6% prevalence is weak ranking (ROC-AUC 0.6593), and the report does not editorialize about that weakness; it prints the numbers, says the proxy "is not a complete mandate-rule evaluation" (m2-report.md:22) and draws no live claim. Acceptable for an evaluation-only milestone; M4's owner should not read issuer-pass PR-AUC as mandate-decision skill.
2. **Agent calibration underprediction disclosed.** Reserved agent 0.0-0.1 band underpredicts (0.0285 vs 0.0487) and the report says so (m2-report.md:51). Bands with fewer than 30 rows or five outcomes per class are marked insufficient in `model-manifest.json`; no calibration claim is made for sparse bands. Failure scenario if ignored at O4: an agent-rate threshold set from June scores would escalate roughly 1.7x more agent purchases than the requested rate on a July-like population. The June/July drift table in the manifest makes this visible.
3. **Threshold proposals are correctly gated.** Cuts come from seen customers June 16-30 only (`classifier_fit.py:297-298`), the calibrator is not refit on that window, July rates at unchanged cuts are reported without selecting anything, and no numeric threshold exists in code or artifact. July drift (requested 0.10 -> reserved actual 0.1113, agent 0.1545) is in `july_rates_at_june_proposals`.
4. **Cold starts and small slices.** July has zero zero-prior-approved rows and zero low-support rows in both populations, so no July claim is made for them (m2-report.md:42). The 45 public attempts all scored without error, so supported missingness works live. The report's separate paragraph on public-attempt feature availability (merchant recency missing 17.8% vs 2.5% in July agent rows) is an honest parity caveat I could not re-derive in the window but which matches the manager's progress log entry at 01:14-01:15; it suppresses any live-calibration claim for that mix.
5. **Card vs user vs mandate scope.** Features are card-scope and customer-scope only; no mandate-derived feature is a predictor, matching design section 4. `for_event` rejects mandate/card/customer identity disagreement loudly.
6. **Minor: report prose exceeds the generator.** The frozen `m2-report.md` contains verification paragraphs (artifact reload, 45-attempt scoring, uv-sync isolation, initial-run byte-drift note) that `scripts/classifier_fit.py` does not emit, and the script refuses to rerun while outputs exist. Every quantitative claim in those paragraphs was independently reproduced by this review (items 5-7 above, uv.lock hash `024e138f...`, library versions numpy 2.5.3 / scikit-learn 1.9.1 / catboost 1.2.10 matching the manifest), so the content is verified even though a one-shot rerun of the script would produce a shorter report. A future round could have the script emit or re-verify those paragraphs.
7. **Minor: initial-run byte drift disclosed, not resolved.** The report discloses that the first fit produced a different artifact hash with identical probabilities on 1,000 rows and identical calibrator coefficients, preserved outside the tree. My independent refit reproduced the final calibrator coefficients exactly, supporting determinism of the fitted parameters. Unresolved pickle byte-level drift is acceptable for an evaluation-only artifact pinned by hash; it must be understood before any M4 operational artifact is minted.

## Failure scenarios considered and rejected

- Reserved-customer leakage into fitting/calibration/thresholds: all fitting masks intersect `population == "seen"` (`classifier_fit.py:256-262`); split sets are disjoint and asserted; base-pack overlap is zero (recounted).
- Temporal leakage: features use `bisect_left` on sorted `(timestamp, authorization_id)` keys, strictly pre-event; windows are half-open UTC and every purchase day must match exactly one window or the run raises.
- Escalation firing from the artifact: hardcoded false, manifest statuses pinned, no consumer in engine/runner, threshold absent from artifact and code.
- Silent fallback on missing/broken artifact: load raises on any mismatch (schema, hash, versions, names); no default score path exists.
- Scenario/authorization-ID keying: none present; predictors are the 50 frozen numeric keys.

## Commands actually run

From `/private/tmp/classifier-m2-r1-glm` with `/Users/david/Projects/Bucheggang/.worktrees/classifier/.venv/bin/python`, `PYTHONPATH=src`, scripts stored and outputs written under `/private/tmp/classifier-review-reports/M2/r1/glm/`:

- `git rev-parse HEAD`, `git status --porcelain`, `git log --oneline -5`, `shasum -a 256 -c docs/reviews/classifier/M2/r1/MANIFEST.sha256` (twice, before and after).
- `verify_counts.py`: full recount of 140,096 rows, window/population cross-tab, base-pack overlap, CU1007 cold-start check.
- `verify_refit.py`: independent LR and CatBoost fit on the fit window, May metrics.
- `verify_brier.py`: independent refit+calibrator fit, July reserved/seen metrics, agent band reproduction.
- `verify_artifact.py`, `verify_may.py`, `verify_cal.py`: artifact load, pipeline inspection, calibrator monotonicity.
- `verify_au0035.py`, `verify_45.py`: AU0035 score via `for_event` with the real SCEN0004 draft; all 45 public attempts scored.
- Greps for classifier imports outside the lane, numpy/sklearn/catboost imports outside the lane, `except`/fallback patterns.
- Reads: `m2-report.md`, `split-manifest.json`, `model-manifest.json`, `classifier_fit.py`, `history.py`, `behaviour.py`, `types.py`, design sections 4-5, M0 G1 disposition, progress log, `pyproject.toml`, `classifier_split.py`, `classifier_replay.py`.

## Limits

- I did not rerun `uv sync` in either direction (it would write a `.venv` inside the grading tree); the optional-group isolation claim was verified statically via the import graph and the unchanged `uv.lock` hash, and the library versions were confirmed inside the worktree venv.
- I did not refit the full 300-iteration CatBoost on the refit window and dump a fresh joblib to compare serialized bytes; I reproduced the calibrator coefficients and all reported metrics to full precision instead, which covers the numbers in the report.
- The public-attempt feature-availability statistics (8/45 merchant-recency missing, 63/2,477) were not recomputed; the 45-attempt scoring run confirms all attempts produce complete 50-key features without error.
- The initial preserved run at `/private/tmp/classifier-m2-initial-20260925/` was not reloaded; its description matches the manager log.

## Observed outcome

Head `f5d27c8` clean and manifest-intact before and after review. Every quantitative claim in `m2-report.md` and `model-manifest.json` that I set out to reproduce matched exactly, including both candidates' May metrics, the selected candidate, calibrator coefficients, all reserved/seen July headline metrics, the agent-band calibration numbers, AU0035's score, and the 45-attempt min/median/max with zero escalations. Escalation is structurally impossible without owner O4. No fallback path, no ID predictor, no leakage into selection, fitting, calibration or thresholds was found. Verdict: APPROVE.
