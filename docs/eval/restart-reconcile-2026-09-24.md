# Step-up expiry across restart

Observed on 2026-09-24 during plan 05 live verification, based on main `8cb591a`. The original runner failure occurred on `b3b8184`.

- Scenario: `SCEN0135`
- Run: `run_9328cc3adcf476d9`
- Mandate: `TMa575eab935b50a33`
- Customer answers sent: none
- Simulator reset: not called

## Failure

The real engine returned `step_up` with `no_card_history` for `AU10371-dcf476d9`. The simulator accepted it at approximately 20:13:58 UTC. Its authoritative expiry was 20:15:58 UTC; the local sweep deadline was five seconds earlier.

The worker was stopped at a persisted pending-state checkpoint while its driver moved from a bounded background task to a persistent terminal. On restart, it loaded the pending authorization without resubmitting the original decision. Viseca had already expired the step-up. The sweeper's `/resolve` call received HTTP 409 `authorization_not_pending` and stopped. The loop surfaced `StepUpError: step-up sweeper failed; pending step-ups are no longer timed out`.

The restarted loop had accepted a second step-up, `AU10372-dcf476d9`, before it observed the sweeper failure. That step-up also expired while the worker was stopped for diagnosis.

`GET /v1/authorizations/{id}` returned HTTP 404. The supported `GET /v1/authorizations` returned authoritative rows. Its `run_id` query parameter restricts the list to the run.

## Repair

The sweeper handles only the explicit 409 `authorization_not_pending` response by reading `GET /v1/authorizations?run_id=<run>`. It requires:

- Exactly one row matching the pending authorization ID.
- Matching run ID and a complete authorization equal to the stored event, including mandate identity.
- Status `declined`, decision source `timeout`, and reason `step_up_expired`, in both the row and its decision.
- A timezone-aware `finalized_at` between the stored expiry and the present.

It records the observed decline through `record_accepted` and marks the step-up file resolved. The raw platform row is retained as acceptance evidence. The local Decision maps the platform's `step_up_expired` to the existing `step_up_timeout` reason and labels its origin `simulator-step-up-expiry`. Its message and evidence come from the platform.

There is no second `/resolve` call. A missing or ambiguous row, conflicting identity, different outcome, malformed timestamp, failed read, or another API error still raises. This repair does not reconcile unrecorded approvals, customer answers sent by another process, or the separate accepted-submit-before-persistence gap.

The CLI passes the known run ID when starting the sweeper. No `loop.py` decision logic changes.

## Live verification

Through the existing settings loader, set its `.env` path to the repository's ignored credential file, then run:

```python
book = StepUpBook()
book.sweep("TMa575eab935b50a33", "run_9328cc3adcf476d9")
```

Observed sequence for each of the two authorizations:

1. POST `/resolve`: HTTP 409 `authorization_not_pending`.
2. GET `/v1/authorizations?run_id=run_9328cc3adcf476d9`: HTTP 200.
3. Verified timeout decline written to local decision history and state.
4. Pending file marked resolved.

| Authorization | Platform status | Source | Platform reason | Platform finalized_at |
| --- | --- | --- | --- | --- |
| AU10371-dcf476d9 | declined | timeout | step_up_expired | 2026-09-24T20:16:14.383461Z |
| AU10372-dcf476d9 | declined | timeout | step_up_expired | 2026-09-24T20:22:38.444001Z |

Before: two pending, zero approvals. After: zero pending, zero approvals, two declines. The saved resolution records retain the platform fields above. A second `sweep` returned `[]` and made no API calls or duplicate records.

No customer approval or rejection was synthesized. This verifies the recovery of these expired step-ups; it does not claim completion of the remaining scenario attempts.
