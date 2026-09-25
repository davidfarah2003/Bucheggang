# Runner deadline verification

This change removes fixed-output smoke evaluators and replacement payment decisions after extraction or evaluation failure. It does not enable models or close the remaining runner state-consistency work.

## Runtime changes

- The CLI accepts only `--evaluate engine`, which is also the default. The two smoke functions are removed.
- Extraction returns validated facts or raises `ProcessingTimeout`. A failed extraction cannot become `facts=None`.
- Evaluation returns its actual Decision or raises. An expired guard cannot become `step_up` or `decline`.
- Each HTTP call uses a total asynchronous budget covering client setup, connection, response headers and response-body reading. The default is 30 seconds; a supplied absolute deadline can shorten it. There is one request and no retry.
- Decision submission requires the event deadline. Customer resolution uses `StepUp.expires_at`; timeout resolution uses the remaining five-second expiry margin. The automated event deadline is never reused for a human answer.
- A restarted sweeper already beyond that margin reads the authoritative authorization record directly. It records only the verified platform timeout decline accepted by the existing reconciliation checks.
- `settings.load_openrouter()` returns only the provider key in a dataclass whose representation hides it. It is not called by model-off startup. A missing provider configuration raises.

## Actual execution

The normal offline command was run in the deadline worktree:

```sh
uv run python scripts/replay.py --all \
  --policy SCEN0000=docs/eval/replay-policies/SCEN0000.json \
  --policy SCEN0001=docs/eval/replay-policies/SCEN0001.json \
  --policy SCEN0002=docs/samples/scen0002_draft.json \
  --policy SCEN0003=docs/eval/replay-policies/SCEN0003.json \
  --policy SCEN0004=docs/eval/replay-policies/SCEN0004.json \
  --output .cotal/replay-deadlines.csv
```

It exited 0:

| Scenario | Approve | Decline | Step up |
| --- | ---: | ---: | ---: |
| SCEN0000 | 1 | 0 | 0 |
| SCEN0001 | 5 | 5 | 0 |
| SCEN0002 | 1 | 11 | 0 |
| SCEN0003 | 4 | 6 | 1 |
| SCEN0004 | 0 | 10 | 1 |
| Total | 11 | 32 | 2 |

Local extraction plus evaluation was p50 0.227 ms and p99/max 0.420 ms. This excludes network and process startup.

A separate inline execution used the same public pack and policy files with the real `loop.extract_with_budget`, `loop.decide_with_guard`, `evaluate` and pure state application. All 45 decisions, reason lists and evidence lists matched direct evaluation. Counts were again 11/32/2. No engine state file was written.

The last actual event was copied with an expired real-clock deadline. Extraction and evaluation each raised `ProcessingTimeout`. Submitting its actual Decision and attempting an expired timeout resolution each raised `ApiTimeout` before dispatch. The simulator settings cache remained empty, so neither expired dispatch path read credentials. No customer answer was constructed.

One worker was occupied by a bounded synchronization wait while actual extraction was queued with 50 ms available. The caller raised `ProcessingTimeout`, cancelled the queued task and returned no replacement result. The wait was released and the executor closed. Five invalid human windows, NaN, infinity, zero, five seconds and boolean true, were rejected.

`python -m leash.runner.cli --help` displayed only the engine evaluator. Loading provider settings in the new worktree with no `.env` raised `SettingsError`.

## Real HTTP budget check

A temporary loopback HTTP server exposed a plain text body, a 409 response and a body written one byte every 80 ms. The client used a temporary local configuration. No real credential was loaded or sent. This service measured transport behavior and did not emulate simulator authorizations or return payment decisions.

Observed requests:

| Request | Result |
| --- | --- |
| GET `/body` | 200, complete body returned |
| GET `/refused` | `ApiError`, status 409 and the actual text body |
| GET `/trickle`, 0.250 s deadline | `ApiTimeout` after 0.253 s |
| GET `/expired`, deadline already passed | `ApiTimeout`, no request reached the server |

The server saw exactly `/body`, `/refused` and `/trickle`. Each trickled byte arrived sooner than a per-read timeout, but the total budget still expired. The client did not retry. Its error stated that the remote outcome was unknown. The owned server was stopped and the temporary configuration removed.

The same isolated configuration exercised the scoped provider accessor. The returned object had exactly one field, `api_key`, and its representation did not contain the value. No provider was called.

A read-only review identified JSON decoding outside the budget in the first draft. Decoding now happens inside the bounded operation, followed by an explicit clock check before any result is returned. The decoded body is retained on the response so `call()` does not parse it again. A body larger than 16 MiB raises before decoding. This size check runs after HTTPX has buffered the response; it does not claim a streaming memory bound.

After that correction, a real loopback JSON response containing 1,000 integers decoded successfully and `call()`'s body reader used the same cached object. A 16 MiB plus one byte response raised `ApiResponseError`. Repeating the trickled-body request still raised `ApiTimeout` after 0.253 s for a 0.250 s budget. The server saw exactly `/json`, `/large` and `/trickle` and was stopped afterward.

## Remaining limits

A timed-out running Python thread cannot be forcibly cancelled by `Future.cancel()`. Its late return is discarded and cannot trigger submission. Executor shutdown still waits for running pure work. This change does not claim process isolation for a hung extractor or evaluator.

An HTTP timeout after dispatch cannot establish whether a mutation was accepted. Durable intents, ambiguous-write reconciliation, shared-lock effective-policy refresh and final state checks remain separate P3 work. Until those land, this branch is not a model-enabled release candidate.

No live simulator call was made because credential rotation remains unconfirmed. No real customer confirmation, answer, tightening or revocation was performed. The sweeper's new bounded write path still needs live verification after rotation. No test suite or linter was run.
