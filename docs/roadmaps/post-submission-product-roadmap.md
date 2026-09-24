# Post-submission product roadmap

This roadmap describes product work after the 25 September 2026 submissions. It extends the hackathon demo without changing the current submission scope. The Wallet remains the trusted place where a customer confirms a proposed policy and answers a purchase step-up.

## Delivery order

| Phase | Work | Completion gate |
| --- | --- | --- |
| 1. Product and service foundation | Choose the production host, regions, customer identity provider, data retention, and provider billing model. Replace demo usernames and process-local sessions with authenticated customer identity. Scope drafts, mandates, purchases, and provider settings to that identity. Move from shared local files to durable storage with concurrency control and backups. Keep simulator and provider secrets server-side. | Two customer accounts can use the service without reading or changing one another's data. Restart and restore preserve their policies and audit history. |
| 2. Remote MCP pilot | Add a hosted remote MCP endpoint, authorization, tenant scoping, rate limits, and audit records. Keep the local stdio transport for development. Connect one external client end to end, beginning with Claude Code if access is available. Validate ChatGPT workspace plan and publishing requirements before adding it. The agent can author a proposal, read its summary and status, and link the customer to the Wallet. Confirmation and step-up resolution stay in the Wallet. | A real client creates a draft, the customer confirms or rejects it in the Wallet, and the client reads the resulting status for the same customer. |
| 3. Multi-task Wallet | Add a pending-draft inbox, a list of confirmed task mandates, and purchase activity across those mandates. Define list and action contracts first. Separate pending step-ups from finalized purchase decisions and link each step-up to one purchase. Resolve how multiple active mandates work with the payment provider before enabling them. | A customer can review two independent drafts and mandates. Confirming, rejecting, revoking, or answering a step-up for one does not change another. |
| 4. Global spending policies | Define account-level limits separately from task rules. Specify daily and monthly windows, timezone and reset boundaries, counted outcomes, pending purchase reservations, concurrent authorizations, and conflict behavior when a task policy is more permissive. Store versions and audit changes. Compose global and task rules into the effective policy and enforce them in the decision engine. | Manual boundary runs cover just-under, at-limit, and over-limit purchases, midnight and month-end, concurrent requests, declines, pending step-ups, and policy changes. Each result is recorded once and explained in the Wallet. |
| 5. Shopping Harness, one provider | Decide whether customers bring API credentials, authorize provider accounts, or use app-paid API access. A consumer chat subscription does not by itself establish API access. Build a provider-neutral chat and tool-call interface, then one adapter, such as Apertus when its endpoint and access are confirmed. Store credentials outside the browser, encrypted at rest, and redact them from logs. The agent may propose and inspect policies but cannot confirm them or resolve step-ups. Surface provider errors directly and do not switch providers automatically. | One configured provider completes a request, creates a draft through MCP, and hands the customer into the Wallet. Provider outages and authorization failures are visible. |
| 6. Policy controls and sliders | Add visual controls only for numeric rule fields with exact supported units, ranges, and semantics. Show the resulting plain-language rule, the agent's proposed value, example outcomes, and any unresolved question. Keep the saved draft and its version/hash authoritative. | Every slider value maps to the exact validated rule shown to the customer. Unsupported rules remain unavailable rather than being approximated. |
| 7. Production readiness | Add privacy and retention controls, account deletion, key rotation, backup recovery, abuse limits, service monitoring, cost controls, accessibility review, and an operator runbook. Review the public MCP tool list and customer authorization boundaries before launch. | A documented recovery exercise and a live end-to-end run complete with audit evidence and no cross-customer access. |

## Dependencies

- Customer identity and durable, tenant-scoped storage come before remote MCP and multi-task Wallet work.
- Remote MCP authorization must bind every tool call to the authenticated customer. A shared demo bearer token is not a production identity system.
- The payment provider's mandate behavior determines whether multiple active task policies can be supported and how purchases map to them.
- Global limits require defined accounting semantics and engine enforcement before the Wallet can offer controls.
- Provider credentials and billing choices come before provider adapters and the Harness.
- Slider controls follow the policy contract. The UI must not invent meanings the engine cannot enforce.

## Decisions to make before implementation

1. Which host, region, and identity provider will hold customer and policy data?
2. Does the Harness use customer-supplied API keys, provider authorization, or app-paid usage? Which first provider has confirmed access and acceptable terms?
3. Which events count toward daily and monthly limits? How are pending purchases reserved, and what timezone defines each period?
4. Does a customer have multiple active task mandates at once, and how does the payment provider identify the policy for each purchase?
5. What purchase information can external MCP clients read, and which tools require explicit customer authorization?

## Current boundary

The Friday demo stays on the narrower path recorded in [plan 01](../plans/01-policy-confirmation.md) and [plan 04](../plans/04-customer-app.md). It uses the standalone Wallet and an external MCP client. The built-in multi-provider Harness, draft and mandate lists, global spending controls, and sliders remain later work.
