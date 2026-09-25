# Runner intent recovery

The first checkpoint added write-ahead storage, accepted-result recovery and bounded multi-mandate locks. The integration checkpoint below connects them to runner and app mutation paths. This branch is not a release candidate; live verification and independent review are pending.

## Write-ahead storage

`MutationJournal` stores private, versioned records under `data/intents/<mandate_id>/`. An intent binds its operation, method, path, payload, deadline and local context. Authorization mutations also bind a validated Event, Decision, pre-dispatch MandateState and run ID. A prepared or accepted intent blocks further dispatch for that mandate until its local recording is complete.

Files use mode0600. The file and directory metadata are synced before return. Intent files are ignored by git. An accepted response is checked against the request identity, outcome, source and payload before acceptance. Reopening an accepted record repeats those checks. A changed response is refused rather than treated as a completed write.

No remote request is made by this storage layer. Future callers must hold the affected mandate locks through preparation, dispatch, recording and completion. Remote reconciliation is still being implemented.

## Actual process-exit recovery exercise

The input was an existing accepted response from the earlier runner run `run_5b4c0b025db068a3`: authorization `AU10001-5db068a3`, CHF18.00, resolved to approve. Its original event, decision and pre-resolution state came from the saved decision file in the runner worktree. This historical run used the old smoke evaluator. It is a genuine simulator receipt, and it is not evidence of a new customer answer or a model-enabled approval.

An inline Python command used an isolated temporary directory and the real journal, state and history code:

1. Save the original pre-resolution state in the isolated state directory.
2. Prepare the resolution intent and reopen it through another journal instance. Further dispatch was refused while it remained prepared.
3. Store the actual saved accepted response in the journal. No API was called.
4. Start a separate Python process. It loads the accepted intent, calls the real `engine.state.record`, then exits abruptly with `os._exit(17)` before any history file or intent-completion write.
5. The parent observed exit17 and no history file. It called `records.recover_accepted` twice, then completed the journal.

Observed result: exactly one approval for CHF18.00, one history file, and no pending intent after reopening. The second recovery did not add spend or another history record. The original source record was unchanged. The temporary directory was removed.

This checks local recovery after state persistence. It does not exercise a lost simulator response or prove live reconciliation.

## Actual cross-process lock exercise

A separate Python process held `lock-b` using the real `flock` implementation. The parent requested the reversed input set `lock-b, lock-a` with a100 ms deadline. The helper sorted the set, acquired the earlier lock and then timed out after0.103 s on the held lock. The earlier lock was released during unwinding and was immediately acquirable again.

After the holder exited, the sorted unique set was acquired successfully. The child exited0 and all temporary files were removed. No simulator call was involved.

## Validation observations

An altered copy of the actual accepted response carried the wrong final status. `MutationJournal.accept` raised `UnresolvedMutation`; the persisted intent stayed prepared. A separate copy of an accepted journal file was altered to carry another authorization ID. Reopening it raised `UnresolvedMutation`. Intent permissions were0600, and `git check-ignore data/intents/private.json` matched the new ignore rule.

## Integration checkpoint

The runner now requires LEASH_POLICY_STORE before any remote startup. It verifies the supplied draft against its saved customer confirmation and resolves the customer's mandate set through owned_confirmations. Final evaluation and customer-approval rechecks load customer_mandates under the sorted lock set. The journal keeps the persistent mandate state separately from the customer-wide evaluation snapshot.

Submit and resolve now persist intent before dispatch and store the accepted response before local financial state. Tighten and revoke use the same coordinator. Revocation is returned as confirmed only after an authoritative GET reports revoked. Known mandate_widening refusals are recorded and the original error is re-raised; other uncertain writes stay open. A separate durable dispatched phase prevents reusing an intent for another POST.

