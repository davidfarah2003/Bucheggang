# Local Wallet and MCP verification

Date: 25 September 2026. Initial application revision: `22a9923239f78f16b19807b9e148eb22919fc732`. Ownership repair starts from main `498898155272e17b9907c364d723a503541ad6fc`.

These checks used running servers and real HTTP/MCP clients. No simulator run, confirmation, step-up answer, tightening or revocation was submitted. No provider was replaced and no decision record was fabricated.

## MCP and Wallet flow

Started the real Wallet API with an isolated policy directory and `LEASH_PORT=8873`. An `mcp.ClientSession` connected over stdio to `python -m leash.policy.mcp_server`, sharing that directory. The proposal came from the existing shoes sample with its questions still unanswered.

| Request or action | Observed |
| --- | --- |
| MCP initialize and list tools | Six tools: authoring instructions, proposal, status, summary, buy, purchase status |
| MCP authoring instructions and proposal | Saved draft `673d9e7d-3325-4801-9245-4843210bfe09`, version 1 |
| MCP status and summary | Pending; saved instruction matched read-back |
| MCP purchase status | Explicit parked-tool error |
| Anonymous GET session, draft, pending, mandate history and decision detail | 401 for each |
| POST session with an isolated local demo username | 200 |
| GET saved draft through Wallet HTTP | 200; same hash as MCP result |
| POST confirm with wrong version, then wrong hash, both with no answers | 409 for each: `draft version or hash changed; reload before confirming` |
| Authenticated GET unknown history and decision IDs | 404 |
| GET pending in the isolated empty runtime | 200, empty list |
| DELETE session, then GET session | 204, then 401 |
| Final MCP status | Still pending |

The first client invocation failed before creating a draft because this installed MCP SDK uses `is_error` and `structured_content`, rather than the older camel-case response attributes. Reading the installed response model and using those fields made the actual calls above succeed. No application source was changed for that client correction.

A second real MCP process used streamable HTTP and an ephemeral in-memory bearer token. Missing and incorrect bearer values each returned 401. The authenticated MCP client initialized, listed six tools and read the same pending draft created through stdio. The token was neither printed nor stored. The owned HTTP MCP process was stopped after the requests, exit -15.

## Browser at 400 px

Chrome opened the running Wallet with a 400 by 860 mobile viewport and a separate browser context. Local demo login succeeded.

The documented `?draft=<id>` link failed with `URL query parameter draft_id is missing or is not a non-empty string`. The implemented `?draft_id=<id>` link loaded the saved draft, its rules and both unanswered questions. Confirm remained disabled. The rule-details drawer opened and closed. Approvals showed no pending purchases; Policy and Activity correctly showed no active wallet in this unconfirmed session. Sign-out returned to login.

The draft page had `innerWidth=400` and `document.documentElement.scrollWidth=400`; no element exceeded the right edge. No browser console errors or warnings were reported. This covers the draft and empty-state screens only, not a populated customer step-up or accepted-purchase history.

The documentation-link correction is separate PR #40. No frontend file was changed here. The Wallet server received SIGTERM and stopped; its listener on port 8873 was verified absent.

## Ownership failure and repair

The original runner routes required a login but did not check who confirmed the referenced mandate. A second read-only server used the actual saved records from the completed hiking-boots run, an empty isolated confirmation store and the unrelated local username `unrelated-evaluation-user`. The records remained at their original location; no fixtures or copies were created.

| GET route | Before | After repair |
| --- | ---: | ---: |
| `/mandates/TMd3ea0352275a0858` | 404 | 404 |
| `/mandates/TMd3ea0352275a0858/decisions` | 200 | 404 |
| `/decisions/AU10323-414975d9` | 200 | 404 |

On the repaired implementation, anonymous history, detail and pending requests returned 401. The unrelated customer's pending response was an empty list. `StepUpBook.get` read an existing completed-run step-up and validated its authorization and mandate against the stored path. Both short-lived read-only servers stopped cleanly.

The repair shares the existing confirmation-store ownership lookup through `leash.policy.ownership.owned_confirmations`. It gates history and detail by `confirmed_by`, limits pending to owned mandates and checks the step-up's mandate before `book.answer` can call the simulator. Duplicate confirmation ownership fails loudly. No endpoint response shape changes.

The app passes its existing shared `DraftStore` to the runner routers. The standalone runner `--serve-port` now requires `LEASH_POLICY_STORE` pointing to the same confirmation store. Starting it without that variable raised `RuntimeError: --serve-port requires LEASH_POLICY_STORE with the customer confirmations`, exit 1, before any run creation. Its local customer header must identify the username recorded as `confirmed_by`.

## Limits

No successful customer confirmation or step-up answer was made in this verification. The actual human Wallet journey remains scheduled with the shared simulator slot. Positive owner access and a live populated pending list need that retained confirmation record; no synthetic owner record was inserted to claim those checks passed.

The demo login still accepts a local username without a password. Ownership filtering does not turn it into production authentication. Shared mutation locking, effective-policy rechecks, accepted-result persistence intents and complete live end-to-end timing are separate open work.
