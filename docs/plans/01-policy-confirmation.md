# 01 Policy draft and confirmation

- Status: draft
- Owner: Oskar (proposed)
- Lane: policy. Channel `team.zurichbuchegg.policy`, branch `lane/policy`, worktree `.worktrees/policy`
- User flow step: customer request, then draft policy, then confirmation in the Viseca app, then `mandate_id`
- Design: [Secure policy confirmation](../idea/viseca-agent-control-layer.md#secure-policy-confirmation), [Policy model](../idea/viseca-agent-control-layer.md#policy-model)
- Papers: [AutoCedar](../papers/2607.03656v1.pdf) (reviewed intent atoms, floors and ceilings, gaps surfaced before the policy is final), [SAFR](../papers/SAFR.pdf) (audit record of the confirmation), [Progent](https://arxiv.org/abs/2504.11703) (symbolic permission rules and monotonic confinement)
- Challenge API: [technical_details.md, step 5 and Rule format](../../viseca-2026/technical_details.md)
- Contracts: `PolicyDraft`, `Rule`, the field vocabulary, `POST /drafts/{id}/confirm` in [contracts.md](../contracts.md)

## Goal

Turn a cardholder instruction into a policy the customer can read, check against example purchases, and confirm. The shopping agent only ever receives the `mandate_id`.

The authoring flow works for any shopping category. The shoe scenario below is a sample for review, not a template or an allowed-category list. Unsupported product details remain visible as open questions until the customer reviews an enforceable draft.

Running example, from `SCEN0002`:

> Replace my worn road-running shoes in size 43. Buy only from a specialist sports retailer, only if the order can be returned within 14 days or more, and pay no more than CHF 200. Ask me when uncertain.

## Scope

In:

- User-side policy recommendation: the customer's agent gets the field vocabulary, rule format, examples, and known gaps from the MCP tool, then proposes rules from the cardholder instruction. The MCP backend validates and stores that proposal; it makes no LLM call.
- `propose_task_policy`: the user-side agent supplies the instruction and an explicit proposal. The backend validates its rule fields, source phrases, examples and open questions, then stores a canonical `PolicyDraft`. An invalid proposal raises.
- Progent's monotonic confinement rule applies to later policy edits: an expanded set of allowed purchases requires a fresh customer confirmation. Automatic tightening may only remove purchases from that set, and still needs an auditable version and hash.
- Draft store with version and hash. The app reads a draft from the backend by `draft_id`; it never gets one from the agent.
- The confirm route: hash and version check, answers to open questions folded into rules or `uncertainty_policy`, then the runner's mandate create and confirm calls, then `Mandate` stored and returned.
- The policy MCP tools supply authoring instructions and store proposed drafts. Status, purchase and runner tools can be added around the same confirmed mandate contract. No confirm, resolve, tighten or revoke tool is exposed to the shopping agent.

Out:

- Purchase decisions and step-up handling (plans 02, 05).
- Real Viseca authentication. The demo app uses a local login.
- Global policy management is parked until the live runner loop, app step-up flow, and replay work end to end. The intended shape is recorded under Later in plan 04.

## Steps

1. Draft schema in `src/leash/contracts/` with the engine lane (already sketched in `contracts.md`). A sample draft for `SCEN0002` in `docs/samples/` so the app lane can build against it today.
2. Provide the user-side agent a fixed instruction bundle with the field vocabulary, JSON shape, examples, and ambiguity prompts. Validate its proposed JSON on the backend; reject unknown fields and fields outside the vocabulary. Rule values stay numbers, strings or lists of strings. The backend makes no model call.
3. Example purchases, following AutoCedar's floors and ceilings:
   - must approve: size 43 road shoes, CHF 150, sports retailer, 30-day returns;
   - must decline: CHF 230; or size 42; or a second pair after one succeeded;
   - must ask: return period not stated.
   Run them through `leash.engine.evaluate` at draft time; the expected result is stored next to each example, and a mismatch fails validation of the draft.
4. Open questions for gaps the instruction leaves, for example "the merchant does not state a return period: ask me, or decline?" The answer becomes a rule or sets `uncertainty_policy`.
5. Store the draft immutably with version and SHA-256 of its canonical JSON. Any edit is a new version.
6. Confirm route per `contracts.md`: mismatch is a 409; call the runner's mandate client and store the `Mandate`.
7. MCP server exposing the agent-facing tools, backed by the same store. A short transcript of an agent using them is a demo asset (plan 06).
8. Audit entries for draft, confirmation and rejection: what was submitted, version, hash, who confirmed, when.
9. `get_policy_status(draft_id)` tool. Reads the store and returns the draft's state: `pending`, `confirmed` with the `mandate_id`, `confirmed_at` and the confirmed version and hash, or `rejected` with the reason. This is how the agent gets its `mandate_id` after the customer confirms in the Wallet (design, "Secure policy confirmation", step 7). It reads `confirmation.json` and `rejection.json` through `DraftStore.get_confirmation` and a matching `get_rejection`; it never writes and cannot confirm. Unknown draft raises. Try it once: propose, poll `pending`, confirm in the Wallet, poll again and see the `mandate_id`.
10. `get_policy_summary(draft_id)` tool. Returns the current draft version's `plain_english` sentences, the examples with their expected outcomes, the open questions with answers where the customer has given them, and the `uncertainty_policy`. It is the read-back the design lists so the agent can show the customer what it proposed; the Wallet still loads the draft from the backend, never from the agent. No rule fields, no hash.
11. `docs/mcp-client.md`: the launch command (`uv run python -m leash.policy.mcp_server` with `LEASH_POLICY_STORE` set to the same directory as the Wallet API), a client config block for one MCP-compatible agent, and the tool list with one-line descriptions. Then record one real session as `docs/samples/mcp-transcript-scen0002.md`: the agent calls `get_policy_authoring_instructions`, proposes the SCEN0002 policy with `propose_task_policy`, polls `get_policy_status` until the Wallet confirms, and prints the `mandate_id`. That transcript is the plan 06 asset from step 7.
12. `buy(mandate_id, facts: [PurchaseFacts])` and `get_purchase_status(authorization_id)`. Parked for the 12:00 submission; see Decisions. The tool shapes are in `docs/contracts.md` under "MCP tools" so an agent can be written against them, and the backend answers `buy` with an error that says purchases arrive through the simulator in demo mode.

## How we check it works

- For each of the 5 scenario instructions, the extractor produces a draft that passes validation. A team member reviews each draft by hand against the instruction and notes the result in the Log.
- The `SCEN0002` examples produce approve, decline and step_up from `evaluate`.
- Changing a rule after the app has loaded the draft makes confirmation fail with a 409.
- `grep -r "confirm\|resolve\|revoke" src/leash/policy/mcp*` shows no agent-callable tool with those names.
- `list_tools` on the MCP server shows exactly `get_policy_authoring_instructions`, `propose_task_policy`, `get_policy_status`, `get_policy_summary`, `buy` and `get_purchase_status`, and every tool's input and output matches "MCP tools" in `docs/contracts.md`.
- After a Wallet confirmation, `get_policy_status` returns the same `mandate_id` the confirm route returned. Before it, `pending`. After a rejection, `rejected` with the reason.
- `docs/samples/mcp-transcript-scen0002.md` is a real session, with the draft id and mandate id it produced, and the same draft id appears in the store.

## Decisions

- The customer answers open questions on the confirmation screen. The app never chooses a default on the customer's behalf.
- Keep the simulator's `guidance` and `open_questions` fields empty because live events omit them. Store the customer's answers in the confirmed policy and audit record.
- 2026-09-24 23:30, David: the agent-facing MCP surface is the six tools in "MCP tools" in `docs/contracts.md`. The four authoring and status tools (steps 2, 9, 10) are in scope for Friday 12:00. `buy` and `get_purchase_status` (step 12) are declared in the contract and parked: in the challenge, purchases are generated by the simulator and reach the engine through the runner (plan 05), so an external agent has nothing to buy against before the live run, and the demo in plan 06 does not call `buy`. After the submission, `buy` builds an `Event` from the agent's cart and the confirmed mandate, runs `leash.extract.extract_event` over the agent's form for provenance, calls `leash.engine.evaluate` with `leash.engine.state.load`, records through `leash.engine.state.record`, and returns the `Decision`; a `step_up` goes to the Wallet through the existing step-up book and `get_purchase_status` reports the resolution. Until then `buy` raises with the message in the contract. No tool ever confirms, resolves, tightens or revokes.
- `get_policy_status` tells the agent only what the store knows: the state, the mandate id and the timestamps. It returns no rule text, so the agent cannot use it to learn the policy it was not shown, and `get_policy_summary` returns only the `plain_english` sentences the customer also sees.
- The design's `request_policy_confirmation` is not a tool. Confirmation is requested by the agent handing the customer the Wallet link `/app/?draft=<draft_id>`; the backend never pushes to the customer. `get_user_context` is not a tool either: the agent gets the field vocabulary from the authoring guide and nothing about the customer's history or cards.

## Log

(one line per finished task: date time, who, what, how it was tried, sha)

2026-09-24 17:09 oskar1: SCEN0002 sample draft with six rules and five boundary examples; loaded `docs/samples/scen0002_draft.json` and recomputed its SHA-256, `hash_matches True`, @4b912dc.
2026-09-24 17:43 oskar1: immutable draft store and simulator draft mapping; created, revised and confirmed a temporary grocery draft through `DraftStore`, observed stale version rejected, version 2, simulator draft `SD-1`, mandate `TM-2`, @8b6d3b8.
2026-09-24 18:40 oskar1: serialized draft revision, confirmation and rejection with a per-draft file lock and checked rule value types; ran one temporary-store smoke flow, observed numeric string rejected, version 2, and one terminal race winner with one conflict, @6c90c83.
2026-09-24 17:45 oskar1: fixed-output prompt, strict model proposal validation and deterministic instruction compiler; ran five supplied instructions and observed 4, 3, 6, 3, 5 rules, while invalid model output raised `InvalidDraft`, @6837a79.
2026-09-24 17:52 oskar1: made compiler mode explicit under AGENTS.md no-fallback rule; reran five instructions with deterministic mode and got 4, 3, 6, 3, 5 rules; missing or invalid model mode output raised `InvalidDraft`, @09ae26f.
2026-09-24 18:00 oskar1: incorporated Progent's rule that policy expansion needs explicit approval and clarified that the customer-side agent drafts proposals while the MCP backend only provides instructions and validates/stores them; paper reviewed at arXiv:2504.11703v3.
2026-09-24 19:15 oskar1: implemented the agreed `confirming_answers` question contract in compiler output and draft validation; created a temporary SCEN0002 draft and rejected an answer outside its options, with six rules and two questions.
2026-09-24 19:22 oskar1: confirmation accepts only the draft's confirming answers and rejection checks the supplied version and hash; called SCEN0002 confirm and stale reject through FastAPI TestClient, observed 200 with a mandate ID and 409, using the local FastAPI dependency directory.
2026-09-24 19:32 oskar1: assembled the FastAPI customer shell with local username sessions and the policy draft router; called login, draft GET, app GET and logout through TestClient using the approved app static mount, observed 401, 200, 200, 204, then 401.
2026-09-24 19:47 oskar1: corrected missing and revoked session handling to return 401; called DELETE /session without a cookie, after login, and after logout, observed 401, 204 and 401.
2026-09-24 21:00 oskar1: integrated shell smoke against runner #25 @fb57cfc, mandate routes #26 @32abc7b and app static @448a6d6 in a temporary source tree; FastAPI TestClient observed login/session 200, unauthenticated session 401, app 200, unknown draft/mandate/history 404, pending step-ups 200 and logout 204.
2026-09-24 21:09 oskar1: added `python -m leash.api` and `docs/run-wallet.md`; launched it on 127.0.0.1:8128 against a temporary tree with runner #25 @fb57cfc, mandate routes #26 @636629e and app static @448a6d6, observed unauthenticated session 401, login 200 and `/app/` 200, then stopped the server.
2026-09-24 21:24 oskar1: after rebasing onto runner #25 @ed2bc3c and mandate #26 @636629e, launched `python -m leash.api` on 127.0.0.1:8129 with app static @448a6d6 in the temporary tree; observed `/session` 401 unauthenticated, login 200, `/app/` 200 and pending step-ups 200, then stopped the server.
2026-09-24 21:31 oskar1: rejected usernames containing internal spaces, tabs or newlines; one-off FastAPI TestClient smoke against app static @885d699 observed 422 for each and for whitespace-only input, and 200 for `local-demo`.
2026-09-24 18:39 policy_confirm: customer confirmation service and app routes; called `GET /drafts/{id}` and `POST /drafts/{id}/confirm` with FastAPI TestClient, observed 200 and mandate `mandate-1`, then 409 for stale confirmation; SCEN0002 merchant ambiguity raised `UnresolvedQuestion` before simulator call, @ae6380d.
2026-09-24 18:51 policy_confirm: reserved draft confirmation before simulator calls; one-off FastAPI call observed concurrent reject blocked, confirm 200 and stale repeat 409; simulated confirm failure raised and left pending simulator draft ID `sim-2` while revise was blocked, @7267153.
2026-09-24 18:46 policy_confirm: MCP authoring guide resource and two agent tools; called `list_tools`, `read_resource`, `get_policy_authoring_instructions`, and `propose_task_policy` through an in-memory MCP client, observed two tools, JSON guide and stored draft version 1; installed the source package with pip, @39b8e6e.
2026-09-24 19:39 oskar1: removed the unused server-side deterministic compiler and made the authoring guide category agnostic; stored a kitchen mixer proposal with one rule and observed two MCP tools through `list_tools`.
2026-09-24 20:32 oskar1: recorded the owner decision to defer global policy management until the runner loop, app step-up flow and replay work end to end; its later shape is in plan 04.
