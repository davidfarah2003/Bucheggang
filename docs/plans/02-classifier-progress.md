# Classifier progress and review ledger

- Feature: personalized payment classifier, per [02-classifier-handoff.md](02-classifier-handoff.md).
- Manager seat: `classifier_manager` on the Cotal mesh, space `zurichbuchegg`.
- Reviewed proposal: [02-classifier-design.md](02-classifier-design.md), SHA-256 `4d8ea6601aa2a23927a895b03ccd8e90ec8ae275da818dbc377d01e258409eb9`, unchanged (re-hashed 2026-09-24 20:21 CEST). The proposal and its review record stay as written. Implementation decisions are recorded here and in later milestone files.

## Startup proof, 2026-09-24 20:21 CEST

Observed by a fresh shell read in this session, after `git fetch origin`:

| Item | Observed value |
| --- | --- |
| cwd | `/Users/david/Projects/Bucheggang/.worktrees/classifier` |
| branch | `lane/classifier` |
| HEAD at handoff | `3d6002ba74e9911766df6646a90505454ff8abd3` |
| HEAD now | `4cbc28e8a7044f5aacb7d820a85fa69eb4effc0b`, fast-forwarded to `origin/main` (merges of PR #14, #15, #16, #18). No local commits. |
| working tree | untracked only: the four `classifier_*` personas, the design, handoff and review files, and this file. Nothing modified, nothing staged. |
| handoff file | `02-classifier-handoff.md` SHA-256 `c90e27a41060dcc80584a03b9a427db3d783fc7aff8ac6d0cef25d8618eb3245` |
| review record | `02-classifier-review.md` SHA-256 `3560b454d501838aa411d6c2e523b7ebda51a76cbf06c37cfb1f2a1299a0e082` |

Model and effort:

- `cotal_orientation` reports `Model pin: claude-opus-5-5 (from COTAL_MODEL / the agent file)`. The session's own system identity is Opus 5.5, `claude-opus-5-5`.
- Effort: the persona requests `launchOptions.effort: xhigh`. The effort level is not observable from inside the session. david_orch reported by DM at about 20:15 that the native Claude Code UI shows xhigh. That is their observation, recorded here as theirs.
- Harness: Claude Code, auto permission mode. The user approved continuing auto mode on the existing gateway billing (relayed by david_orch).

Cotal grants, as `cotal_orientation` reported them at 20:16 (broker-enforced, auth mode):

- Capabilities: `spawn`, `role:default`.
- Post: `team.zurichbuchegg`, `team.zurichbuchegg.>`, `events.u_z6cyd6sxvllatss36qzlv3oexu.>`. This is wider than the persona's `allowPublish`. The seat does not post on the human spine.
- May join: `announce`, `team.zurichbuchegg`, `team.zurichbuchegg.>`, three `events.<user>.>` subtrees.
- The seat booted on `announce` and the spine again after the session restart. Both were left. Joined `team.zurichbuchegg.classifier` and `team.zurichbuchegg.classifier.review` in normal mode, `team.zurichbuchegg.contracts` and `team.zurichbuchegg.progress` in quiet mode (confirmed by `cotal_channel_mode` results).
- `cotal_spawn` and `cotal_despawn` are in the tool list and have not been exercised yet.
- `cotal_personas` failed at 20:17: "this request reached manager instance pwa8zc1o7zisrm684fbfmcpoo3b4x58, but the caller bound to 8bwdfej50l4iuviwyuqfoscgad4vn1r; the class queue chose a different member and list-personas WAS NOT RUN". This is the multi-manager binding mismatch the handoff describes. The roster shows two managers, `local.UATCAQ...` and `u_i6vuwbdwxmqjum2qaro6fjo3om.manager_pwa8...`; neither id matches the one this seat is bound to.

## Ownership boundaries

| Area | Owner | Notes |
| --- | --- | --- |
| `.worktrees/classifier`, branch `lane/classifier` | classifier_manager | only writer checkout of this seat |
| `src/leash/contracts/`, `src/leash/engine/` evaluator, checks, state | engine_builder (coordinated by david_main) | PR #21 `046bd73` (record contract) and PR #22 `f2fa10e` (state store, checks, evaluate) are open and unmerged |
| runner infrastructure, `src/leash/runner/` | runner_builder | PR #18 merged at `4cbc28e` |
| offline replay, `scripts/replay.py` | david_orch | plan 05 task 3; not duplicated here |
| policy, extraction | Oskar (oskar1, extract_builder) | PR #19 `6a2e128` removes the purchase-time extraction model |
| app | Rishabh (rishabh_agent) | |
| proposed classifier modules | classifier_manager, pending engine_builder agreement at M0 | proposal: a subpackage `src/leash/engine/classifier/` (history features, behavioural inference, Jev adapter), offline scripts under `scripts/classifier_*.py`, manifests and reports under `docs/eval/classifier/`. Integration into `evaluate()` goes through an interface agreed with engine_builder, not by editing their files. |

## Milestones

| Milestone | State | Target | Review round |
| --- | --- | --- | --- |
| M0 re-anchor, scope, contract proposal, ownership map | in progress | not yet frozen | not started |
| M1 personal-history features and deterministic integration | not started | | |
| M2 offline behavioural-model comparison | not started | | |
| M3 Jev semantic assessments | not started; blocked on M0 scope item 1 and credentials | | |
| M4 end-to-end integration and release decision | not started | | |

## Open items for M0

1. Jev scope versus the no-model ruling. david_main posted on `contracts` that no model runs at purchase time. Docs PR #20 (`13ca99f`, open) writes "No language model runs at purchase time" into `docs/idea/viseca-agent-control-layer.md` and "No model call in the decision path" into the security requirements, and removes `model` from `FactSource` and `Check.source`. At about 20:20 david_orch relayed by DM that david_main reports David clarified the ruling as extraction-only and that Jev decision classification stays in scope. This is second-hand; M0 needs the clarification written into a file the owner controls, and PR #20's wording reconciled with a Jev assessment path, before any model-enabled code.
2. Provenance B1 is still present on main: `src/leash/extract/facts.py:130` copies only the `product_type` source into `sources["matches_request"]`, while lines 127-128 also use size.
3. Integration interface with engine_builder: where history features and assessments enter `evaluate()`, given PR #22's signature. Agree on `contracts` before writing under `src/leash/engine/`.
4. Local-policy overlay versus the simulator's frozen run snapshot, mutation coordination (R1), absolute deadlines for automated and human paths (R2), redundant selected option (R3). runner_builder logged that a PATCH with any `hard_rules` returns 409 `mandate_widening`; only `uncertainty_policy` tightening works live.
5. ML dependencies. `pyproject.toml` on main has no numpy, scikit-learn or catboost. M2 needs them; adding them touches a shared file and needs agreement.

## Known blockers

- Reviewer spawning. The `classifier_review_*` personas exist only as untracked files in this worktree. The manager reads personas from the repo root's `.cotal/agents/`, which does not contain them (checked 20:20). Together with the manager binding mismatch above, `cotal_spawn(name: "classifier_review_grok")` is not expected to work until the personas are committed to main or another supported path is agreed. No grants or supervisors will be changed to work around it.
- Reviewer tiers untested. grok-4.7 high, gemini-3.8-flash high and glm-5.3 max on Jcode have not been launched at those tiers. They will be attempted exactly as specified at the first frozen target; a refusal is reported, not substituted.
- Jev credentials. The root `.env` defines no Jev provider variable (variable names checked, values not read). M3 cannot run a real provider call until a scoped credential is supplied.

## Reviewer ledger

| Milestone | Round | Reviewer | Model / requested effort | Launch result | Target | Report | Verdict | Cleanup |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Log

2026-09-24 20:21 classifier_manager: startup. Oriented, fixed channels, fast-forwarded lane/classifier 3d6002b to 4cbc28e (origin/main), wrote this record. No source changed, no model fitted, no provider or simulator called.
