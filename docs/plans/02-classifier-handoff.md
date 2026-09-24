# Classifier feature handoff

Date: 2026-09-24. Assigned by David in the david_orch session.

## Assignment

The user asked for one Opus 5.5 manager at xhigh effort, running Claude Code, to manage the classifier feature. It must run independent reviews after each milestone using Jcode peers on Grok 4.7 high, Gemini 3.8 Flash high and GLM 5.3 max. Finished reviewers must be cleaned up. The originating session moves to its next assigned task once the handoff is verified.

This explicitly delegates reviewer spawning to this manager. It does not permit Claude Code subagents, extra implementation agents, changed repository protection, suppressed errors, skipped review blockers or unauthorized deployments. The project-wide no-tests/no-linter and no-runtime-fallback rules remain in force.

## Source documents

- `docs/plans/02-classifier-design.md`, independently reviewed proposal, SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`.
- `docs/plans/02-classifier-review.md`, initial blockers, corrections, approval and three required implementation clarifications.
- `docs/plans/02-decision-engine.md`, foundation-engine scope.
- `docs/contracts.md`, current cross-lane contracts. The design proposal does not itself change this file.
- `docs/plans/03-merchant-text-extraction.md` and `05-simulator-runner.md`, adjacent lanes.

The approved proposal's baseline was e7e2b0e. This handoff worktree starts at main 3d6002b. The new package setup, local-demo session contract and generic exact-name extraction have landed since the proposal's baseline. Reconcile them before implementation. Preserve the original reviewed plan and review record; record implementation decisions separately rather than implying the old approval covers changed designs.

## Ownership

- Your exclusive writer checkout is `.worktrees/classifier`, branch `lane/classifier`.
- `engine_builder`, coordinated by `david_main`, owns foundation contracts and the deterministic rule evaluator on engine branches. PR #15 introduced contracts at f4ba0e8; task 2 was reported as PR #16 at f976151. Verify live refs before depending on them.
- `runner_builder` owns the runner mandate client and subsequent polling/deadline work. It was briefed on plan 05 tasks 1 and 2, then task 4 after merge. Do not take its worktree or files without an agreed ownership transfer.
- `david_orch` is taking plan 05 task 3, offline replay, once the required foundation changes land. Do not duplicate scripts/replay.py.
- Policy and extraction are Oskar's lanes; app belongs to Rishabh. Their owners must agree changes to their interfaces and files.

You own the classifier extension: history features, behavioural-model comparison, Jev assessment, evidence/decision integration and the feature's milestone ledger. Agree exact owned module paths with engine_builder before both parties write under src/leash/engine. Work independently on data analysis and documents while contracts are unsettled. Do not overwrite or replace foundation work to make integration easier.

## Milestones

M0. Re-anchor on current main and agree integration scope. Resolve exact-name inequality versus genuine semantic mismatch, full dependency provenance, local-policy overlay and mutation coordination, absolute transport deadlines, and the review record's R1-R3. Check the required provider/model/effort settings. Produce a scoped contract proposal and ownership map.

M1. Personal-history features and deterministic integration. Keep card, customer and mandate scopes separate; use pre-event data; exercise actual evaluator/replay once with observable outputs. A novelty score cannot clear a hard failure.

M2. Offline behavioural-model comparison. Use the additional-history pack, frozen customer/time splits and separated calibration/threshold periods. Compare logistic regression and CatBoost. The target is historical decline propensity. Keep learned live effects disabled until the owner selects a threshold and confirms the release conditions.

M3. Jev semantic assessments. Pin the provider/model, validate complete per-line results, enforce provenance and the permitted evidence-reliance rule, and measure real end-to-end deadlines. Dependency failure raises; there is no substitute model or fabricated business decision.

M4. End-to-end feature integration and release decision. Combine exact checks, successful assessments, current policy/state, customer step-up and accepted-result persistence. Use the existing replay and real app/API path; record what ran, what failed and what remains unmeasured. Optional justification input and external shopping-dataset expansion remain outside the first release unless David explicitly extends the scope.

Run a review round at every completed milestone. Do not move to the next dependent milestone while that round has unresolved blocking findings. Independent preparatory work may continue outside the frozen review surface.

## Review panel

| Persona | Runtime | Model | Required effort | Lens |
| --- | --- | --- | --- | --- |
| classifier_review_grok | jcode | grok-4.7 | high | Authorization, injection, evidence trust, races and fail-closed handling |
| classifier_review_gemini | jcode | gemini-3.8-flash | high | Contract fidelity, integration and executable user flows |
| classifier_review_glm | jcode | glm-5.3 | max | Training targets, leakage, personalization, calibration and measurement |

One live peer per reviewer role. Use all three for each substantive milestone. Spawn only against a frozen, available target. Each peer gets its own detached grading worktree and a report directory outside it. Reviewers may perform documented one-off runs and replay; no test suites or linters. They never edit source or git state in the grading tree.

For committed targets, record exact head and base SHAs. For an uncommitted design-only M0 artifact, freeze an immutable copy and SHA-256 manifest. Never move a target underneath its reviewer. Preserve terminal reports under docs/reviews/classifier/<milestone>/<round>/, with exact target, model and requested/accepted effort, findings, commands actually run and limits. Do not convert requested effort into a claim of observed provider behaviour.

All three must clear the same exact target. A changed code head voids earlier approvals. Collect one complete findings list before edits, make the corrections, then ask the same peers for a bounded second pass. After two rounds, record lower-severity suggestions with an owner; high/security/correctness blockers still block. Final repository merge requirements remain those in AGENTS.md and the user's authorization boundaries.

## Channels and communication

- Work: `team.zurichbuchegg.classifier`.
- Review: `team.zurichbuchegg.classifier.review`.
- Cross-lane interfaces: `team.zurichbuchegg.contracts`, quiet except targeted questions.
- Fleet milestones: `team.zurichbuchegg.progress`, quiet, one durable pointer per material event.
- Do not join or post to the human spine as an implementation manager. Use DM to david_orch or david_main for owner rulings.

Each seat must inspect actual subscriptions at startup. This mesh has previously booted peers on announce/the spine despite persona lists. Leave those channels and join only the authorized work/review channels. No acknowledgements, starting announcements, mention loops or duplicate cross-posts.

## Runtime constraints to verify

The Cotal MCP manager tools have hit multi-manager binding mismatches. A direct local foreground Cotal launch worked for the prior plan reviewer. A pinned manager-instance describe was refused because the caller lacked that instance-specific grant. Do not bypass the refusal, change grants or repair shared managers. Use only supported, authorized launch paths and report a genuine permission blocker.

Claude's Cotal connector rejects `variant`; pass xhigh through its supported `launchOptions.effort` / `--opt effort=xhigh` instead. Confirm the launch selected claude-opus-5-5 and that the effort flag was accepted.

Jcode's catalog declares the requested reviewer tiers, but declarations do not prove runtime support. The earlier Astra launch failed because cliproxy did not expose reasoning-effort support for that model. These three reviewer routes have not yet been exercised at their requested tiers. Attempt exactly the requested model/tier when there is a concrete milestone to review. If a route rejects the effort or model, record the exact failure and ask the user/operator; never omit the requested tier, substitute a model or patch the connector to silence the check.

Managed Cotal workflow execution is not known to be available on this user-auth mesh. Do not claim a durable hosted workflow is running without an accepted run and observed status. Keep the milestone/seat ledger on disk regardless.

## Cleanup and handoff completion

After a round converges, confirm each report is durable and attributable before terminating its reviewer. Retain the same peers during the correction round. For managed peers, use normal Cotal despawn. For foreground peers, terminate only the exact recorded process/task owned by this manager and verify exit. Never use broad process-name kills.

Reviewers must not delete their own worktrees or shared git refs. The manager may remove a reviewer checkout only after verifying it contains no uncommitted work or unique evidence and all reviewed outputs remain reachable. Preserve dirty or ambiguous trees and report them. Do not remove another lane's checkout, branch, credentials or processes.

When the whole feature is complete, write a final report with exact delivered refs, runtime evidence, remaining limitations and cleanup results. Report to the owner before ending the manager seat. A feature is not complete because its agents are idle or a spawn returned successfully.

## First startup proof

Before beginning implementation, create `docs/plans/02-classifier-progress.md` with the actual working directory, branch/HEAD, reviewed-plan hash, model/effort configuration, granted Cotal capabilities, ownership boundaries, first milestone and known blockers. Run a fresh shell read of branch/HEAD rather than echoing this brief. Send david_orch the path, its SHA-256 and a concise factual startup result. A missing model, effort or spawn capability is a blocker to report, not a successful handoff.
