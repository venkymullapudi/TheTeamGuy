# Improvement roadmap

The improvement loop (a cloud routine, every 3 hours) works through this list
top to bottom, one item per run. Only one run works at a time: every run, cloud
or local, takes the `teamguy-loop-lock` branch via `scripts/improve_lock.sh`.
Each run implements an item with tests, ticks the box, commits and pushes to
`main`. Edit freely: reorder, add or delete items, and the loop follows.

Choices marked *(default)* were the recommended answers to design questions
nobody has answered yet. Change them here if you disagree.

## Now

- [ ] **Earned XP, not self-reported XP** *(default: human accepts)*. A finished
  task goes to `review` instead of `done`. `teamguy accept <id>` grants the XP;
  `teamguy reject <id> "why"` sends it back to `todo` with the feedback, and the
  next attempt sees it in the prompt. Standup, onboarding and kudos XP stay
  automatic.
- [ ] **Deliverables are saved** *(default: work files)*. Each task writes
  `.teamguy/work/<id>-<slug>.md`: the final deliverable, the crew transcript
  (who was asked what, what came back), and tokens used. `teamguy show <id>`
  prints it.
- [ ] **Token budget** *(default: per-task budget that grows with level)*. Count
  input/output tokens across the guy's own calls and his LLM crew calls, report
  them per task, and stop gracefully when a task goes past
  `brain.task_token_budget` (scaled by level).
- [ ] **Claude Code crew args**: let `claude-code` members set `args:` (for
  example `--permission-mode`, `--allowedTools`) and document the trade-offs.
  Headless `claude -p` can't stop to ask for permissions.

## Next

- [ ] **Standup inbox**: `teamguy standup --join` reads
  `.teamguy/standups/inbox.md` by default, then clears it, so teammates can drop
  updates in asynchronously.
- [ ] **Live smoke test**: `scripts/live_smoke.sh` runs onboard → work →
  standup with the Claude brain in a temp dir and skips cleanly when there are
  no credentials.
- [ ] **Streaks and fun**: a standup streak, a "🔥 on fire" badge for a week of
  accepted work, and an achievement or two in `teamguy level`.

## Done

- [x] `team.yaml` with all the guy's duties; `The<Team>Guy` naming.
- [x] Crew (llm / command / claude-code), skills, work loop, standups,
  onboarding, levels L0–L7.
- [x] Clear error for an OAuth token in `ANTHROPIC_API_KEY` (`18b101c`).
