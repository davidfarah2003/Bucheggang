# Purchase rechecks

The local purchase path previously returned an idempotent result before reading the mandate's current status. Its Wallet answer path also copied an approval into the pending decision without re-evaluating current permissions or spending state.

## Changes

- Every `buy`, including a repeated key, reads the mandate status under the customer and mandate locks before returning a result.
- New local step-ups retain the validated agent-form facts used for their first decision. Approval rechecks use those facts with the current effective policy and state.
- A hard failure found at recheck produces a decline. A new uncertainty reason leaves the request pending and returns an error because the customer was not asked about that reason.
- The response window is checked again under the lock. Timeout resolution also verifies that the window has expired.
- The answer route returns the recorded decision, including a policy decline following a requested approval.
- Pending rechecks with period rules reject newer projected approvals whose timestamps are after the original request. This applies to local and simulator rechecks. The original event timestamp cannot be advanced without changing the purchase and its history binding; the request must be replaced to use a newer spending window.

Existing local pending records without their original facts cannot be approved through this path. They can still be declined or reach their timeout. The implementation does not reconstruct missing facts or silently replace them with a new extraction.

## Observed checks

The production recheck helper was exercised on the first pending purchase produced by replaying the public inputs with agent-form facts. These were offline evaluations, with no customer answer or persistent mandate-state write.

| Input to the recheck | Observed result |
| :--- | :--- |
| Unchanged purchase and permissions | `step_up`, `new_device` |
| Revoked mandate | `decline`, `mandate_revoked` |
| Tightened amount cap | `decline`, `amount_over_limit` |
| A later public purchase projected as approved, with a period rule | Both local and simulator rechecks rejected the stale pending approval |

The original pending state was unchanged by each recheck. Simulator and provider credential accessor counts remained zero. The complete five-policy public replay still produced 45 rows: 11 approve, 32 decline and 2 step_up, with exact decision and reason-code parity against the committed baseline.

After the newer classifier integration reached main, the current history-only callback was replayed across all 45 inputs again. Both pending purchases were rechecked unchanged and with revoked mandates: unchanged requests stayed pending, revoked mandates declined, and their original state remained unchanged.

A disposable Uvicorn instance was also exercised through real HTTP: `/app/` returned 200; anonymous session, pending-step-up and global-policy reads returned 401; anonymous agent-session creation and an answer request for an unknown purchase returned 401; account creation with a wrong Origin returned 403. No account, pairing or purchase record was created. The first startup probe used an unavailable FastAPI helper; switching the probe to the application's existing startup-hook API allowed the exercise to run. The owned server stopped and its temporary store was removed.

The fresh mandate read on repeated `buy`, an authenticated HTTP answer and recovery after interrupted local writes still require live lifecycle verification. These observations do not establish a complete customer Wallet journey. No test suite or linter was run.
