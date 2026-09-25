# Local purchase recording recovery

Local purchases previously called `records.recover_accepted` without first saving its inputs. A process exit after the spending-state write could leave a purchase key without an authorization ID. An interrupted resolution could leave the pending-question file unresolved after the final decision had already changed state.

## Implementation

The purchase file now saves the evaluated decision, pre-write state, acceptance time and original pending-question data before state or history changes. A resolution saves the checked result in the pending file before its state transition. Both use a `recording` field, removed after the other writes finish.

The coordinator completes an unfinished recording under the existing customer and mandate locks. The Wallet sweeper also discovers unfinished purchase records, including ones whose pending-question file has not been created yet. Conflicting identities and ambiguous ordering raise errors. Recovery preserves the decision and expiry; it does not call a model, repeat evaluation or supply a customer answer.

A key without a saved evaluated result remains failed. Older interrupted writes without the new recording inputs cannot be reconstructed by this change. Local records remain separate from simulator mutation intents and contain no invented simulator receipt.

## Observed execution

The measured checkout was based on `a92b4d07e3b2a441ccaccf7e801a98a2886bce95`. The [JSON evidence](local-purchase-recovery-2026-09-25.json) includes SHA-256 hashes of both changed runtime files.

An inline `LEASH_ENABLE_MODELS=0 uv run --no-sync python` command evaluated public inputs with the production engine and exercised the recording helpers in isolated storage. Facts submitted to this local-storage exercise were labelled `agent_form`. Earlier approvals were offline projections, with no customer confirmation or simulator acceptance claimed.

Each child process ran the real recording code. A Python trace hook called `os._exit(17)` immediately after `engine.state.record` returned, or `os._exit(18)` immediately after `records.recover_accepted` returned. The parent then called `recover_local_purchases` twice under the mandate lock.

| Evaluated outcome | Interruption points exercised | Observed recovery |
| :--- | :--- | :--- |
| Approve | State write and history write | One new approval, one history file, completed purchase key; second recovery changed nothing |
| Step-up | State write and history write | One pending question, one history file, completed purchase key; original facts and expiry retained |
| Timeout decline | State write and history write | One final decline, no new approval, no pending question; initial and resolution history files retained |

The timeout exercise used the pending records from the preceding run after their original response windows expired. It did not shorten or replace their expiry and supplied no customer answer. All six child processes exited at the requested boundary. Each recovered state matched the engine's intended transition exactly.

Wrong mandate and authorization identities raised `PurchaseFailed` before any stored JSON changed. Recovery left an unevaluated key unchanged with a null authorization ID. Simulator and OpenRouter credential accessor counts remained zero throughout these exercises.

The complete `scripts/replay.py --all` command from [run-replay.md](../run-replay.md), with its output directed to private evidence, completed 45 purchases: 11 approve, 32 decline and 2 step_up. Every decision and reason code matched `docs/eval/replay-2026-09-25-all.csv`. The initial comparison command named a nonexistent baseline file and raised `FileNotFoundError`; correcting that path completed the comparison without rerunning or changing the application.

Private command outputs and isolated records are retained under `.cotal/local-recording-20260925T124854874293/`. No test suite or linter was run.

## Human verification remains incomplete

The separate real MCP and Wallet attempt ran source `feb1ed7501ce98eae64c91b0560d146010b3b524`. Its `connect` call ended with `PairingTimeout`. No purchase was submitted, and the driver made no Wallet mutation or customer answer. The API stopped at its configured 900-second limit. Its store retains one pairing record and no account, confirmed policy or purchase.

These storage exercises do not verify an authenticated Wallet approval, repeated `buy` after revocation, or recovery through the complete owned coordinator and HTTP lifecycle. Those checks still require a real customer pairing and policy confirmation. No replacement live session was started after the timeout.
