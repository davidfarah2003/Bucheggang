# 06 Evaluation and demo

- Status: report generator merged in #38 and exercised. Labels remain provisional; human Wallet E2E, two full live dry runs and pitch/submission work remain open. The 45-input real Jev exercise has not passed.
- Owner: everyone; Rishabh drives the pitch
- Channel: `team.zurichbuchegg` (spine)
- Papers: [Selective Conformal Risk Control](../papers/2512.12844v2.pdf) (report the two numbers: how often the system decides alone, and how often it is wrong when it does; its guarantees need more labelled, exchangeable data than 45 attempts, so no guarantee is claimed), [CaMeL](../papers/2503.18813v2.pdf) (report lost utility next to blocked attacks)
- Event: jury criteria and slots in [primary-findings.json](../research/2026-09-24/primary-findings.json) (JURY, SUBMIT); comparable projects in [wallet-control-research.html](../research/2026-09-24/wallet-control-research.html)

## Goal

Labels to check decisions against, a report the pitch can quote, and a demo that runs the same way twice.

## Labels

`docs/eval/labels.csv`: one row per public attempt, `authorization_id, expected, reason, notes`. Two people label independently tonight from `purchase_attempts.csv`, `purchase_attempt_items.csv`, `merchants.csv` and the scenario instruction, then reconcile disagreements in a third column. The organizers publish no answer key; these are our labels and the report says so. Known judgement calls to settle while labelling: AU0016 (return terms missing), the SCEN0001 split order, "a shop I use regularly" for an unseen merchant.

## Report

`docs/eval/report.md`, produced by `scripts/report.py` from `scripts/replay.py` output:

- decisions per scenario: approve, decline, step_up counts;
- agreement with labels, with every disagreement listed and explained;
- autonomy rate (share decided without a step-up) and error rate on those, per scenario;
- extract lane's corpus table (pass 1; there is no model pass, docs/idea Decision pipeline);
- latency p50 and p99 for offline extraction/evaluation and the available live measurements; complete live end-to-end timing remains unavailable until both ends are recorded;
- attacks in SCEN0004 stopped or escalated, and ordinary purchases in SCEN0000 to SCEN0002 approved without a question.

Numbers come from files in `docs/eval/`; the report links to them. No number appears in the pitch that is not in the report. [run-report.md](../run-report.md) documents explicit inputs, labels-pending operation and measurement limits. [live-demo-checklist.md](../live-demo-checklist.md) separates observed evidence from the customer flow still to be exercised.

## Demo script (four minutes of content, cut to the slot)

This is the intended sequence. The public attempt IDs below identify offline examples, not selectable live purchases. Use the live bootstrap's team scenario IDs, the customer's actual choices and the resulting decisions. Do not announce an approval or fixed latency before observing it.

1. The external shopping agent proposes a `SCEN0002` draft through MCP and opens the Wallet at `/app/?draft_id=<id>`. Review the saved draft and examples, answer the return-terms question, and confirm. Show the `mandate_id` the agent receives. The Wallet also works directly without any built-in Harness.
2. Show an ordinary purchase's actual outcome and judge panel. Quote the measured timing. The early `SCEN0002` approval is an offline reference; missing live-card history may cause a step-up.
3. A manipulated purchase from `SCEN0004`: injected merchant text is shown verbatim on the panel, flagged, and the decision is driven by the rule it tried to override.
4. A `step_up` on the phone: AU0016, return terms not stated; the customer rejects; the next attempt at the same merchant is declined as a re-quote.
5. Revoke on the policy page; the following purchase is declined with `mandate_revoked`.
6. Close on the report's two numbers per scenario.

Assets: `docs/screens/` screenshots of the mobile-first Wallet demo, the agent-side terminal transcript from plan 01 step 7, a 6-slide deck in `docs/pitch/`. Harness screenshots are later product work.

## Steps

1. Tonight: labels by two people, reconciled.
2. Friday 09:00: `scripts/report.py` and the first report from the offline replay.
3. Friday 10:30: full live dry run. The demo is live; there is no recorded fallback (AGENTS.md section 6).
4. Friday 11:00: deck; book the expert-round slot before 12:00.
5. After the expert round: fold Q&A findings; final submission 17:30.

## How we check it works

- The demo runs twice in a row against the live API with the same outcomes.
- The report's numbers match the replay CSV it links.
- Nobody in the room can find a scenario ID in `src/`.

## Decisions

- Keep the expert pitch within its 1-minute slot and show a concise live flow. Screenshots from a real run may support the pitch deck, but do not replace the live demo.

## Log

(one line per finished task: date time, who, what, how it was tried, sha)

