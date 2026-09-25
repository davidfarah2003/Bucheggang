# Local paired Wallet rehearsal

Date: 25 September 2026. Checkout: `d486574` on `main`.

I ran the Wallet API over loopback and the policy MCP server over stdio from the same checkout. Both used one disposable policy store. The client exercised the real HTTP and MCP transports; it did not replace application routes or simulator responses. The store and both processes were removed or stopped after the run. No simulator write, customer mandate confirmation, or purchase answer was submitted.

| Operation | Observed result |
| --- | --- |
| `GET /app/`; anonymous `GET /session` | 200; 401 |
| Register local account; read its session | 201; 200 |
| MCP `begin_pairing`; Wallet pairing read | Pairing displayed with `policy:propose` and `policy:read` |
| MCP `complete_pairing` before Wallet approval | `PairingPending` tool error |
| Wallet pairing approval; MCP completion | 204; agent token returned to MCP client |
| MCP authoring instructions and proposal; Wallet draft read | Draft saved; HTTP 200 with the same version and hash |
| MCP status and summary | `pending`; instruction matched the saved draft |
| Stale Wallet confirmation using wrong version and hash | 409; no mandate created |
| Second account reads first account's draft | 404 |
| First account rejects draft; MCP status readback | 204; `rejected` |
| Wallet revokes agent; MCP reads status again | 200; `Unauthorized` tool error |

The first transport exercise stopped after pairing because the local driver looked for `state` in the MCP status response. The actual response uses `status` as specified by `policy_status`. I corrected the driver and reran the full sequence above. That was a driver error; application code did not change.

The documented 45-attempt offline replay also completed on this checkout: 11 approve, 32 decline and 2 step up. All 45 decision and reason-code pairs matched `replay-2026-09-25-all.csv`. JavaScript syntax checks and Python compilation passed. The installed `uv` wrapper could not open its cache under the filesystem sandbox, so these checks used the existing `.venv/bin/python` directly.

An authenticated read-only `GET /v1/bootstrap` reached the live simulator. It reported API version `0.1.0`, ten available scenario IDs, an 8-second automated decision deadline, a 120-second step-up window, and reset disabled. No scenario run or mandate was created. A complete customer confirmation, simulator decision, Wallet step-up answer and repeat run remain unverified on this checkout. The live slot and actual Wallet operator are prerequisites for that exercise.
