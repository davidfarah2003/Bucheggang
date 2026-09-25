# Identity backend over real local transports

The backend at `4e4a5e5d523784bf36b6028bac61800e6de9b341`, the frozen candidate for PR #73, completed the local HTTP/MCP exercise described here. The candidate was checked out separately, with its own installed dependencies. Its source was not edited.

The run used an actual Uvicorn process on an OS-selected loopback port, actual HTTP clients, and an actual policy MCP subprocess over stdio. Accounts and policies were disposable local records. No transport was mocked. No pairing approval, mandate confirmation, customer purchase answer, simulator request or model-provider request was made.

## Observed results

| Operation | Observed result |
| --- | --- |
| Anonymous session, drafts, mandates, global policy and agents reads | 401 on all five |
| Registration | 201; response contained a 32-character account ID and the submitted disposable username |
| Duplicate registration | 409 |
| Two simultaneous registrations of one new username | One 201 and one 409 |
| Session and owned draft, mandate and agent lists | 200; all new-account lists were empty |
| Session cookie | HttpOnly and SameSite=Strict |
| Initial global policy | Version 0, keyed by account ID |
| Global-policy PUT without Origin or with a different Origin | 403 |
| Global-policy PUT with the configured exact Origin | 200; the empty policy advanced to version 1 |
| Repeating the obsolete global-policy version/hash | 409 |
| Malformed draft identifier | 422 |
| Valid UUID with no draft, and unknown mandate | 404 |
| Second account with an 80-character Unicode username | 201; its global policy remained version 0 |
| Actual API stop/start using the same disposable store | Existing session still returned 200 with the same account ID; global policy retained version 1 |
| Logout without Origin | 403 |
| Logout with exact Origin, then session read | 204, then 401 |
| Password login after logout | 200 |
| Six unknown-account login attempts | Five 401 responses, then 429 |

There were 36 individually recorded HTTP observations plus the two concurrent registration requests. Every status in the completed run matched its expected status. The two registration requests used separate HTTP clients and ran concurrently in a two-worker executor.

## Actual MCP subprocess

The client initialized a real stdio session and called the policy server's tools:

- Unpaired `get_policy_authoring_instructions` returned the pairing-required tool error.
- `begin_pairing` returned a code, private verifier, expiry and scopes. The authenticated HTTP pairing display matched the returned label and scope list.
- `complete_pairing` with the correct code and verifier, before any approval, returned `PairingPending`.

The Wallet pairing shell returned 200 with `Referrer-Policy: no-referrer`. The account's agent list stayed empty after the refused completion. The code and verifier were used in memory and are excluded from this report and its result file. The pairing approval route was not called.

## Storage and cleanup

After the operations, eight identity JSON files were present. Every file had mode 0600. Their contents contained none of the supplied password, original session cookie, pairing code or verifier in clear. This was a check of those concrete secrets, not a proof covering every possible credential or storage failure.

The API process was stopped after verification. The stdio session closed and its subprocess exited. The disposable policy/identity store was removed by its owning context. No existing app server, supervisor or teammate process was stopped. The detached source tree and its generated untracked lockfile were retained.

## Probe corrections

The first execution stopped because the probe expected 404 for `missing-preflight-draft`. That string is not a canonical UUID; the backend correctly returned 422. The next execution checked malformed IDs as 422 and a newly generated, unknown canonical UUID as 404.

The second execution then stopped in the probe's MCP result access: the installed MCP 2.2 client uses `is_error` and `structured_content`, while the probe used the older camel-case names. The installed model fields were inspected and the probe was corrected. No application code changed for either stop. The original stopped executions and their local logs were retained separately.

The third execution completed with exit 0:

```text
/private/tmp/identity-http-4e4a5e5/.venv/bin/python \
  .cotal/identity_http_exercise_v3.py
```

The driver is an ignored, local transport exercise. No test suite or linter was added or run. [Recorded observations](identity-http-2026-09-25.json) contain statuses and scope limits, with no credential values. The recorded time in that file is the result file's observed write time; individual request wall-clock timestamps were not captured.

## What this does not establish

This does not cover a human approving a pairing, a paired agent proposing an owned draft, the customer confirming a real simulator mandate, a purchase answer, or live simulator write recovery. Session expiry after 12 hours idle or 24 hours absolute was not exercised. The observed account separation covers global policy and empty lists; it does not establish foreign-draft isolation after a paired proposal. HTTPS cookie behaviour was not exercised on this loopback HTTP run.

These are functional observations against the named candidate. They do not replace the independent security review or establish a completed Wallet journey. Confirmation and global-policy customer-lock integration remains a separate policy follow-up.
