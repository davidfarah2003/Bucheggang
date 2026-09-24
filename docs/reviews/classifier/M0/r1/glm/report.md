# Classifier M0 review, round r1, reviewer GLM

- Verdict: **BLOCK** (one blocker, G1; corrections are one paragraph in the M0 file).
- Target: commit `d651ef85920925d36ece77fc5eaa4d13fff0bd8f` (parent `635398266160cbf690ae6dcc2c05db1f96698634`), detached, working tree clean, identical to `origin/lane/classifier`.
- Milestone document `docs/plans/02-classifier-m0.md`, SHA-256 `acbad9174f6532d5a1e9283261c2ea7087c99dd8cd582d18ddfbd6dc8359e323`. Verified identical before and after review.
- Incorporated design `docs/plans/02-classifier-design.md`, SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`, unchanged from its approved hash.
- Reviewer seat `classifier_review_glm`, harness jcode. Model pin recorded by `cotal_orientation`: `glm-5.3` (from COTAL_MODEL / the agent file). Requested effort: `max` (persona `variant: max`). Accepted effort is not observable from inside the session; the harness surfaced no rejection and the tier was not omitted by the reviewer. Runtime provider route observed in the environment: `JCODE_ACTIVE_PROVIDER=openrouter` via cliproxy. The manager should confirm harness-side that the max tier was honored; this report does not claim it as an observed provider behaviour.
- Scope: M0 re-anchor document plus every factual claim it makes against main, the two data packs and the design it incorporates. No code approval, no merge authorization, no model-performance validation.

## Blocking finding

### G1: candidate-selection leakage into the final refit, high

`docs/plans/02-classifier-design.md:101-103`, incorporated unchanged into M2 by `docs/plans/02-classifier-m0.md:111` and `:179` ("M2 is offline and needs only P5", per design section 5).

The protocol selects the candidate configuration on May outcomes of the 400 fitting customers ("fit through April and select the candidate on May"), then refits the selected configuration "through May" on those same customers. The final artifact's parameters are therefore fitted on the same customer-month outcomes that chose it. The split manifest, the June 1-15 calibrator window, the June 16-30 threshold window and the July evaluation are all temporally clean, and the 100 reserved customers never contribute to fitting or selection. The contamination is confined to selection-into-artifact: customer-level autocorrelation (persona-driven decline propensity, habitual merchants and devices) makes May outcomes informative about the same customers' July behaviour beyond an iid sample, so the seen-customer July metrics for the chosen artifact are optimistically biased as an estimate of post-selection performance. The design's own standard elsewhere is strict (`:104-106`: reserved outcomes cannot fit parameters or thresholds; target-derived statistics fitted only within the training partition).

Failure scenario. CatBoost wins on May by a margin inside persona autocorrelation noise. The winner is refit through May on the same 400 customers. The M2 report and the Friday pitch quote seen-customer July PR-AUC, Brier and escalation-rate calibration as if they were an unbiased estimate. A later refit with May excluded from the final fit produces lower seen-customer July numbers. The reserved-customer figures were clean all along, so the avoidable part of the claim is exactly the headline seen-customer number.

Required correction, one of:

1. Refit the selected configuration through April only (data strictly earlier than the selection month), or
2. Select the candidate on a customer-disjoint subsample of the 400 and refit through May on the remainder, or
3. Keep the protocol and label the seen-customer July metrics in the M2 report as selection-informed, with the reserved-customer metrics as the only unbiased headline.

Record the choice in the M0 file (it is the document that freezes what M2 executes) and in the split manifest. Non-negotiable in every variant: the reserved 20% and the July evaluation stay untouched, and the report keeps seen-customer and reserved-customer results separate as `:103` already requires.

## Non-blocking findings

### N1: deterministic subset dominates the label; keep it a first-class reporting axis

Measured from the pack with stdlib python3 (read-only): of 140,096 purchase rows and 8,154 declines in the additional pack, 3,402 rows trip at least one deterministic rule reproducible from pack columns (international-disabled card 2,955, non-active `card_status` 265, per-transaction limit 175, calendar-month limit at decision time 80, with overlaps), and 3,307 of those are declined. At least 42% of declines are rule-explained; the organiser's own README (`viseca-2026/additional-data-history/README.md`, "How learnable is `status`?") reports AUC 0.65 / AP 0.08 outside hard rules. Design `:108` already requires separate reporting for the deterministic subset, and M0 keeps the score evaluation-only until O4. This is the design being honest, and M2 must not silently drop it: the headline M2 table should lead with the passes-deterministic-checks subset, not the overall AUC. Owner: classifier lane at M2.

### N2: agent and human parity is a calibration issue, not only an AUC issue

Agent rows: 19,037 purchases, 1,341 declines (7.0%). Human rows: 121,059 purchases, 6,813 declines (5.6%). Decline base rates differ by initiator, and the deployed use case scores agent purchases. Design `:108` requires separating human- and agent-initiated purchases. Add explicitly: calibration curves and threshold behaviour (escalation rate at the chosen score cut) must be reported per initiator on July, because a threshold chosen on the mixed population lands at a different escalation rate on agent rows. Owner: classifier lane at M2, David at O4.

### N3: the zero-history slice is structurally empty offline

Every customer in both packs has history (minimum 27 rows per customer in the additional pack per its `metadata.json`; every base-pack customer has months of rows). A genuine zero-history or first-purchase customer therefore cannot exist in any offline split, including the reserved 20%. Design `:110` already says a held-out customer with eleven months of profile is not a cold start and demands the slice be reported as unassessable when outcomes are insufficient. M2 must expect the zero-history cell to be empty by construction and must not present low-support (1-5 purchases) or new-card slices as cold-start evidence. Owner: classifier lane at M2.

### N4: live and historical feature derivations stay separate

`recent_attempt_count_10m`, `spend_in_period_before_chf` and `authority_status` exist on live attempt rows (`viseca-2026/data/purchase_attempts.csv`) but have no historical counterpart with the same semantics; the reverse holds for lifetime `approved_spend_before_chf`. Design `:84-88` already forbids training on one and substituting the other and requires inference-time availability for every deployed feature. Verified as present and correct in the frozen design; M0 adds nothing that weakens it. Carried forward, no action at M0.

### N5: ledger wording about a manifest that does not exist

`docs/plans/02-classifier-progress.md:52` says "commit and SHA-256 manifest in the ledger" for the frozen M0 target. There is no manifest file; the target is a commit plus the document hash, which the handoff only requires as a manifest for uncommitted design-only artifacts. Either write the manifest or fix the sentence. Owner: classifier_manager_live.

## What was verified and held

Every load-bearing factual claim in M0 was checked and confirmed:

- Pack statistics: base 4,701 rows, 20 customers, 41 cards, 2025-09-01 to 2026-07-31, 4,565 purchases (4,112 human, 453 agent), 258 declined purchases. Additional: 144,674 rows, 500 customers, 832 cards, same span, 140,096 purchases (121,059 human, 19,037 agent), 8,154 declined. Zero customer, card or authorization-ID overlap between packs. All exact.
- The 45 public attempts span 2026-08-09 to 2026-08-22 (after both history spans), 45 authorizations, 56 cart lines.
- Catalogue equality: all 56 attempt lines carry `item_name` and `item_category` identical to `items.csv`. Exact-name comparison is therefore the only wording gap, exactly as M0 section 2 states, and the instruction-versus-catalogue table matches `scenario_catalogue.csv` verbatim.
- Scenario card and customer scope: AUTH0001 and AUTH0002 are CU0001 on CA0001 with CA0002 also held; AUTH0003 CU0006 on CA0011 (CA0012); AUTH0004 CU0012 on CA0023 (CA0024); AUTH0005 CU0019 on CA0039 (CA0038). Customer scope differs from card scope for every scenario, as M0 section 5 claims.
- Source citations: `extract/facts.py:125-133` (composite `matches_request` provenance while size contributes at 126-128), `contracts/decision.py:31,34,55` (no `"model"` source, `item_id`-keyed facts), `engine/evaluate.py:42` (pure four-argument evaluator), `engine/rules.py:260`, `engine/data.py:32-57,78`, `engine/checks.py:100,113,138,200`, `runner/loop.py:43-44,104,120,136-142,170-175,215-216,232-241,246-247`, `runner/records.py:51-59`, `runner/stepups.py:40,51,59-60,162-181`, `runner/api.py:3,33`, `api/mandates.py:64-93`, `docs/contracts.md:177`, `docs/idea/viseca-agent-control-layer.md:155,170`, `docs/models.md:30`. All verified at this head.
- The two-lock mutation gap, the missing intent journal, the `engine_timeout` substitute decisions and the app-edit blindness in M0 sections 6 and 7 are real in the cited source and correctly assigned to their owners (P3 runner and app, P4 runner, O3 David).
- The Jev pin correction (`jev-1.13.0` does not exist on the route; `typesafe/jev-1.13-20260917` served, provider-pinned, fallbacks off) is recorded with its evidence and without a latency claim. Consistent with the design's pinning and no-substitution rules.
- The additional README's learnability note (AUC 0.81 / 0.65) is quoted accurately in design `:30`.

## Commands actually run

All read-only. No tracked file was edited, staged or committed; no branch, ref or worktree changed; no provider or simulator call; no `uv run`.

- `git status`, `git log --oneline -5`, `git rev-parse HEAD origin/lane/classifier`, `git show --stat HEAD`, `git cat-file -p HEAD^{tree}`, `git branch -a --contains HEAD`, `git remote -v`.
- `shasum -a 256` over `02-classifier-m0.md`, `02-classifier-design.md`, `02-classifier-progress.md`, `02-classifier-handoff.md`, `02-classifier-review.md`, before and after review.
- `python3` stdlib scripts (no repository code imported) over `viseca-2026/data` and `viseca-2026/additional-data-history`: pack counts and spans, initiator and status splits, transaction-type mix, cross-pack ID overlap, attempt span and counts, scenario authority ownership, catalogue equality over all 56 lines, deterministic-rule decomposition of declined purchases, calendar-month limit reproduction, per-month composition, agent and human decline rates.
- `sed` and `grep` reads of every cited source file and README.

The repository's own scripts were not executed: the grading tree has no virtualenv and its `uv.lock` is deliberately untracked, and reviewer rules allow one-off runs but not dependency installation into a tree whose state must stay pristine. The M0 SCEN0004 decision table therefore stands as the manager's recorded observation; its inputs, construction and citations verify, and the deterministic path it exercises was read line by line.

## Limitations

- Single reviewer, one lens. Authorization, injection and integration coverage belongs to the other two panel seats.
- The deterministic-rule decomposition is my reconstruction from pack columns; the generator's true rule set may be larger, so 42% is a lower bound on the rule-explained share.
- Accepted effort tier is unobservable from inside the seat (see header).
- The M0 document's milestone sequencing (M1 before M3, O1 gating Jev inputs) was assessed for consistency, not re-derived from the simulator documentation beyond the cited lines.

## Observed outcome

One blocker (G1, split-protocol leakage into the final refit, correction is one recorded paragraph), four non-blocking findings with owners, one ledger wording fix. Every factual claim in the M0 document that I could check from the repository and the data packs is accurate, every citation resolves, and the ownership map leaves no classifier-lane file with an ambiguous writer. The design's evaluation-honesty apparatus (separate deterministic subset, initiator split, cold-start slices, calibration windows, reserved customers, threshold-as-owner-decision) is present and is the reason this review found only one protocol defect rather than several.

A changed target hash voids this verdict. Terminal verdict for the round follows on `team.zurichbuchegg.classifier.review`.