Pending redelivery has a separate reconciliation budget from its expired automated deadline. The raw delivered Event remains in history; the exact effective policy used for evaluation is saved in the intent. New step-ups take their expiry from the actual accepted response. An already-expired platform window uses a read-only intent that cannot dispatch a resolution. Verified platform timeout declines are recorded as observed outcomes. They do not substitute for failed evaluation.

On a customer approve, the pending marker is removed from an in-memory checking copy so evaluate cannot return its old idempotent step_up result. Current permissions and customer-wide spend are evaluated again. A current decline is sent through resolve instead of approving. Customer declines are preserved. The sweeper also checks withdrawn permissions while a step-up is pending, and reserves its final three local-window seconds for timeout resolution.

These paths import successfully. The positive-owner remote paths have not run because live simulator calls remain paused. After #54 merged, the runner adopted _effective(remote, draft, edits, record). Mandate response metadata is preserved, and a tighten patch includes the full current effective rule set before appending its new restrictions, so confirmed global rules cannot be dropped from the payload.

## Further actual execution

The complete coordinator recovery path was exercised with the same genuine historical CHF18 receipt and original saved StepUp. A separate process again exited17 after state.record. Coordinator.record then completed one approval, one history file, the resolved step-up file with its run ID, and the journal. The original source files were not changed. No confirmation or ownership record was created for this exercise, and no new customer answer was submitted.

A real loopback Uvicorn server ran the changed create_app with an isolated empty policy store. Anonymous session, draft-list, mandate-list and pending reads returned401. After an actual local login, each owned list returned200 and an empty array. Unowned mandate detail, history and decision detail returned404; an unowned revoke also returned404 before simulator access. Wallet HTML returned200. Logout returned204 and the next session read returned401. The simulator settings cache stayed empty. The owned server exited and the temporary store was removed.

The CLI without LEASH_POLICY_STORE exited1 with `runner requires LEASH_POLICY_STORE with the customer confirmations`, before run_progress or start_run. The full public replay still produced45 rows:11 approve,32 decline and2 step_up. Local extraction plus evaluation was p50 0.234ms and p99/max0.388ms.

## Remaining gates

The new journal dispatch/reconciliation calls, current-policy refresh, genuine customer approval, tightening and revocation need live execution after credential rotation. Positive-owner HTTP behavior has not been manufactured with invented confirmations. Current confirmations were not found in the inspected runner, runner-live or policy worktrees. The legacy raw decision receipts are retained as historical evidence only.

Concurrent policy confirmation can also supersede a mandate. Its write path is owned by the policy lane and is not covered by this branch's tighten/revoke coordination yet. That ordering needs agreement before claiming every app permission mutation is serialized. Model startup, full absolute-budget composition and the classifier release holds remain separate gates.

Live verification remains paused for challenge-key rotation. No test suite or linter was run.

## Customer guard and global-policy integration

The coordinator now takes a customer-scoped flock before enumerating owned mandates, then takes their sorted locks and rechecks the set. The initial immutable confirmation lookup only identifies the customer. The guard remains held through accepted writes and recovery. Lock filenames use SHA-256 of the UTF-8 customer value, so valid Unicode names fit the filesystem. The policy confirmation lane will use this helper after the runner change merges.

A separate process held the customer guard with an empty owned-mandate set. A different customer acquired its own guard immediately; the same customer timed out after0.104s under a0.100s allowance. After the child exited0, an80-character Unicode customer acquired a guard and empty mandate set successfully. Every generated lock filename was69 bytes and mode0600. No confirmation was created.

Actual global-policy HTTP calls on the rebased app passed anonymous401, first GET version0, PUT200/version1, exact read-back, stale409 and duplicate-control422. A second logged-in customer saw empty version0. No simulator settings were loaded.

That exercise also found an upstream defect: an80-character Unicode username was accepted by login, but GET /global-policy returned500. Its quoted filename was725 bytes and GlobalPolicyStore.read raised macOS OSError errno63. The policy owner has the finding; this branch does not change global-policy storage. The healthy preferences were written only in an isolated temporary store, and that store and the owned server were removed.
