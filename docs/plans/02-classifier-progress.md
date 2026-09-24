# Classifier progress and review ledger

- Feature: personalized payment classifier, per [02-classifier-handoff.md](02-classifier-handoff.md).
- Manager seat: `classifier_manager_live` on the Cotal mesh, space `zurichbuchegg`, since the 20:4x restart. The earlier seat `classifier_manager` is stopped and stays stopped.
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
| `.worktrees/classifier`, branch `lane/classifier` | classifier_manager_live | only writer checkout of this seat |
| `src/leash/contracts/`, `src/leash/engine/` evaluator, checks, state | engine_builder (coordinated by david_main) | merged on main: #21 `11d911f`, #22 `1180c07`, #23 `3665ab1` |
| runner infrastructure, `src/leash/runner/` | runner_builder | merged on main: #18 `4cbc28e`, #24 `7d7e176`, #25 `ed2bc3c` |
| offline replay, `scripts/replay.py` | david_orch | plan 05 task 3; not duplicated here |
| policy, extraction | Oskar (oskar1, extract_builder) | #19 `2befdc0` (purchase-time extraction model removed) merged |
| app, `src/leash/api/` | Rishabh (rishabh_agent) | #26 `636629e` (mandate routes, `MandateEdits`) merged |
| proposed classifier modules | classifier_manager_live, pending engine_builder agreement | full map in [02-classifier-m0.md](02-classifier-m0.md) section 11 |

## Milestones

| Milestone | State | Target | Review round |
| --- | --- | --- | --- |
| M0 re-anchor, scope, contract proposal, ownership map | r1 open: gemini APPROVE, glm BLOCK (G1), grok pending | [02-classifier-m0.md](02-classifier-m0.md) at commit `d651ef8`; file hashes in [MANIFEST.sha256](../reviews/classifier/M0/r1/MANIFEST.sha256) | r1 |
| M1 personal-history features and deterministic integration | not started | | |
| M2 offline behavioural-model comparison | not started | | |
| M3 Jev semantic assessments | not started; needs owner ruling O1 and contract P1 | | |
| M4 end-to-end integration and release decision | not started | | |

## Open items after M0

The open items from startup are answered in [02-classifier-m0.md](02-classifier-m0.md):

