# Improvement roadmap

The improvement loop (a scheduled task in the Claude desktop app on the owner's
Mac, every 3 hours at :39) works through this list
top to bottom, one item per run. Only one run works at a time: every run, cloud
or local, takes the `teamguy-loop-lock` branch via `scripts/improve_lock.sh`.
Each run implements an item with tests, ticks the box, commits and pushes to
`main`. Edit freely: reorder, add or delete items, and the loop follows.

Choices marked *(default)* were the recommended answers to design questions
nobody has answered yet. Change them here if you disagree.

## Now

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
- [x] Fix: standup attendance XP keyed to the meeting day, not the wall clock
  (a standup for another date no longer pays out twice; fixed the red baseline).
- [x] Earned XP: finished tasks go to 👀 review; `teamguy accept <id>` pays the
  XP, `teamguy reject <id> "why"` sends it back with feedback the retry sees.
- [x] Deliverables are saved: each task writes `.teamguy/work/<id>-<slug>.md`
  (deliverable, crew transcript, tokens); `teamguy show <id>` prints it.
- [x] Token budget: `brain.task_token_budget` (default 200k at L0, +50% per
  level, 0 = no limit) caps the guy's turns plus LLM crew per task; past it the
  task is parked as blocked, and `teamguy work` / the work file report usage.
