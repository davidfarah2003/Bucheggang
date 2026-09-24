# 01 Policy draft and confirmation

- Status: draft
- Owner: unassigned
- User flow step: customer request, then draft policy, then confirmation in the Viseca app, then `mandate_id`
- Design: [Secure policy confirmation](../idea/viseca-agent-control-layer.md#secure-policy-confirmation), [Policy model](../idea/viseca-agent-control-layer.md#policy-model)
- Papers: [AutoCedar](../papers/2607.03656v1.pdf), [SAFR](../papers/SAFR.pdf)
- Challenge API: [technical_details.md, step 5 and Rule format](../../viseca-2026/technical_details.md)

## Goal

Turn a cardholder instruction into a policy the customer can read, check against example purchases, and confirm. The shopping agent only ever receives the `mandate_id`.

Running example, from `SCEN0002`:

> Replace my worn road-running shoes in size 43. Buy only from a specialist sports retailer, only if the order can be returned within 14 days or more, and pay no more than CHF 200. Ask me when uncertain.

## Scope

In:

- `propose_task_policy`: instruction in, canonical draft out (rules, source phrase for each rule, example purchases, open questions).
- Stored draft with version and hash. The app reads it from the backend by `draft_id`.
- Confirmation screen in the Viseca app.
- Mapping the draft to `POST /v1/mandates` and `POST /v1/mandates/{draft_id}/confirm`.

Out:

- Global policies (later plan).
- Purchase decisions and `step_up` (separate plans).
- Real Viseca authentication. The demo app uses a local login.

## Steps

1. Define the draft schema. Each rule has `field`, `operator`, `value`, optional `currency`, `scope`, `period_days`, plus our own `source_text` and `plain_english`. Only the first six go to the simulator. Rule values stay numbers, strings or lists of strings.
2. Write the extractor prompt with a fixed JSON output. Validate the output against the schema and reject unknown fields.
3. Generate example purchases for the draft, following AutoCedar's floors and ceilings:
   - must approve: size 43 road shoes, CHF 150, sports retailer, 30-day returns;
   - must decline: CHF 230, or size 42, or a second pair;
   - must ask: return period not stated.
4. List open questions for gaps the instruction leaves, for example "merchant does not state a return period: ask or decline?" The customer's answer becomes a rule or sets `uncertainty_policy`.
5. Store the draft immutably with version and SHA-256 hash of its canonical JSON. Any edit creates a new version.
6. Build the app screen: original sentence, rules with the phrase each came from, example purchases with their expected result, open questions, confirm and reject buttons.
7. On confirm, check the hash still matches, then call the simulator's create and confirm endpoints and store the returned `mandate_id` against our draft version.
8. Write an audit entry for draft, confirmation and rejection (SAFR audit fields: what was submitted, version, who confirmed, when).

## How we check it works

- For each of the 5 scenario instructions, the extractor produces a draft that passes schema validation. A team member reviews each draft by hand against the instruction.
- The example purchases for `SCEN0002` produce the expected approve, decline and ask when run through the decision engine (once plan 02 exists).
- Changing a rule after the app has loaded the draft makes confirmation fail with a version mismatch.
- The agent-facing MCP tools have no way to confirm a draft.

## Open questions

- Who answers open questions in the demo: the customer on the confirmation screen, or a default we pick and show?
- Do we keep the simulator's `guidance` and `open_questions` fields empty, given live events omit them?