1. Jev scope: main now carries the ruling (`docs/idea/viseca-agent-control-layer.md:155, 170`, `docs/models.md:30`, docs PR #20 merged as `4fcaab6`). Jev reads the customer's own history, adds a step 8 risk signal and never reads merchant text. Catalogue fields are owner ruling O1.
2. B1 is still on main at `src/leash/extract/facts.py:130` (Oskar).
3. Integration interface: proposal P2 (`assess()` outside `evaluate()`, one optional `assessments` argument).
4. R1: proposal P3 and owner ruling O3. R2: proposal P4. R3: M0 section 8.
5. ML dependencies: proposal P5.

## Model pin

Jev through OpenRouter System One, `typesafe/jev-1.13-20260917`, provider pinned to `typesafe` with fallbacks off. The key is `OPENROUTER_API` in the main checkout `.env` (name only; the value is never printed). Evidence in M0 section 9.

## Known blockers

- Reviewer launch route. The `classifier_review_*` personas are committed on `lane/classifier` only; main does not carry them, so the manager's catalogue cannot spawn them by name. Reviewers launch in the foreground with `cotal spawn --config <absolute persona path>`, the route the handoff records as working for the prior plan reviewer. No grants or supervisors are changed.
- Reviewer tiers: first exercised at the M0 round. Outcomes are in the ledger.
- Owner rulings O1 to O4 (M0 section 12).

## Reviewer ledger

| Milestone | Round | Reviewer | Model / requested effort | Launch result | Target | Report | Verdict | Cleanup |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0 | r1 | classifier_review_grok | jcode grok-4.7 / high | launch 1 PID 6695 exited 1 without a report (evidence in `/private/tmp/classifier-review-reports/M0/r1/grok/launch1-evidence/`). Launch 2 PID 93053 (task `bvpgalun1`) resumed `session_crab_1790278215234_c7a85d4d097dc0d1` and stalled on authentication and manager-binding errors. Stopped the exact task at 23:19; launcher and bridge 94226 exits verified. Launch 3 PID 44974 exited 1 before review: its event WAL lock was held by PID 6861 recorded on `Davids-MacBook-Pro-1030.local`, while the current host identified as `Mac.galaxus.box`. No lock or event state was changed. Launch 4 uses the same persona, model and tier under fresh principal `classifier_review_grok_r1fresh`, PID 58750 (task `b1xojtxpk`), with an eight-minute report-or-error brief and its own detached grading tree | `d651ef8`, base `ed2bc3c`, manifest [MANIFEST.sha256](../reviews/classifier/M0/r1/MANIFEST.sha256) | pending at 23:23, `/private/tmp/classifier-review-reports/M0/r1/grok-fresh/report.md` | pending | original grading tree `/private/tmp/classifier-m0-r1-grok` preserved clean; fresh tree `/private/tmp/classifier-m0-r1-grok-fresh` clean at `d651ef8` |
| M0 | r1 | classifier_review_gemini | jcode gemini-3.8-flash / high | 21:31 same route, launcher PID 10043 (task `bmohyb8j3`), children 10212, 10218, 10372; jcode session `session_vole_1790278266685_0c9e46ca321f8704`, journal `/private/tmp/jc-42308d2e4536/home/sessions/`; launcher still alive after the verdict | same | [report.md](../reviews/classifier/M0/r1/gemini/report.md), SHA-256 `61ca79a6ba01bdf1efebd89cbd95d8fb167d9c721edd6c6746dc0cfd6357ffe9` | APPROVE `d651ef8` | grading tree `/private/tmp/classifier-m0-r1-gemini`, clean; launcher not yet stopped |
| M0 | r1 | classifier_review_glm | jcode glm-5.3 / max | 21:31 same route, launcher PID 10235; jcode session `session_seedling_1790278266746_0ef44751a2c0c41b`, journal `/private/tmp/jc-fa84d885c314/home/sessions/`. Wrote its report, DM and verdict, then the launcher exited 1 on a journal error. Orphan 10374 stopped by exact PID (TERM), exit verified; 10447 reaped | same | [report.md](../reviews/classifier/M0/r1/glm/report.md), SHA-256 `f10f1a62fa6626bade7ab23411316c6529deace6b6d9ce8aa900fb5d096227b6`. Written first to the non-designated path `/private/tmp/classifier-m0-r1-glm-report/glm-m0-r1.md`. david_orch placed a byte-identical copy at `docs/reviews/m0-r1-glm.md` | BLOCK `d651ef8`, G1 (high) plus N1 to N5 | grading tree `/private/tmp/classifier-m0-r1-glm`, clean; no process left |

The session-create record of each reviewer names jcode's default `gpt-5.6-sol`; every message record after it names the requested model. The effort values are the session's request settings, not observed provider behaviour.

## Log

2026-09-24 20:21 classifier_manager: startup. Oriented, fixed channels, fast-forwarded lane/classifier 3d6002b to 4cbc28e (origin/main), wrote this record. No source changed, no model fitted, no provider or simulator called.
2026-09-24 20:43 classifier_manager: merged origin/main into lane/classifier as `706e76e` (engine #22 #23, docs #17 #20, runner #24). No conflict.
2026-09-24 20:5x classifier_manager_live: replacement seat after the restart. Native stream verification printed `native-stream-20260924-1906 706e76e`. The old seat is not revived.
2026-09-24 21:0x classifier_manager_live: reviewer personas now report to `classifier_manager_live`. Ran `scripts/classifier_m0_exact_name.py` with "27-inch monitor" and "27-inch computer monitor" (M0 section 2) and `scripts/classifier_m0_jev_probe.py` with `typesafe/jev-1.13-20260917` (HTTP 200) and `jev-1.13.0` (HTTP 400) (M0 section 9). Pack statistics in M0 section 5.
2026-09-24 21:12 classifier_manager_live: merged origin/main as `1c0874b` (app #26), then as `6353982` (runner #25, `ed2bc3c`). Re-checked every M0 citation against `6353982`; the SCEN0004 output is identical.
2026-09-24 21:28 classifier_manager_live: M0 written in [02-classifier-m0.md](02-classifier-m0.md). Frozen for review round r1; commit and manifest in the ledger.
2026-09-24 21:36 classifier_manager_live: M0 r1 frozen at `d651ef8` (base `ed2bc3c`). Three detached grading worktrees and external report directories under `/private/tmp`. All three reviewers launched in the foreground on the requested model and tier; none refused. Ledger rows above.
2026-09-24 22:30 classifier_manager_live: M0 r1 reports preserved under `docs/reviews/classifier/M0/r1/`: gemini APPROVE, glm BLOCK on G1 (split protocol refits on the selection month). Grok launch 1 crashed without a report; launch 2 is reviewing. No M0 edits until grok's findings are in. M0 line 88 says P2 was "agreed with engine_builder"; no agreement message exists, so r2 corrects it to proposed. Paused all new work and spawns at david_orch's request for the managed-agent migration.
2026-09-24 23:23 classifier_manager_live: Grok launch 2 stalled for over an hour. Stopped its exact task, verified launcher and bridge exit. Launch 3 failed on a principal event WAL safety lock; preserved the lock and logs. Launched a fresh principal with the same `classifier_review_grok` persona, grok-4.7/high, immutable `d651ef8` tree and an eight-minute report-or-error brief. The five topic worktrees are clean at `2c7f168`, but no dependent milestone source work begins until the M0 panel clears. The user requested five additional builders and parallel work; the gate still applies. Current checkout has pre-existing untracked `docs/reviews/m0-r1-glm.md` and `uv.lock`, untouched.
