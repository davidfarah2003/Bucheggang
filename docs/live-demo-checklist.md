# Live demo checklist

Recorded state: 25 September 2026, before the morning dry run. Unchecked items below have no complete observed result yet. This checklist does not certify the application as finished.

## Evidence already available

| Check | Evidence | Limit |
| --- | --- | --- |
| All 45 public purchases through real extraction and evaluation | [Current replay](eval/replay-2026-09-25-all.csv), [report](eval/report.md) | Offline sequential policies, no customer answers or simulator submission |
| Deterministic field extraction | [Report field table](eval/report.md#deterministic-extraction-corpus) | Annotated fields only |
| Original live themes | [SCEN0101](eval/live-SCEN0101-2026-09-24.md), [SCEN0135](eval/live-SCEN0135-2026-09-24.md), [SCEN0130](eval/live-SCEN0130-2026-09-24.md), [SCEN0106](eval/live-SCEN0106-2026-09-24.md), [SCEN0122](eval/live-SCEN0122-2026-09-24.md) | Four later runs had no approvals; SCEN0101's approval used curl |
| Restart with an unanswered step-up | [SCEN0130](eval/live-SCEN0130-2026-09-24.md) | Zero approved spend in that run |
| Platform expiry while worker was down | [Restart reconciliation](eval/restart-reconcile-2026-09-24.md) | Strictly verified timeout declines only |
| MCP proposal, status and summary with a real mandate | [MCP transcript](samples/mcp-transcript-scen0002.md) | Does not establish an actual human Wallet step-up answer |
| Current-checkout paired Wallet and MCP rehearsal | [Local paired rehearsal](eval/takeover-local-rehearsal-2026-09-25.md) | Disposable store; draft rejected without a simulator mandate or human purchase answer |
| Full local user flow with models on, recorded | [Demo video](https://github.com/davidfarah2003/Bucheggang/releases/download/demo-2026-09-25/leash-user-flow.mp4) (also `docs/demo/leash-user-flow.mp4`), produced by `scripts/record_demo.py` driving the real Wallet while `scripts/flow_sim.py --manual` runs the agent over MCP | Local purchases only; the step-up answer comes from a scripted browser tap, not a person |

## Before a live run

- [ ] Record the exact application commit and any uncommitted changes. Use one checkout for the API, MCP server and worker, with the same policy store and runtime data directory.
- [ ] Confirm with the team that the simulator slot is free. A fresh confirmation supersedes the team's previous mandate. Do not reset the team or reuse an old run as the new demo.
- [ ] Have the customer at the Wallet before starting a scenario that may ask a question. Do not invent an answer or send an approval from a script.
- [ ] Start the Wallet following [run-wallet.md](run-wallet.md) and the external shopping agent following [mcp-client.md](mcp-client.md). Keep credentials out of terminals captured for the presentation.
- [ ] Read the live bootstrap through the runner client. Record the currently available scenario IDs and deadline windows. Public offline IDs are not live team IDs.
- [ ] Select a live scenario whose purchase purpose matches the actual confirmed instruction. Do not copy the shoes instruction into a grocery scenario to force a chosen result.
- [ ] Runtime models are on for the local purchase demo through `scripts/wallet.sh` and `scripts/mcp-stdio.sh` (behavioural threshold 0.498, Jev probability-sum tolerance 0.015). Record the model manifest and threshold in use. Simulator runs through the runner keep the model setting they are started with; record it.

## Customer flow

For every item, record the command or UI action, HTTP status, authorization or draft ID, and the file holding the observed response. Mark a failure as a failure before changing code.

- [ ] Without login, customer API routes return 401. Logging in creates a session; logging out invalidates it.
- [ ] The Wallet API is served on 127.0.0.1 only and never through the tunnel. Only the MCP server goes through the tunnel.
- [ ] The agent calls the real MCP authoring and proposal tools. Read-back through `get_policy_summary` matches the proposed instruction and customer-readable rules. `get_policy_status` says pending.
- [ ] At `/app/?draft_id=<id>`, the customer sees the saved rules, examples and unanswered questions. The confirm action submits the saved version and hash. An attempt using an obsolete version or hash returns 409 and creates no simulator mandate.
- [ ] The customer answers the open questions and confirms in the Wallet. Record the actual submitted choices. The mandate ID displayed by the app matches the confirmed MCP status and live simulator record.
- [ ] Launch the real engine worker with that confirmed draft and mandate. Use `--evaluate engine`, never a smoke evaluator. Save the run ID and log.
- [ ] For an ordinary approval, verify the simulator accepted the exact authorization, the app shows its checks and the approved amount is counted once. If the system asks because card history is absent, record that result; do not claim an autonomous approval.
- [ ] For a step-up, compare the app's timer with `StepUp.expires_at`. The customer presses the answer. Verify the answer route, authoritative simulator outcome, disappearance from pending and recorded state change. Automated event deadlines and the human answer window are distinct.
- [ ] Open history and the decision detail. The displayed action, reasons, event, checks and state before/after match the accepted record. Check an unknown ID and an ID outside the logged-in customer's mandate ownership.
- [ ] At a 400 px viewport, read the draft, pending question, mandate and decision detail. Check wrapping and horizontal overflow. Use real backend data; label screenshots as captures from the completed run.
- [ ] Where the selected live scenario contains merchant instructions, show the exact supplied text, the injection flag and the resulting checks. An offline annotated example may explain the feature, but cannot stand in for this live step.

## Policy changes and recovery

- [ ] Tighten the active mandate through the Wallet and read it back. Confirm the effective policy and revision. If the simulator rejects the change, preserve the error and do not claim that tightening succeeded.
- [ ] Verify a purchase already being evaluated cannot be approved against the old policy after tightening has been acknowledged. This requires the shared-lock and effective-policy integration; it is not established by the earlier runs.
- [ ] Revoke through the Wallet, read back the revoked status and verify queued purchases decline with `mandate_revoked`. Verify pending step-ups cannot approve after revocation.
- [ ] Restart with nonzero approved spend and verify exactly-once state recovery. The recorded zero-approval pending restart alone does not cover this.
- [ ] Check that a missing dependency, failed provider call or expired automated deadline raises a named error. Do not introduce a fabricated business decision or alternate provider as a substitute.

## Finish and repeat

- [ ] Read the run and authorization list through the runner client. Reconcile generated, delivered, finalized, rejected and local-handled counts. Record platform-only outcomes separately.
- [ ] Confirm no requests remain pending. Stop only the worker, server and tunnel started for this run. Preserve logs and records.
- [ ] Repeat the complete flow with a fresh mandate and new run. Compare actual outcomes rather than declaring the second run equivalent in advance.
- [ ] Reconcile independent labels with a human, regenerate the report and use only supported figures in the pitch. Keep local-function latency separate from network or customer latency.
- [ ] Rishabh prepares the pitch and presentation assets. The expert slot and submission still require a human. No screenshot or recording replaces the live demo.

## Current blockers and deferred scope

A fresh Wallet step-up run needs the reserved window and an actual customer at the Wallet ready to answer; a recorded curl approval from an earlier run is not a Wallet answer. Shared model contracts and pure composition merged in #47. The [real-provider exercise](eval/jev-public-2026-09-25.md) stopped twice on probability sums off by the provider's two-decimal rounding; the contract now accepts a 0.015 tolerance without renormalizing, and the local purchase path runs both models with threshold 0.498 (Log in plans/01-policy-confirmation.md, 2026-09-25 10:35). Model-enabled runner startup against the simulator has not been exercised live.

Processing failures raise errors after #50; timeout substitute decisions were removed. Since #58 (eb78312), runner submissions/resolutions and app tightening/revocation use durable intents, customer-first locks and current-policy rechecks. Confirmation and account-wide policy writes take the same customer lock since #76 (94d1720). These paths have local checks; a live Wallet confirmation and step-up answer under the merged code, and complete live end-to-end latency, remain unverified.

Account-wide policy storage and read-only Wallet disclosure are merged in #54 and #66. Account/session/pairing routes and MCP identity binding are merged in #73 and #76, and the Wallet identity screens in #82. Local HTTP and browser checks do not establish a completed human pairing, confirmation or purchase answer. Built-in shopping-provider execution remains deferred product work; the MCP purchase tools `buy`, `get_purchase_status` and `wait_for_purchase` are live for local purchases. No human confirmation or answer is supplied by this checklist.
