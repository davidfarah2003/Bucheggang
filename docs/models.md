# Models and seats

David's machine runs a `jcode` harness with one provider that exposes many model families. Seats spawned from David's manager can use any of them; Oskar and Rishabh spawn `claude` seats from their own machines with their own subscriptions, and can ask David's main session to spawn a jcode seat for them into their lane (the seat joins the same channels either way).

## Catalog (jcode, provider `cliproxy`, ids are bare)

Declared in `~/.jcode/config.toml` on David's machine; `cotal models --agent jcode` prints it when a local manager runs. The cliproxy provider refuses effort tiers for every model we tried (Gemini, Opus), and a refused tier kills the seat at boot, so no persona sets `variant`.

| Family | Ids worth using | Efforts |
| --- | --- | --- |
| Anthropic | `claude-opus-5-5`, `claude-fable-5-1`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001` | low, medium, high, xhigh, max (haiku: none) |
| OpenAI | `gpt-6-sol`, `gpt-5.6-sol`, `gpt-5.5`, `gpt-5.4-mini` | per model |
| Google | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.5-flash-lite` | low, medium, high |
| xAI | `grok-4.7`, `grok-4.6`, `grok-4.20-0309-reasoning` | per model |
| Zhipu | `glm-5.3`, `glm-5.3-flash`, `glm-5.2` | per model |
| DeepSeek | `deepseek-v4-pro`, `deepseek-v4-flash` | low, high, max |
| Moonshot | `kimi-k3`, `kimi-k2.7-code` | per model |

The full list is in `~/.jcode/config.toml` (`grep '^id = '`).

## Assignment by role

| Persona | Default | Why | Other seats |
| --- | --- | --- | --- |
| `<lane>_builder` | `claude-opus-5-5` | strongest on multi-file Python | `gpt-6-sol` for a second builder in the same lane, so the two seats do not share blind spots |
| `reviewer` | `gemini-3.8-flash` (no effort tier; jcode refuses one for Gemini) | a different family from the builder; fast enough for one PR per spawn | `grok-4.7` for the security-shaped PRs (engine combine step, runner deadline guard) |
| `librarian` | `gemini-3.8-flash` | long context, cheap, stays up all event | |
| `labeler` | `grok-4.7` | independent from the builder family | the second labeler is `gpt-5.6-sol`; the two files are reconciled by a human |

Pair a builder with a reviewer from a different family. No model runs inside the product at purchase time (docs/idea, Decision pipeline); the seats above are the only models we run.

## Seat budget

20 to 30 seats are available on David's machine. Planned occupancy at peak:

- 5 lane builders (one per lane), plus at most 3 topic builders in engine, runner and app: 8
- reviewers: spawned per PR, at most 3 alive at once: 3
- librarian: 1
- labelers: 2 tonight, then 0
- humans' main sessions: 3

That is 17. The rest is headroom for a second reviewer on a contested PR or a respawn. Do not spawn a seat without a task and a stopping condition in its prompt.

## Spawning on David's manager for someone else's lane

From David's main session:

```
cotal_spawn(name: "policy_builder", cwd: ".worktrees/policy", model: "gpt-6-sol", variant: "high",
            prompt: "Do task 2 of docs/plans/01-policy-confirmation.md ...")
```

The seat joins `team.zurichbuchegg.policy` and reports there. The lane owner (Oskar) reads that channel from their own main session and re-briefs by posting on it with an `@policy_builder` mention. `cotal_despawn(name: ...)` only reaches your own seats, so the owner asks David on the spine when they want a seat David spawned stopped.
