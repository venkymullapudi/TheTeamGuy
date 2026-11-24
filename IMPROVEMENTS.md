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

_(empty: the loop takes from Next)_

## Next

- [ ] Quick wins: `teamguy backlog quick` lists todo tasks of 1 ☕ (the "I have
  ten minutes" menu) with their XP and a nudge to bump one.
- [ ] Swap: `teamguy backlog swap <a> <b>` trades the line positions of two todo
  tasks (finer than bump/sink), with a do-si-do quip.

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
- [x] Claude Code crew args: `claude-code` members take `args:` (default
  `--permission-mode acceptEdits`), the task now goes on stdin instead of argv,
  `teamguy crew` shows the args, and the README explains the permission trade-offs.
- [x] Standup inbox: `--join` reads `.teamguy/standups/inbox.md` when no
  `--updates` file is given, clears it afterwards (`--keep-inbox` to keep), and
  the preview shows who has already checked in.
- [x] Live smoke test: `scripts/live_smoke.sh` runs onboard → work → standup
  with the Claude brain in a temp dir; skips (exit 0) with no SDK or no
  API key/auth token in the env (OAuth tokens don't count), `TEAMGUY_SMOKE_FORCE=1`
  overrides, `KEEP=1` keeps the folder. Tests cover the skip paths with a fake binary.
- [x] Streaks and fun: `teamguy level` shows a workday standup streak (and best),
  a 🔥 on-fire badge (5+ tasks accepted in 7 days) and six achievements derived
  from the journal; `accept` and `kudos` announce newly unlocked ones.
- [x] Weekly recap: `teamguy recap` prints a pasteable, colorless week in review
  (accepted tasks, XP, standups and streak, kudos, achievements new this week,
  tasks waiting for review); `--days` and `--date` move the window.
- [x] Brag at standup: the standup update ends with a one-line brag (streak this
  standup makes, achievements unlocked since the last standup, each bragged once);
  `fun.as_of` now also takes an ISO timestamp cutoff.
- [x] Backlog bump: `teamguy backlog bump <id>` moves a todo task to the front
  of the line so `work --next` picks it first (review/done/blocked can't cut in).
- [x] Review nudges: tasks sitting in 👀 review for 2+ days get "⏳ N days and
  counting" (🕸️ cobwebs at 5+) in standup blockers and `teamguy backlog`; the
  recap names the oldest one. `State.review_age` counts the days.
- [x] Unblock: `teamguy unblock <id> "note"` moves a 🧱 blocked task back to todo;
  the retry's prompt and work file carry the notes, and blocked `work` runs hint at it.
- [x] Re-estimate: `teamguy backlog effort <id> N` changes a todo task's effort
  (1–5 ☕) and shows the XP change; growing past 3 ☕ gets a cheeky quip.

- [x] Rename: `teamguy backlog rename <id> "new title"` rewords a todo or blocked
  task (old names kept under `renamed`); review/done tasks keep their names.
- [x] Backlog search: `teamguy backlog find <words>` lists tasks of any status
  whose title, old names or summary contain every word (case-insensitive).
- [x] Task notes: `teamguy backlog note <id> "..."` pins context to a todo task;
  the work prompt and work file include every note (blocked/review get a hint).
- [x] Show notes: `teamguy backlog` marks todo tasks that carry notes with a 📎N
  count (review/done/blocked stay clean).
- [x] Backlog stats: `teamguy backlog --stats` counts tasks by status (plus a
  total) and sums the ☕ left in todo, quipping how many days of caffeine that is (4 ☕/day).
- [x] Peek next: `teamguy backlog next` shows the task `work --next` would pick
  (☕, XP, pinned notes, how many wait behind it) without starting it.
- [x] Unnote: `teamguy backlog unnote <id> N` unpins note N from a todo task;
  no N (or an out-of-range one) lists the numbered notes.
- [x] Sweep: `teamguy backlog sweep [--days 30]` moves done tasks accepted N+ days
  ago into an archive (journal entry, tidy-up quip); recaps, achievements, `find`,
  `show` and `--stats` still see them, and archived ids are never reused.

- [x] Sink: `teamguy backlog sink <id>` sends a todo task to the back of the line
  (behind every other todo), the opposite of `bump`; review/done/blocked can't.
- [x] Stale todos: `teamguy backlog stale [--days 14]` lists todo tasks created
  N+ days ago, dustiest first, with a 🕸️ quip and a bump/sink/drop nudge.
- [x] Unsweep: `teamguy backlog unsweep <id>` brings an archived task back into
  the backlog (still done, back in id order) with a journal entry and a sheepish quip.
- [x] Roll: `teamguy backlog roll` picks a random todo task and bumps it to the
  front of the line (🎲 quip; review/done/blocked never roll; one todo is "rigged").
