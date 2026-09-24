#!/usr/bin/env bash
# Spawn one agent for one lane on the team mesh, rooted in that lane's worktree.
#
#   scripts/spawn.sh <persona> <lane|-> "<brief>" [--model <id>] [--variant <tier>] [--detach]
#
#   persona  a file in .cotal/agents/ without .md: builder, reviewer, librarian, labeler
#   lane     policy | engine | extract | app | runner, or - for no lane (librarian, labeler)
#   brief    the spawn prompt: the task, where to stop, where to report
#
# The persona file fixes the harness, the default model and the channels. --model and
# --variant override the model for this seat only (see docs/models.md for the catalog).
# The worktree and branch are created on first use. Never two builders in one worktree:
# for a second builder in a lane, pass a topic branch name as the lane, e.g. engine-spend.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
persona="${1:?persona}"; lane="${2:?lane or -}"; brief="${3:?brief}"; shift 3
space="${COTAL_SPACE:-zurichbuchegg}"

[ -f "$repo/.cotal/agents/$persona.md" ] || { echo "no persona .cotal/agents/$persona.md" >&2; exit 1; }

# Seat names must be lowercase [a-z0-9_]: no dots, no hyphens (the mesh refuses them).
if [ "$lane" = "-" ]; then
  cwd="$repo"; name="$persona"
else
  base="${lane%%-*}"                       # engine-spend -> engine
  cwd="$repo/.worktrees/$lane"; name="${base}_${persona}"
  if [ ! -d "$cwd" ]; then
    git -C "$repo" fetch -q origin
    if git -C "$repo" show-ref -q "refs/heads/lane/$lane"; then
      git -C "$repo" worktree add -q "$cwd" "lane/$lane"
    else
      git -C "$repo" worktree add -q -b "lane/$lane" "$cwd" origin/main
    fi
    echo "created worktree $cwd on lane/$lane"
  fi
fi

# Detached by default: only a manager-spawned seat can stand itself down with cotal_despawn,
# and only a detached seat is listed by `cotal ps` and stoppable with `cotal stop`. Pass
# --foreground to watch the TUI in this terminal instead (then stop it with ctrl-c).
mode="--detach"
for a in "$@"; do [ "$a" = "--foreground" ] && mode=""; done
set -- "${@/--foreground/}"

exec cotal spawn "$persona" --space "$space" --config "$repo/.cotal/agents/$persona.md" \
  --name "$name" --cwd "$cwd" --prompt "$brief" $mode "$@"
