# Expert round: one-minute pitch draft

Rishabh directs the final spoken pitch. Use [the six-slide deck](deck.html) for the one-minute pitch. The live demonstration requires its own time; adapt its claims to actual observed results. Rehearse the spoken script and slide advances together.

> An AI shopping agent can find what you want, but who decides what it may buy? Agent on a Leash gives the customer control in a Viseca Wallet. The agent proposes bounded rules through MCP. The customer confirms the saved policy; the agent receives only a mandate ID. Each purchase is checked against those rules, spending history and purchase facts. Merchant instructions cannot rewrite the policy. The engine approves, declines or requests a step-up, with an explanation. In an offline replay of 45 public attempts, 11 were approved, 32 declined and two left pending step-up. Correctness against reconciled labels remains unmeasured. We will show the actual live flow when ready.

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
- Use the closing live-demo sentence only if a fresh live run is ready. If it is not ready, end after the labels sentence; do not substitute a recorded demonstration. Reserve the live demonstration for a slot outside the one-minute pitch.
- Slides are authored as self-contained HTML. Open `docs/pitch/deck.html`, use the arrow keys or controls to advance, and use browser print for six pages. No screenshot or recording replaces the live demo.
