# 06 Evaluation and demo

- Status: draft
- Owner: everyone; the third teammate drives the pitch
- Channel: `team.zurichbuchegg` (spine)
- Papers: [Selective Conformal Risk Control](../papers/2512.12844v2.pdf) (report the two numbers: how often the system decides alone, and how often it is wrong when it does; its guarantees need more labelled, exchangeable data than 45 attempts, so no guarantee is claimed), [CaMeL](../papers/2503.18813v2.pdf) (report lost utility next to blocked attacks)
- Event: jury criteria and slots in [primary-findings.json](../research/2026-09-24/primary-findings.json) (JURY, SUBMIT); comparable projects in [wallet-control-research.html](../research/2026-09-24/wallet-control-research.html)

## Goal

Labels to test against, a report the pitch can quote, and a demo that runs the same way twice.

## Labels

`docs/eval/labels.csv`: one row per public attempt, `authorization_id, expected, reason, notes`. Two people label independently tonight from `purchase_attempts.csv`, `purchase_attempt_items.csv`, `merchants.csv` and the scenario instruction, then reconcile disagreements in a third column. The organizers publish no answer key; these are our labels and the report says so. Known judgement calls to settle while labelling: AU0016 (return terms missing), the SCEN0001 split order, "a shop I use regularly" for an unseen merchant.

## Report

`docs/eval/report.md`, produced by `scripts/report.py` from `scripts/replay.py` output:

- decisions per scenario: approve, decline, step_up counts;
- agreement with labels, with every disagreement listed and explained;
- autonomy rate (share decided without a step-up) and error rate on those, per scenario;
- extract lane's corpus table (pass 1, pass 1 plus 2);
- latency p50 and p99 for extract, evaluate and end-to-end, from the fake-simulator run and the live run;
- attacks in SCEN0004 stopped or escalated, and ordinary purchases in SCEN0000 to SCEN0002 approved without a question.

Numbers come from files in `docs/eval/`; the report links to them. No number appears in the pitch that is not in the report.

## Demo script (four minutes of content, cut to the slot)

1. Confirmation: the `SCEN0002` sentence becomes rules and four example purchases; the customer answers the return-terms question; Confirm. Show the `mandate_id` the agent receives and nothing else.
2. Ordinary purchase approved with no question (an early `SCEN0002` attempt). Show the judge panel: every check passed, 6 ms.
3. A manipulated purchase from `SCEN0004`: injected merchant text is shown verbatim on the panel, flagged, and the decision is driven by the rule it tried to override.
4. A `step_up` on the phone: AU0016, return terms not stated; the customer rejects; the next attempt at the same merchant is declined as a re-quote.
5. Revoke on the policy page; the following purchase is declined with `mandate_revoked`.
6. Close on the report's two numbers per scenario.

Assets: `docs/screens/` screenshots, the agent-side terminal transcript from plan 01 step 7, a 6-slide deck in `docs/pitch/`.

## Steps

1. Tonight: labels by two people, reconciled.
2. Thursday 09:00: `scripts/report.py` and the first report from the offline replay.
3. Thursday 10:30: full live dry run, recorded (`asciinema` or screen recording) as the fallback if the API is slow during the slot.
4. Thursday 11:00: deck; book the expert-round slot before 12:00.
5. After the expert round: fold Q&A findings; final submission 17:30.

## How we check it works

- The demo runs twice in a row against the live API, or once live and once from the recording, with the same outcomes.
- The report's numbers match the replay CSV it links.
- Nobody in the room can find a scenario ID in `src/`.

## Open questions

- Which of the two pitches (1 minute expert, 2 minutes main) gets the live demo, and which uses the recording? Proposed: recording for the expert round, live for the main round.

## Log

(one line per finished task: date time, who, what, test, sha)
