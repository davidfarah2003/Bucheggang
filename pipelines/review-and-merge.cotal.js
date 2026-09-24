// One PR through review, a human merge gate, and the merge.
// The PR record is filled in per start (see docs/cotal-lang.md).
const pr = { number: 5, sha: "c118751", lane: "extract", owner: "oskar" }

const reviewer = await spawn("pr_reviewer", {
  worktree: `review-${pr.number}`,
  permits: { turns: 2, wallClock: "45m" },
})

const verdict = await ask(reviewer, {
  name: "verdict",
  schema: { verdict: "string", sha: "string", blockers: "array" },
  deadline: "40m",
  attempts: 2,
})

if (verdict.verdict === "APPROVE" && verdict.sha === pr.sha) {
  const gate = await checkpoint(
    "merge",
    `${pr.lane} PR #${pr.number} @${pr.sha} approved with no blockers. Merge it?`,
    { timeout: "3h", onExpiry: "fail" },
  )
  if (gate.status === "resolved") {
    const merger = await spawn("merger", { permits: { turns: 1, wallClock: "15m" } })
    const m = await turn(merger, { name: "merge", deadline: "10m" })
    log("merged", pr.number, m.status)
  }
} else {
  log("blocked", pr.number, verdict.sha, verdict.blockers.length)
}