2026-09-24 20:32 oskar1: clarified that the current demo uses an external shopping agent through MCP and opens the standalone Wallet with the saved draft ID; a built-in Harness is later work.

2026-09-25 00:09 david_orch: report generator, evidence-linked report and live checklist implemented @3852542. `uv run python scripts/replay.py --all` with the five explicit drafts documented in run-replay.md wrote the new 45-row replay: 11 approve, 32 decline, 2 step_up; local total p50 0.248 ms, p99/max 0.462 ms. `uv run python scripts/report.py` read that replay plus four live CSVs (50 finalized, 49 local outcomes, one platform-only timeout), measured 145/145 annotated extraction fields and 7/7 authored adversarial instruction recall, and wrote docs/eval/report.md with labels pending. Explicit provisional labels-b @4e15565 exercised all labelled calculations and disagreement rows in an ignored scratch report; no provisional label metrics were put in the published report. Missing explicit labels and mismatched label/replay mode exited 1; omitted --labels-mode and existing output exited 2; the existing report hash was unchanged. labels-a @c3afec9 initially failed on its trailing comment row, reported to its owner; no input repair or fallback was applied by the reporter. No simulator request, customer answer, test suite or linter. Human reconciliation, full Wallet E2E, complete live end-to-end timing and repeated live demo remain open. Review pending.

2026-09-25 david_orch: real Jev exercise on core71f119c and standalone producer0940fd7 with evaluation-only CatBoost e4815c5. Initial driver exited1 after6 composed inputs when request7 failed activity probability normalization; one separate diagnostic request passed the unchanged parser. Fresh recorded driver exited1 after35 composed inputs when request36 returned spend probabilities unusual0.14, ordinary0.80 and unclear0.05, sum0.99. Total44 actual provider requests; neither45-input batch completed. No retries within batches, normalized probabilities, substitute decisions, simulator requests or customer answers. Full model-off scripts/replay.py --all still returned45 rows11/32/2, local p50 total0.239ms p99/max0.421ms. Evidence: docs/eval/jev-public-2026-09-25.md and linked partial CSVs/JSON. Strict validation and the model-enabled release gate remain.
2026-09-25 oskar7: regenerated `docs/eval/replay-2026-09-25-all.csv` from the five explicit draft paths in `docs/run-replay.md` on main ec5bb96; `uv run python scripts/replay.py --all --policy SCEN0000=docs/eval/replay-policies/SCEN0000.json --policy SCEN0001=docs/eval/replay-policies/SCEN0001.json --policy SCEN0002=docs/samples/scen0002_draft.json --policy SCEN0003=docs/eval/replay-policies/SCEN0003.json --policy SCEN0004=docs/eval/replay-policies/SCEN0004.json --output docs/eval/replay-2026-09-25-all.csv` exited 0: 45 rows, 11 approve, 32 decline, 2 step_up. Decisions match the prior CSV; AU0040 reasons are now `item_mismatch|injected_instructions` instead of `item_mismatch|unrequested_item|injected_instructions`, and SCEN0004 draft hash is now `3a83840408674d175a5ace5a629983fd0f08e9162bdba814d6d17e36fc603870` instead of `743b2c4ada5e80acdd0eb1248bcfc6f96a0bb011cc3173cb187058158552a7ce` after the `facts.is_addon = false` rule was removed in policy @72e7b18. No simulator call, customer answer or label choice.

2026-09-25 david_orch: independent Chrome exercise of frozen app source1c5d61c used the actual Uvicorn API and disposable accounts/store. Registration201, logout then session401, wrong-password error, correct-password login, persistent session after reload, empty Connected agents and Wallet/Activity views, unknown pairing404 and Shop escape all observed. Measured viewport/document widths390/390 and320/320; browser storage empty. Probe corrections and scope in docs/eval/identity-browser-2026-09-25.md. Owned tab/server closed, task exited0, temporary store removal verified. No pairing approval, mandate confirmation, purchase answer, provider or simulator request.

2026-09-25 11:05 david_main: demo video recorded. app/demo-stage.html embeds the real Wallet in a phone frame beside a mirrored agent chat; scripts/record_demo.py drives the Wallet with Playwright while scripts/flow_sim.py --manual runs the agent over MCP with the models on. Take 4 on a wiped store: register, connect approved, propose, confirm, buy at Alpine Basket step_up (new_device, model_history_uncertain) answered in the Wallet as approve, buy at Fresh Corner Market decline (unfamiliar_merchant), activity and the pipeline tab with the CatBoost and Jev bars. Output docs/demo/leash-user-flow.mp4 58 s at 1600x900 30 fps, gif 800 px. The step-up answer in the recording is a scripted browser tap, not a person. Commits ead3e8e, 33e8b45.
