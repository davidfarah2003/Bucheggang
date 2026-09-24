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

Running example, from `SCEN0002`:

> Replace my worn road-running shoes in size 43. Buy only from a specialist sports retailer, only if the order can be returned within 14 days or more, and pay no more than CHF 200. Ask me when uncertain.

## Scope

In:

- User-side policy recommendation: the customer's agent gets the field vocabulary, rule format, examples, and known gaps from the MCP tool, then proposes rules from the cardholder instruction. The MCP backend validates and stores that proposal; it makes no LLM call.
- `propose_task_policy`: instruction and an explicit compiler mode in, canonical `PolicyDraft` out (rules with the source phrase for each, example purchases, open questions). A failed model-supplied proposal raises; it never switches to deterministic mode.
- Progent's monotonic confinement rule applies to later policy edits: an expanded set of allowed purchases requires a fresh customer confirmation. Automatic tightening may only remove purchases from that set, and still needs an auditable version and hash.
- Draft store with version and hash. The app reads a draft from the backend by `draft_id`; it never gets one from the agent.
- The confirm route: hash and version check, answers to open questions folded into rules or `uncertainty_policy`, then the runner's mandate create and confirm calls, then `Mandate` stored and returned.
- The MCP tools the shopping agent sees: `propose_task_policy`, `get_policy_status`, `request_policy_confirmation` (creates the pending item the app shows), `buy` (delegates to the runner), `get_purchase_status`. No confirm, resolve, tighten or revoke tool.

Out:

- Global policies (after the hackathon).
- Purchase decisions and step-up handling (plans 02, 05).
- Real Viseca authentication. The demo app uses a local login.

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
6. Confirm route per `contracts.md`: mismatch is a 409; success calls the runner's mandate client and stores the `Mandate`.
7. MCP server exposing the agent-facing tools, backed by the same store. A short transcript of an agent using them is a demo asset (plan 06).
8. Audit entries for draft, confirmation and rejection: what was submitted, version, hash, who confirmed, when.

## How we check it works

- For each of the 5 scenario instructions, the extractor produces a draft that passes validation. A team member reviews each draft by hand against the instruction and notes the result in the Log.
- The `SCEN0002` examples produce approve, decline and step_up from `evaluate`.
- Changing a rule after the app has loaded the draft makes confirmation fail with a 409.
- `grep -r "confirm\|resolve\|revoke" src/leash/policy/mcp*` shows no agent-callable tool with those names.

## Open questions

- Who answers open questions in the demo: the customer on the confirmation screen (proposed), or a default we pick and show?
- Do we keep the simulator's `guidance` and `open_questions` fields empty, given live events omit them? Proposed: yes; our store keeps the real answers.

## Log

(one line per finished task: date time, who, what, how it was tried, sha)

2026-09-24 17:09 oskar1: SCEN0002 sample draft with six rules and five boundary examples; loaded `docs/samples/scen0002_draft.json` and recomputed its SHA-256, `hash_matches True`, @4b912dc.
2026-09-24 17:43 oskar1: immutable draft store and simulator draft mapping; created, revised and confirmed a temporary grocery draft through `DraftStore`, observed stale version rejected, version 2, simulator draft `SD-1`, mandate `TM-2`, @8b6d3b8.
2026-09-24 18:40 oskar1: serialized draft revision, confirmation and rejection with a per-draft file lock and checked rule value types; ran one temporary-store smoke flow, observed numeric string rejected, version 2, and one terminal race winner with one conflict, @6c90c83.
2026-09-24 17:45 oskar1: fixed-output prompt, strict model proposal validation and deterministic instruction compiler; ran five supplied instructions and observed 4, 3, 6, 3, 5 rules, while invalid model output raised `InvalidDraft`, @6837a79.
2026-09-24 17:52 oskar1: made compiler mode explicit under AGENTS.md no-fallback rule; reran five instructions with deterministic mode and got 4, 3, 6, 3, 5 rules; missing or invalid model mode output raised `InvalidDraft`, @09ae26f.
2026-09-24 18:00 oskar1: incorporated Progent's rule that policy expansion needs explicit approval and clarified that the customer-side agent drafts proposals while the MCP backend only provides instructions and validates/stores them; paper reviewed at arXiv:2504.11703v3.
