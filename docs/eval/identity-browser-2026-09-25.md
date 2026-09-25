# Identity UI in a real browser

Independent Chrome checks used the frozen app candidate `1c5d61c5db05b174398b922a6648b8437ce7e460` from PR #82. The same checkout served the actual Wallet API through Uvicorn on an OS-selected loopback port. The browser used an isolated context and a disposable policy store. No browser response or transport was replaced.

## Observed flow

The Register screen contained Username and Password fields. A disposable account was created through its button; the network panel recorded POST `/account` returning 201. A session read identified the newly registered username. Shop then displayed the external-MCP-client disclosure.

At an explicitly emulated 390-pixel viewport, a fresh disposable account completed this sequence through the UI:

1. Registration followed by a matching username in GET `/session`.
2. Account menu, then Sign out. GET `/session` returned 401.
3. Wrong-password sign-in displayed `Username or password is wrong.` inline.
4. Correct-password sign-in restored a session identifying that account's username.
5. Connected agents displayed `No connected agents`.

The credential values were generated in browser memory and were not returned by the browser tools. `localStorage` and `sessionStorage` each had zero entries.

Changing the emulated viewport to 320 by 640 reloaded the page. GET `/session` still returned 200 and Connected agents still showed the empty state. Measured `innerWidth` and document `scrollWidth` were 390/390 and 320/320 respectively.

An unknown, nonsecret pairing selector produced an actual GET `/pairing/preflight_missing` with HTTP 404. The Pair screen displayed the error and offered `Continue without this agent link`. Clicking it returned to Shop and removed the `pair` query parameter. No pairing approval was submitted.

At 320 pixels, the browser opened Wallet's Needs you, Active and Rules tabs, then Activity. Each rendered its actual empty-state response without horizontal page overflow. The Rules view showed global-policy version 0 and said account-wide editing was unavailable there. The observed network requests for pending step-ups, drafts, mandates and global policy returned 200. The final inspected view had no console errors or warnings; this is not a claim about all earlier browser-tool execution errors.

## Probe corrections

The initial browser script assumed the controls were inside a form element. They are rendered as inputs and action buttons; the probe stopped on that incorrect assumption before submission. The controls were then addressed by their actual IDs and button text.

A plain browser-window resize yielded a measured width of 500 pixels. Explicit device emulation established the reported 390- and 320-pixel viewports. That emulation reloaded the page and discarded the first probe's in-memory credential. A new disposable account was generated for the subsequent register/logout/wrong-password/correct-password sequence. No real customer credential was reset or recovered, and no application source was changed for these probe corrections.

## Scope and cleanup

These checks did not approve a pairing, revoke an agent, confirm a mandate or answer a purchase. They do not establish a genuine human Wallet journey or foreign-draft isolation after a paired proposal. No simulator or model-provider request was made by this browser exercise.

Only the owned browser tab was closed. A stop marker shut down the owned Uvicorn process; its task completed with exit 0 and the temporary store's removal was independently verified. Existing browser tabs and teammate services were left alone. The isolated source tree and generated untracked lockfile were retained.

No test suite or linter was added or run. The earlier [HTTP/MCP identity checks](identity-http-2026-09-25.md) and [Origin/customer-lock checks](policy-locks-http-2026-09-25.md) record their separate source revisions and limits.
