# Cotal Lang for the pipeline work

Cotal Lang is a small JavaScript subset for coordinating agents over hours. A program is a flowchart: `spawn` a seat, `turn` it for one piece of work, `ask` it for a typed record, `checkpoint` for a human decision, `wait` for a channel message, and run branches with `parallel`, `race` and `fanOut`. Every effect is written to a journal before it runs, so a run survives the process that started it and resumes on any host. The docs are `cotal_docs(page: "workflows")` and `cotal_docs(page: "lang-card")`.

## Where it stands on our mesh, 2026-09-24

Hosted runs do not work on `zurichbuchegg`. The docs say user-auth meshes refuse them ("a user-auth mesh runs no programs yet: the manager refuses the family by name"), and a probe from `david_main` was refused by the broker before reaching a manager. The `--local` driver has no credential on a user-auth mesh either. So today a program cannot spawn, turn or checkpoint anything here.

What does work: the `@cotal-ai/lang` package installed with the CLI validates and simulates a program offline. `pipelines/review-and-merge.cotal.js` validates with zero problems. That means we can write and check the programs now and run them the moment one of these happens:

- the Cotal cloud host enables hosted runs for user-auth spaces, or
- we stand up a static-auth mesh of our own (`cotal up` on one machine, everyone joins with creds files) and run the pipelines there.

The second is a real option for Friday if the frozen manager is not cleared: a static mesh on David's machine, reachable over Tailscale or the venue LAN, gives us hosted runs, one manager, and detached jcode seats in one move. It costs a re-login for the three of us and new persona ACLs.

## What we would put in a program

The pipelines are the parts of the flow that are the same every time and that today a human relays by hand.

### 1. Review and merge (`pipelines/review-and-merge.cotal.js`)

One PR: spawn a reviewer bound to a worktree for that PR, `ask` it for a typed verdict (`{ verdict, sha, blockers }`), and if it approves at the exact head, `checkpoint` the merge for the lane owner. On resolve, a merger seat rebases and merges and posts the `merged:` line. The program refuses to merge on a stale SHA because the verdict record carries the SHA and the program compares it.

What it replaces: the owner watching `review`, checking the SHA matches, merging, and posting `merged:` by hand. Today that loop is done by `david_main` for Oskar's PRs and has already slipped twice on rebased heads.

### 2. Review fan-out

`fanOut(prs, review, { key: pr => pr.id })` runs pipeline 1 over every open PR at once, one reviewer seat each, and returns all verdicts. A blocked PR does not hold up the others.

### 3. Contract change

When a builder posts a proposal on `contracts`, a program `wait`s for `message("team.zurichbuchegg.contracts", { matches: "@<lane>_builder" })` from each affected builder with a timeout, then either opens the checkpoint for the owner (disagreement or silence) or turns a builder to land the PR. Replaces the "no answer after two tasks" rule with a real timer.

### 4. Task loop for a lane

`turn(builder, { name: "task-n", deadline: "45m" })` per plan task, in order, with the builder yielding `done`, `blocked` or `handoff`. On `blocked` the program `escalate`s to the owner as a checkpoint with the note attached. `permits: { turns, wallClock }` caps what a runaway seat can spend. Replaces the owner re-briefing a builder by hand after each task.

### 5. Deadline heartbeat

`race({ deadline: () => sleep("2h"), done: () => wait(message("team.zurichbuchegg.progress", { matches: "milestone: runner" })) })` posts a `deadline:` line if the milestone has not landed. Cheap, and it turns the timeline in AGENTS.md into something that fires.

## The typed verdict

Pipeline 1 uses `ask` with this schema, which the handler enforces:

```
{ verdict: "string", sha: "string", blockers: "array" }
```

`verdict` is `APPROVE` or `BLOCK`, `sha` is the full head graded, `blockers` is a list of one-line findings. The reviewer persona posts the same content on `review` for humans; the program reads the record, not the channel.

## Rules for programs here

- One program per pipeline in `pipelines/`, validated offline before it is committed: `node -e 'require("@cotal-ai/lang").validate(src)'` from the CLI's install (`/opt/homebrew/lib/node_modules/cotal-ai/node_modules/@cotal-ai/lang`).
- A merge is always a `checkpoint`. The program never merges without a named human resolving it.
- `permits` on every spawn. A seat with no turn or wall-clock budget is a seat we forgot.
- No fallback branches in a program either: a failed `ask` throws L4006 and the run holds for a human; it does not approve.
