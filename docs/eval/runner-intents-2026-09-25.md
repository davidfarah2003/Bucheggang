# Runner intent recovery

The first checkpoint adds write-ahead storage, accepted-result recovery and bounded multi-mandate locks. Dispatch does not use these helpers yet. This checkpoint is not a completed runner integration or a release candidate.

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

## Remaining integration

The runner still needs to use the journal before every submit and resolve, reconcile ambiguous writes from authoritative API reads, and restore pending step-up records after restart. App tightening and revocation also need journaled writes under the same locks. Final evaluation must reload effective policy and the customer-wide state under sorted owned-mandate locks, including the customer-approval path. No current dispatch or customer endpoint claims those changes are active.

Live verification remains paused for challenge-key rotation. No test suite or linter was run.
