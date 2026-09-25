# O4 operating point

Status: manager-selected O4 cut. Runtime activation and release clearance remain unverified.

David's direct response on 2026-09-25 approved enabling behavioural escalation and left the numeric choice to this feature manager. I select the most conservative of the four frozen June proposals: calibrated score at least `0.8950478918645203`. The fitting and calibration periods are unchanged. This is a review signal for a customer step-up, never an automatic decline, approval or fraud finding. Deterministic failures remain authoritative.

| Frozen observation | All purchases | Agent purchases | Human purchases |
| --- | ---: | ---: | ---: |
| June 16-30 selected cut, escalation rate | 1.0087% | 1.8519% | 0.8080% |
| June decline recall | 17.91% | 22.50% | 15.96% |
| Reserved July rate at unchanged cut | 0.9630% | 2.0455% | 0.7421% |
| Seen July rate at unchanged cut | 1.1503% | 1.5218% | 1.0592% |

The selection minimizes the observed review burden among the four frozen candidates. The public 45-attempt score maximum was 0.2364, below the selected cut. Those attempts therefore cannot demonstrate an escalation at this cut. The reserved agent July 0.0-0.1 score band underpredicted historical declines, and the zero-history/low-support July slices have no calibration evidence. Historical decline is a proxy for a review signal, not a consent or fraud label.

The proposed operating budget for a staged release is at most 1.5% classifier-driven step-ups over all evaluated purchases and at most 3% among agent purchases in an observed window of at least 1,000 relevant events. These are release monitoring ceilings, not a per-request fallback or a reason to discard a required result. If observed volume exceeds a ceiling, pause further rollout through an explicit operator release decision; do not substitute an approval or retry a model call. No live counter or operator release procedure exists yet, so the budget has not been enforced or verified.

The [explicit O4 overlay](model-o4-1pct.json), SHA-256 `60eedeced3e10931065a84b7a69d66dc6f7a083a64b9380268ae00f04ea3ae71`, pins the unchanged evaluation manifest by SHA-256 and names the frozen June cut. `BehaviorModel` rejects an overlay that points outside the repository, differs from the pinned manifest, changes the release status or names a cut absent from the June proposals. The selected `model_id` includes the overlay digest prefix. The original evaluation-only manifest remains unchanged and its scoring flag stays false.

One actual derivation over the additional history found a July historical purchase with pre-event score `0.921225` after 37 July rows. The selected overlay set `escalation_fired=True`; the evaluation-only configuration scored the same purchase identically and set the flag false. The derivation took 30.25 seconds including the earlier months. The row's historical status was declined. This is a local scorer exercise, not an authorization decision or a calibration result.

A separate one-off run scored all 45 public authorization profiles under baseline-projected state. Scores ranged from `0.029953` to `0.236441`; zero reached the selected cut. The first probe failed with `KeyError: 'AU0005'` because it did not advance the offline state between events. The corrected run applied each actual baseline decision and completed all 45 profiles. No provider call or customer answer occurred.

A further one-off run on those 45 events derived each authorized profile twice and scored it twice against the selected artifact. Both profiles and scores matched on every event. The combined local duplicate derivation and scoring took 1.415 ms median and 10.51 ms maximum. These timings exclude provider, extraction, locks, simulator I/O and customer waiting; they do not establish a full decision deadline. A separate one-off AU0001 profile derivation and score were identical on both local passes; changing only the scored `escalation_fired` flag made the result unequal to the trusted recomputation. This exercised the comparison used by the runner, without calling Jev or the complete model-enabled runner path.

At `d81abd4`, the runner accepts both the SHA-pinned O4 overlay and main's explicit threshold for its evaluation-only manifest. The main demo scripts currently default to a separate `0.498` threshold; that demo cut is not the selected O4 release cut. An O4 overlay with a conflicting configured threshold raises before loading the provider credential. After assessment, the runner re-derives the authorized pre-event features and re-scores them with the loaded model. A mismatched feature profile, score, support, model identifier or escalation flag raises before decision composition. The pure evaluator is not an authenticated external boundary.

Activation still requires complete real-provider coverage, exact-head release clearance, current policy/state and deadline checks, and a genuine Wallet customer-answer run. The shared `JevAnswer` accepts off-grid sums within 0.015, while the classifier adapter at `d81abd4` additionally requires each returned probability to lie on the 0.01 grid. The contract owner has not aligned that broader shared type with the selected provider format. Earlier local opt-in startup reached the missing scoped provider credential before any request. After the merge, offline runs checked the O4 scorer, default model-off evaluator and captured provider-body parsing; no new provider, simulator or Wallet call was made.

Source: [M2 report](m2-report.md) and [frozen model manifest](model-manifest.json), including `june_threshold_proposals` and `july_rates_at_june_proposals`.
