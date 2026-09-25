# Expert round: one-minute pitch draft

Rishabh directs the final spoken pitch. Use [the six-slide deck](deck.html) with the live demonstration and adapt the spoken result to what actually happens. This script is approximately 120 words; rehearse against the one-minute slot.

> An AI shopping agent can find what you want, but who decides what it may buy? Agent on a Leash puts a Viseca Wallet control layer between the agent and the purchase. The agent proposes a bounded task policy through MCP. The customer sees the saved rules in the Wallet and confirms them. The agent gets a mandate ID, never permission to approve its own exceptions. For each purchase, our engine checks the confirmed policy, spending history and purchase facts. Merchant instructions cannot rewrite the rules. It approves, declines or asks the customer, with an explanation. In our offline replay of 45 public attempts, 11 were approved, 32 declined and two escalated. We have not yet measured correctness against reconciled labels. Now we will show the actual live customer flow and its result.

## Presenter cues

| Slide | Cue | Source or limit |
| --- | --- | --- |
| 1 | Customer control over delegated shopping | [Product design](../idea/viseca-agent-control-layer.md) |
| 2 | MCP draft, Wallet confirmation, opaque mandate | [MCP and Wallet local verification](../eval/local-app-e2e-2026-09-25.md) covers a pending draft and read-back, not a completed confirmation |
| 3 | Structured purchase and explainable action | [Decision pipeline](../idea/viseca-agent-control-layer.md#decision-pipeline); show the actual live event if available |
| 4 | 45 offline: 11 approve, 32 decline, 2 step-up; 43/45 initially autonomous | [Report decisions table](../eval/report.md#decisions-by-scenario). Labels pending, so do not call these correct or safe purchases |
| 5 | Demonstrate observed live flow only | [Live checklist](../live-demo-checklist.md). Public attempt IDs do not select a live scenario |
| 6 | Bounded permission and next evidence | [Report verification gaps](../eval/report.md#verification-still-required) |

## Evidence and presentation limits

- The report's latency p50 and p99 describe local offline extraction and evaluation only. Do not use them as network or end-to-end payment latency.
- The two annotated merchant-instruction attempts in the report were declined or escalated. They do not measure success against all manipulated purchases.
- The current live simulator report records declines and one platform timeout. A completed human Wallet step-up, two complete live runs and labelled error rate are not established. Use a fresh actual outcome when presenting.
- Slides are authored as self-contained HTML. Open `docs/pitch/deck.html`, use the arrow keys or controls to advance, and use browser print for six pages. No screenshot or recording replaces the live demo.
