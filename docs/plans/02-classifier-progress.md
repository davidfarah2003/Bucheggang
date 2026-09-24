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
| M0 re-anchor, scope, contract proposal, ownership map | complete: r2 Grok, Gemini and GLM APPROVE the same exact target; low-severity zero-history erratum recorded below | [02-classifier-m0.md](02-classifier-m0.md) at `6cd4340316c0ebc546a2c0f8ff6b147ef1688db8`, base `b4c77f2`; [r2 manifest](../reviews/classifier/M0/r2/MANIFEST.sha256) | r2, all three APPROVE |
| M1 personal-history features and deterministic integration | history feature derivation implemented and exercised; evaluator contract integration pending separate engine-owned PR | [hist-1 schema](../eval/classifier/feature-schema.md), `src/leash/engine/classifier/history.py` | not frozen |
| M2 offline behavioural-model comparison | not started | | |
| M3 Jev semantic assessments | not started; history-only adapter can proceed without O1, integrated model check needs P1 | | |
| M4 end-to-end integration and release decision | not started | | |

## Open items after M0

The open items from startup are answered in [02-classifier-m0.md](02-classifier-m0.md):

1. Jev scope: main now carries the ruling (`docs/idea/viseca-agent-control-layer.md:155, 170`, `docs/models.md:30`, docs PR #20 merged as `4fcaab6`). Jev reads the customer's own history, adds a step 8 risk signal and never reads merchant text. Catalogue fields are owner ruling O1.
2. B1 is still on main at `src/leash/extract/facts.py:130` (Oskar).
3. Integration interface: proposal P2 (`assess()` outside `evaluate()`, one optional `assessments` argument).
4. R1: proposal P3 and owner ruling O3. R2: proposal P4. R3: M0 section 8.
5. ML dependencies: proposal P5.

## M0 r2 errata for downstream work

The frozen M0 r2 document says the zero-history slice has no examples in either supplied pack. A strict pre-event count of prior approved customer purchases finds 542 such purchase rows in the additional pack and 23 in the base pack, all in September 2025. With zero prior rows of any kind, the counts are 482 and 15. July 2026 has zero customer-scoped rows under either definition. Card-scoped zero-prior-approved-purchase counts are different, including five additional-pack July purchases. M1 records the exact scope and missing-value rule. M2 may fit on early zero-history rows, but cannot quote July outcome metrics for that customer-scoped slice. Grok and Gemini preserved separate r2 addenda and kept their approvals. Correct this sentence in a later reviewed target; do not reinterpret the frozen M0 file as a true whole-pack count.

Grok r2 also noted stale `file:line` anchors in M0 after the main merge. The classifier lane checks current source positions before implementing M1 and M4, and updates citations in the next relevant reviewed document. Neither suggestion is treated as an M0 security or contract blocker by those two reviewers.

## Model pin

Jev through OpenRouter System One, `typesafe/jev-1.13-20260917`, provider pinned to `typesafe` with fallbacks off. The key is `OPENROUTER_API` in the main checkout `.env` (name only; the value is never printed). Evidence in M0 section 9.

## Known blockers

- Reviewer launch route. The `classifier_review_*` personas are committed on `lane/classifier` only; main does not carry them, so the manager's catalogue cannot spawn them by name. Reviewers launch in the foreground with `cotal spawn --config <absolute persona path>`, the route the handoff records as working for the prior plan reviewer. No grants or supervisors are changed.
- Reviewer tiers: first exercised at the M0 round. Outcomes are in the ledger.
- Owner rulings O1 to O4 (M0 section 12).

## Reviewer ledger

| Milestone | Round | Reviewer | Model / requested effort | Launch result | Target | Report | Verdict | Cleanup |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0 | r1 | classifier_review_grok | jcode grok-4.7 / high | launch 1 PID 6695 exited 1 without a report (evidence in `/private/tmp/classifier-review-reports/M0/r1/grok/launch1-evidence/`). Launch 2 PID 93053 (task `bvpgalun1`) resumed `session_crab_1790278215234_c7a85d4d097dc0d1` and stalled on authentication and manager-binding errors. Stopped the exact task at 23:19; launcher and bridge 94226 exits verified. Launch 3 PID 44974 exited 1 before review: its event WAL lock was held by PID 6861 recorded on `Davids-MacBook-Pro-1030.local`, while the current host identified as `Mac.galaxus.box`. No lock or event state was changed. Launch 4 uses the same persona, model and tier under fresh principal `classifier_review_grok_r1fresh`, PID 58750 (task `b1xojtxpk`), with an eight-minute report-or-error brief and its own detached grading tree | `d651ef8`, base `ed2bc3c`, manifest [MANIFEST.sha256](../reviews/classifier/M0/r1/MANIFEST.sha256) | [report.md](../reviews/classifier/M0/r1/grok/report.md), SHA-256 `18cb257d77a309c485e9fa367bdac3ae9f39483e0a83a8a2bf5949907cc39962` | APPROVE `d651ef8`, N1 to N3 non-blocking | both r1 grading trees removed by exact path after preserving the report; launch 4 exited before r2 and was relaunched as the same principal |
| M0 | r1 | classifier_review_gemini | jcode gemini-3.8-flash / high | 21:31 same route, launcher PID 10043 (task `bmohyb8j3`), children 10212, 10218, 10372; jcode session `session_vole_1790278266685_0c9e46ca321f8704`, journal `/private/tmp/jc-42308d2e4536/home/sessions/`; launcher still alive after the verdict | same | [report.md](../reviews/classifier/M0/r1/gemini/report.md), SHA-256 `61ca79a6ba01bdf1efebd89cbd95d8fb167d9c721edd6c6746dc0cfd6357ffe9` | APPROVE `d651ef8` | grading tree `/private/tmp/classifier-m0-r1-gemini` removed by exact path; original launcher exited after its Jcode journal vanished, then the same principal was relaunched for r2 |
| M0 | r1 | classifier_review_glm | jcode glm-5.3 / max | 21:31 same route, launcher PID 10235; jcode session `session_seedling_1790278266746_0ef44751a2c0c41b`, journal `/private/tmp/jc-fa84d885c314/home/sessions/`. Wrote its report, DM and verdict, then the launcher exited 1 on a journal error. Orphan 10374 stopped by exact PID (TERM), exit verified; 10447 reaped | same | [report.md](../reviews/classifier/M0/r1/glm/report.md), SHA-256 `f10f1a62fa6626bade7ab23411316c6529deace6b6d9ce8aa900fb5d096227b6`. Written first to the non-designated path `/private/tmp/classifier-m0-r1-glm-report/glm-m0-r1.md`. david_orch placed a byte-identical copy at `docs/reviews/m0-r1-glm.md` | BLOCK `d651ef8`, G1 (high) plus N1 to N5 | grading tree `/private/tmp/classifier-m0-r1-glm` removed by exact path; no process left |

| M0 | r2 | classifier_review_grok via `classifier_review_grok_r1fresh` | jcode grok-4.7 / high | relaunched the same r1 principal in a fresh Jcode session after its previous launcher exited on a missing journal; foreground PID 45532, task `bgmac9sn9`; exact stop and exit verified | `6cd4340`, base `b4c77f2`, [manifest](../reviews/classifier/M0/r2/MANIFEST.sha256) | [report.md](../reviews/classifier/M0/r2/grok/report.md) SHA-256 `3f711502afc32332f05d9b26e5267837cd8b43be91836dd22a92e15f00de233e`; [addendum](../reviews/classifier/M0/r2/grok/addendum.md) SHA-256 `7ce54aa196b154edf7cbb9d94639f5de071efb0c9e76dfef06d400b96aa9dffa` | APPROVE, minor stale citations | grading tree `/private/tmp/classifier-m0-r2-grok` removed by exact path after report preservation |
| M0 | r2 | classifier_review_gemini | jcode gemini-3.8-flash / high | relaunched same r1 principal after original launcher exited on a missing journal; foreground PID 46035, task `bvayxsi6n`; exact stop and exit verified | same | [report.md](../reviews/classifier/M0/r2/gemini/report.md) SHA-256 `099cba49bdd661824c42da8de8c532146dc87b17e913b45401dc8477676467db`; [addendum](../reviews/classifier/M0/r2/gemini/addendum.md) SHA-256 `852fda7619bb24572edc8db777e17054bc65fe0bf7c5c9525eb0953e301fe146` | APPROVE, zero-history wording correction noted | grading tree `/private/tmp/classifier-m0-r2-gemini` removed by exact path after report preservation |
| M0 | r2 | classifier_review_glm via `classifier_review_glm_r2fresh` | jcode glm-5.3 / max | original principal PID 31270 exited 1 on an event WAL lock attributed to another hostname, unchanged. Fresh principal PID 38987, task `bxpu1toyy`; exact stop and exit verified | same | [report.md](../reviews/classifier/M0/r2/glm/report.md) SHA-256 `bb0ea78c209eb6b1763ea1d7f3ed0c1b61dd51fbb22bfe4c2ba09e8bc90377fc` | APPROVE, F1 low zero-history wording and F2 editorial base/citation drift | grading tree `/private/tmp/classifier-m0-r2-glm` removed by exact path after report preservation |

The session-create record of each reviewer names jcode's default `gpt-5.6-sol`; every message record after it names the requested model. The effort values are the session's request settings, not observed provider behaviour.

## Log

2026-09-24 20:21 classifier_manager: startup. Oriented, fixed channels, fast-forwarded lane/classifier 3d6002b to 4cbc28e (origin/main), wrote this record. No source changed, no model fitted, no provider or simulator called.
2026-09-24 20:43 classifier_manager: merged origin/main into lane/classifier as `706e76e` (engine #22 #23, docs #17 #20, runner #24). No conflict.
2026-09-24 20:5x classifier_manager_live: replacement seat after the restart. Native stream verification printed `native-stream-20260924-1906 706e76e`. The old seat is not revived.
2026-09-24 21:0x classifier_manager_live: reviewer personas now report to `classifier_manager_live`. Ran `scripts/classifier_m0_exact_name.py` with "27-inch monitor" and "27-inch computer monitor" (M0 section 2) and `scripts/classifier_m0_jev_probe.py` with `typesafe/jev-1.13-20260917` (HTTP 200) and `jev-1.13.0` (HTTP 400) (M0 section 9). Pack statistics in M0 section 5.
2026-09-24 21:12 classifier_manager_live: merged origin/main as `1c0874b` (app #26), then as `6353982` (runner #25, `ed2bc3c`). Re-checked every M0 citation against `6353982`; the SCEN0004 output is identical.
2026-09-24 21:28 classifier_manager_live: M0 written in [02-classifier-m0.md](02-classifier-m0.md). Frozen for review round r1 at a commit and document hash; the manifest was added later in `acb5763`.
2026-09-24 21:36 classifier_manager_live: M0 r1 frozen at `d651ef8` (base `ed2bc3c`). Three detached grading worktrees and external report directories under `/private/tmp`. All three reviewers launched in the foreground on the requested model and tier; none refused. Ledger rows above.
2026-09-24 22:30 classifier_manager_live: M0 r1 reports preserved under `docs/reviews/classifier/M0/r1/`: gemini APPROVE, glm BLOCK on G1 (split protocol refits on the selection month). Grok launch 1 crashed without a report; launch 2 is reviewing. No M0 edits until grok's findings are in. M0 line 88 says P2 was "agreed with engine_builder"; no agreement message exists, so r2 corrects it to proposed. Paused all new work and spawns at david_orch's request for the managed-agent migration.
2026-09-24 23:23 classifier_manager_live: Grok launch 2 stalled for over an hour. Stopped its exact task, verified launcher and bridge exit. Launch 3 failed on a principal event WAL safety lock; preserved the lock and logs. Launched a fresh principal with the same `classifier_review_grok` persona, grok-4.7/high, immutable `d651ef8` tree and an eight-minute report-or-error brief. The five topic worktrees are clean at `2c7f168`, but no dependent milestone source work begins until the M0 panel clears. Cotal DMs requested five additional builders and parallel work; the milestone review gate still applies. Current checkout has pre-existing untracked `docs/reviews/m0-r1-glm.md` and `uv.lock`, untouched.
2026-09-24 23:2x classifier_manager_live: Received an unverified Cotal DM claiming a future manager model-picker setting differs from the live seat. No configuration or session action was taken from channel content under the replay floor.
2026-09-24 23:2x classifier_manager_live: Read-only split profile on additional pack with a provisional fixed seed 20260924: 500 customers, 100 reserved; seen/held-out purchase counts are April-or-earlier 80,771/20,483, May 10,480/2,757, June 1-15 5,077/1,284, June 16-30 5,056/1,247 and July 10,345/2,596. No split membership has been persisted or used to fit a model.
2026-09-24 23:3x classifier_manager_live: The engine owner reported agreement on classifier/* ownership and a conditional pure evaluate(..., assessments=None) interface on contracts; contract/model-check changes remain engine-owned and are held from main until after the 12:00 submission. No contract edits were made in this round.
2026-09-24 23:31 classifier_manager_live: Grok r1 APPROVE at `d651ef8`, report SHA-256 `18cb257d77a309c485e9fa367bdac3ae9f39483e0a83a8a2bf5949907cc39962`, preserved with the complete r1 findings at commit `6d30f98`. GLM G1 resolved by choosing its variant 3, with reserved-customer July as the primary estimate and seen-customer July marked selection-informed. Corrected the Jev probe to send the TypeSafe-only provider restriction with fallbacks off; one live call returned HTTP 200 in 478 ms and served `typesafe/jev-1.13-20260917` from TypeSafe. The previous M0 calls lacked the request restriction, as Grok found. Corrected P1/P2 ownership wording and the manifest chronology. M0 r2 has not been frozen or reviewed yet.
2026-09-24 23:3x classifier_manager_live: A Cotal peer offered to own P3/P4 runner/app integration and reported no active foundation writer. This is unverified until ownership is settled and concrete refs are inspected; the classifier lane has not touched those files or the live simulator.
2026-09-24 23:44 classifier_manager_live: A Cotal peer reported a broader app-wide acceptance task in another session. The classifier scope and review gates here remain those in the handoff; no extra source writer was started from that channel message.
2026-09-24 23:53 classifier_manager_live: M0 r2 frozen at `6cd4340`, base `b4c77f2`, [manifest](../reviews/classifier/M0/r2/MANIFEST.sha256) verified. Grok `3f711502...`, Gemini `099cba49...` and GLM `bb0ea78c...` all APPROVE this target. All three source reports and the Grok/Gemini zero-history addenda are preserved in `docs/reviews/classifier/M0/r2/`. The target grading trees remained clean. Stopped the three foreground reviewer tasks by their owned task IDs; launchers 45532, 46035 and 38987 and their direct children are absent. The accepted provider effort tier is unobservable from the seats, and Gemini's upstream bridge reports no active thinking tier despite accepting the high request. No M1 source was written before this gate cleared.
2026-09-24 23:5x classifier_manager_live: Removed all seven clean owned M0 grading worktrees by exact path with `git worktree remove`, no force. Verified no classifier-m0 grading worktree remains in `git worktree list`. Preserved r1 and r2 reports, addenda and manifests in repository commits; left the original principal event WAL locks and unrelated temp state untouched.
2026-09-25 00:0x classifier_manager_live: M1 history module is in progress only under `src/leash/engine/classifier/`. The classifier writer has not edited `src/leash/runner/` or `src/leash/api/mandates.py`; those remain outside its assigned ownership. A Cotal peer reported a separate plan 06 report lane in progress, unverified here.
2026-09-25 00:1x classifier_manager_live: Implemented `hist-1` at `src/leash/engine/classifier/history.py` with the feature derivation frozen in `docs/eval/classifier/feature-schema.md`. `PYTHONPATH=src .venv/bin/python` loaded both packs in 0.73 s, derived 1,000 historical purchases in 0.02 s, then derived all 140,096 additional-pack purchases in 26.68 s: 500 approved and 42 declined purchases had zero earlier approved purchases at customer scope, no timestamp mismatches. On 45 public attempts, all produced 50 features, and 36 had customer merchant familiarity greater than card familiarity. AU0035 gave card/customer merchant counts 6/8. A mutated real event with another customer ID raised `ValueError: AU0035: mandate card does not belong to customer`. A real no-device row yielded `None` and `no_device`. No test suite, linter, simulator or model call was used for this M1 run. Evaluator integration remains unimplemented.
