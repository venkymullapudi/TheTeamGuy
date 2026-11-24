# TheTeamGuy 🦸

> Every team has one. The person who knows where the wiki is, why the build is
> red, and which Slack channel the deploy bot moved to.
>
> Now they have a CLI.

`teamguy` reads a `team.yaml` describing **everything your team's go-to person
does** and turns it into an AI teammate named after your team. The guy is a
real member of the team. They:

- 🎒 **get onboarded**: meet the team, read the docs, learn the duties, meet the crew, ship a first task
- 🤝 **work with other agents, skills and LLMs**: hand pieces of a task to the crew, follow team playbooks, check the results
- 🎤 **join standups**: give a real update from their work log, listen, and volunteer for action items
- 📈 **level up**: every contribution earns XP, and each level unlocks more crew, more autonomy and more trust

The guy is named after your team:

| Team name       | Your guy               |
| --------------- | ---------------------- |
| `SIM`           | **TheSIMGuy**          |
| `Infra`         | **TheInfraGuy**        |
| `data platform` | **TheDataPlatformGuy** |
| `k8s-infra`     | **TheK8sInfraGuy**     |

This repo ships with [`team.yaml`](team.yaml) for team **SIM**, so meet
**TheSIMGuy**.

## Install

```bash
pip install -e '.[claude]'
```

The `claude` extra installs the Anthropic SDK (Python 3.10+), so the guy thinks
with Claude (`claude-opus-5-5` by default). Credentials come from
`ANTHROPIC_API_KEY` or `ant auth login`. Without it, use the **offline brain**:
scripted, free and deterministic. It works on Python 3.9+ and is great for demos
and CI.

```bash
pip install -e .
teamguy --brain offline onboard     # or: export TEAMGUY_BRAIN=offline
```

## A day in the life

```bash
teamguy onboard                                  # day one: quests, notes, +XP
teamguy work "write release notes for v2.3"      # the guy gets it done, with the crew
teamguy standup --join < updates.txt             # attends standup, volunteers for items
echo 'Sam: stuck on CI' >> .teamguy/standups/inbox.md  # async update for the next standup
teamguy work 3                                   # works a backlog item from standup
teamguy show 3                                   # read the deliverable and crew transcript
teamguy accept 3                                 # you sign off: the XP is paid out
teamguy reject 3 "missing the rollback steps"    # back to todo; the retry sees your note
teamguy unblock 4 "staging is back up"           # 🧱 blocked -> todo, with a hint for the retry
teamguy backlog note 5 "the runbook is in docs/oncall.md"  # 📎 context for a todo task's first try
teamguy backlog unnote 5 2                      # 🗑️ unpin note 2 (no number: list them)
teamguy backlog --stats                         # 📊 counts by status + days of caffeine left
teamguy backlog next                            # 👉 peek at what work --next picks (notes too)
teamguy backlog sweep --days 30                 # 🧹 archive done tasks accepted 30+ days ago
teamguy level                                    # 🎒 L1 Intern  ███████░░░  220/300 XP
teamguy kudos "saved the release"                # say thanks (+15 XP, they'll remember)
```

```
🛠️  TheSIMGuy picks up #2: Help Alex: fixing login bug, blocked on review
   📖 TheSIMGuy opens the 'ticket-triage' playbook
   🤝 TheSIMGuy → reviewer: Review the login fix in PR 481, focus on session handling…
   ↩️  reviewer: Two issues: the session cookie isn't marked Secure, and there's no test for…

👀 Ready for review: Reviewed Alex's login fix with the reviewer; flagged two issues on the PR.

   Worth +45 XP once you sign off: teamguy accept 2  (or: teamguy reject 2 "what to fix")

$ teamguy accept 2
🚢 #2 accepted! TheSIMGuy: "Reviewed by a real human. Framing this."

✨ +45 XP
★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
  LEVEL UP!  🔧  L2 Junior TheSIMGuy
  Unlocked: Can run team commands like the test suite.
★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★
```

## The teammate

### 🎒 Onboarding

`teamguy onboard` runs the quests a new hire would do:

| Quest               | What happens                                                      | XP |
| ------------------- | ----------------------------------------------------------------- | -- |
| 👋 Meet the team    | Learns the roster and posts a hello                               | 25 |
| 📚 Read the docs    | Reads `onboarding.docs` and writes notes for future reference     | 50 |
| 🗂️ Learn the duties | Studies every duty and plans the first two weeks                  | 25 |
| 🤖 Meet the crew    | Checks in with every agent and tool and sees what's installed     | 25 |
| 🚢 Ship a first task | Finishes a real task with `teamguy work`                         | 50 |

The notes the guy writes go into every prompt afterwards, so they remember what
they learned. Until onboarding is done, the guy stays a 🐣 **New Hire**.

### 🤝 Crew: other agents, LLMs and tools

The guy doesn't do everything alone. In `team.yaml`, `crew:` lists who they can
hand work to:

| Kind          | What it is                                                                   |
| ------------- | ---------------------------------------------------------------------------- |
| `llm`         | Another Claude persona with its own system prompt (reviewer, scribe, …)      |
| `command`     | A fixed command, like `[python3, -m, pytest, -q]`. The task arrives on stdin and in `$TEAMGUY_TASK`, never spliced into the command line |
| `claude-code` | Claude Code in headless mode (`claude -p`), with its own tools, subagents and skills. The task arrives on stdin and in `$TEAMGUY_TASK` |

Each crew member has a `min_level`. An Intern can ask the reviewer for a
second opinion, but only a Senior gets Claude Code.

#### 🔐 Claude Code permissions (`args:`)

Headless `claude -p` can't pause to ask "may I edit this file?", so anything you
didn't allow up front just gets refused. A `claude-code` member's `args:` list is
passed straight to `claude` (as a list, never a shell string; `-p` is added for
you):

```yaml
  - name: claude-code
    kind: claude-code
    command: [claude]
    args: [--permission-mode, acceptEdits]
```

| `args:`                                    | Can it…                          | Trade-off                                  |
| ------------------------------------------ | -------------------------------- | ------------------------------------------ |
| *(none)*                                   | read and suggest                 | safest; it can't change anything           |
| `[--permission-mode, acceptEdits]` *(default)* | edit files, no shell commands | good middle ground; review the diff        |
| `[--allowedTools, "Bash(pytest:*)", Edit]` | use exactly the tools you list   | tight and explicit, more upkeep            |
| `[--permission-mode, bypassPermissions]`   | do anything                      | only in a sandbox or throwaway checkout 🙈 |

`teamguy crew` shows each member's args so nobody's surprised.

### 📖 Skills: team playbooks

`skills/<name>/SKILL.md` files (the same shape as Claude Code skills) are
playbooks the guy opens and follows: `release-notes`, `postmortem`,
`flaky-test-hunt` and `ticket-triage` ship with the repo. Add your own; set
`min_level` in the frontmatter to gate them.

### 🎤 Standups

`teamguy standup` previews the guy's update, built from what they actually did
since the last workday. `teamguy standup --join` attends: it reads teammates'
updates (`Name: update` per line), offers help where it fits, and puts those
action items on the backlog. Notes are saved to `.teamguy/standups/`.

📬 **Standup inbox**: can't make the meeting? Drop your `Name: update` line in
`.teamguy/standups/inbox.md` any time. `--join` reads it (unless you pass
`--updates FILE`, which wins), then clears it so tomorrow starts fresh; add
`--keep-inbox` to leave it alone. With no file and an empty inbox, updates come
from stdin. The preview (`teamguy standup`) tells you who's already checked in.

😎 **Standup brag**: when there's something to brag about, the update ends with
one line: the streak this standup makes (2+ in a row) and any achievement
unlocked since the last standup. Each achievement gets bragged about once.

### 📈 Levels

| Level | Title                   | XP     | Unlocks                                            |
| ----- | ----------------------- | ------ | -------------------------------------------------- |
| 🐣 L0 | New Hire                | 0      | Beginner skills; must finish onboarding            |
| 🎒 L1 | Intern                  | 100    | LLM crew (reviewer, scribe, triager)               |
| 🔧 L2 | Junior TheSIMGuy        | 300    | Team commands (test-runner)                        |
| 🤝 L3 | Teammate                | 700    | Files their own follow-up tasks                    |
| 🧭 L4 | Senior TheSIMGuy        | 1,500  | Claude Code; more steps per task                   |
| 🏗️ L5 | Staff TheSIMGuy         | 3,000  | Picks their own work: `teamguy work --next`        |
| 🔮 L6 | Principal TheSIMGuy     | 6,000  | Everything                                         |
| 👑 L7 | Legendary TheSIMGuy     | 10,000 | Songs are sung                                     |

XP is earned, not self-reported: finished work lands in 👀 review, and only
`teamguy accept <id>` pays out the task XP. `teamguy reject <id> "why"` sends it
back to the backlog, and the guy sees every note on the next attempt. Stuck work
works the same way: `teamguy unblock <id> "creds are in the vault now"` moves a
🧱 blocked task back to todo with your note. Want to help before the first
try? `teamguy backlog note <id> "the logs are in Grafana"` pins context to a
todo task, and the guy reads every note before starting; `teamguy backlog`
marks those tasks with a 📎N count so you can see what's already got context. Standup,
onboarding and kudos XP stay automatic.

Work left in review doesn't get forgotten: after 2 days the standup blocker,
`teamguy backlog` and `teamguy recap` start nudging (⏳ "3 days and counting"),
and after 5 days the guy notes the 🕸️ cobwebs.

XP: **20 × effort** per accepted task, **+5** per crew member worked with,
**+10** per standup, **+5** per action item taken, **+15** per kudos, and **+5**
even for a blocked task (they learned something). Each level also gives the guy
more model turns per task.

### Streaks and achievements 🔥

`teamguy level` also shows bragging rights, all worked out from the journal:

- **Standup streak**: consecutive workdays with a standup (weekends don't break
  it; a missed workday does), plus his best ever.
- **🔥 On fire**: 5+ tasks accepted in the last 7 days.
- **Achievements**: 🚢 First Ship, 🥊 Comeback Kid (accepted after a reject),
  🧑‍✈️ Crew Chief (3+ crew on one task), ☕ Regular (5-standup streak),
  💌 Fan Favorite (3 kudos), 🏭 Shipyard (10 accepted). `accept` and `kudos`
  announce new ones the moment they unlock.

### Weekly recap 📰

`teamguy recap` prints the last 7 days as a short, plain-text post you can paste
straight into the team channel: tasks accepted, XP earned, standups and streak,
kudos, achievements unlocked this week, and anything still waiting on your
review. `--days 14` widens the window; `--date 2026-11-20` ends it on another day.

State (XP, backlog, journal, notes) lives in `.teamguy/state.json` next to
`team.yaml`. Every task also gets a work file at
`.teamguy/work/<id>-<slug>.md` with the final deliverable, the crew transcript
(who was asked what, and what came back) and the tokens it took. Read it with
`teamguy show <id>` before you accept or reject.

### Token budget 🪙

Every task has a token budget: `brain.task_token_budget` in `team.yaml`
(default 200,000) at L0, plus half again per level (L2 gets 2x, L7 gets 4.5x).
It counts the guy's own turns and his LLM crew calls. Once it's spent, LLM crew
hand-offs are refused, the guy stops before his next turn, and the task is
parked as 🧱 blocked with a note instead of quietly burning money. `teamguy
work` and the work file show tokens in/out and how much of the budget went.
Set it to `0` for no limit.

## Summon your guy

```bash
teamguy init SIM
```

```
✨ A wild TheSIMGuy appeared! (the-sim-guy)
   Wrote team.yaml. Edit it to teach TheSIMGuy everything they do,
   then try: teamguy whoami · teamguy today · teamguy card
```

## Commands

| Command                     | What it does                                                    |
| --------------------------- | --------------------------------------------------------------- |
| `teamguy onboard [--status]`| Run the onboarding quests                                       |
| `teamguy work "<task>"`     | Do a task (or `work <id>` from the backlog, `--next` at Staff+) |
| `teamguy standup [--join]`  | Preview the update, or attend and volunteer for action items    |
| `teamguy show <id>`         | The task's work file: deliverable, crew transcript, tokens      |
| `teamguy accept <id>`       | Sign off on finished work and grant the XP                      |
| `teamguy reject <id> "why"` | Send it back to todo with feedback for the next attempt         |
| `teamguy unblock <id> "note"`| Move 🧱 blocked work back to todo with a note the retry sees    |
| `teamguy backlog [add/drop/bump/effort/rename/find]`| The guy's task list (`bump <id>` puts a todo first in line, `effort <id> N` re-estimates it, `rename <id> "..."` rewords a todo or blocked one, `note <id> "..."` pins context the next attempt reads, `unnote <id> N` unpins note N (no N lists them), `find <words>` digs up tasks of any status by title or summary, `--stats` counts tasks by status and the coffees left in todo, `sweep [--days 30]` archives old done tasks; they stay in the journal, recaps, achievements, `find` and `show`) |
| `teamguy level`             | XP, level, what unlocks next, streaks and achievements          |
| `teamguy crew` / `skills`   | Who and what the guy works with (🔓/🔒 by level)                 |
| `teamguy kudos "<msg>"`     | Say thanks                                                      |
| `teamguy journal`           | Recent contributions                                            |
| `teamguy recap [--days N]`  | The week in review, ready to paste into the team channel        |
| `teamguy whoami`            | Banner, mission, level, and a catchphrase                       |
| `teamguy duties [-v]`       | Everything the guy does (`-v` adds checklists)                  |
| `teamguy duty <id>`         | One duty in detail, e.g. `teamguy duty release`                 |
| `teamguy today [--date]`    | Today's agenda plus a ☕ coffee forecast                         |
| `teamguy oncall [--weeks]`  | Who's holding the pager this week and the next few              |
| `teamguy ask "<question>"`  | Answers from the team FAQ                                       |
| `teamguy excuse`            | A battle-tested excuse for when things break                    |
| `teamguy card`              | A collectible trading card with very scientific stats           |
| `teamguy agent`             | Exports the guy as a **Claude Code subagent**                   |
| `teamguy validate`          | Checks `team.yaml` for mistakes                                 |

Use `-f path/to/team.yaml` to point at a different team, `--brain offline` to
skip the API, and `NO_COLOR=1` to turn colors off.

```
$ teamguy today
TheSIMGuy's agenda for Friday, Nov 20 2026
──────────────────────────────────────────
  🚒  On-Call Firefighter                      24/7/365 (send help)  ☕☕☕☕☕
  🙋  Official Answerer of Quick Questions     24/7/365 (send help)  ☕☕☕
  🎤  Standup Host                             every weekday  ☕
  🐑  PR Review Shepherd                       every weekday  ☕☕☕

  If summoned: 🤝 Onboarding Buddy, 📝 Postmortem Author

  Coffee forecast: ☕☕☕☕☕☕☕☕☕☕☕☕  (12 cups) — a respectable grind
```

```
$ teamguy ask "why is the build red"
  ❝ Why is the build red? ❞
💬 TheSIMGuy: Check the flaky-test quarantine list first. Then blame DNS. Then ask TheSIMGuy.
```

```
$ teamguy card
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ TheSIMGuy   ✦ ULTRA RARE
┃ Type: Ops / Glue / Psychic        HP: 508
┠──────────────────────────────────────────────────┨
┃ Tribal Knowledge  ███████████████████░  97
┃ Patience          ███░░░░░░░░░░░░░░░░░  17
┃ Slack Response    ███████████████████░  97
┃ Caffeine Intake   ████████████████████ 100  84/wk
┠──────────────────────────────────────────────────┨
┃ ⚡ Finds the right Confluence page in under 10 seconds
┃ ⚡ Knows every service's owner, even the ones nobody owns
┃ ⚡ Reads stack traces like bedtime stories
┃ 💀 Weak to: Meetings that could have been a Slack message
┃ 💀 Weak to: "Hey, got a sec?" with no follow-up
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

## The `team.yaml`

The whole persona lives in one file. Out of the box, the guy has 14 duties:

| Duty                                    | Cadence             | ☕     |
| --------------------------------------- | ------------------- | ----- |
| 🚒 On-Call Firefighter                  | always              | 5     |
| 🙋 Official Answerer of Quick Questions | always              | 3     |
| 🎤 Standup Host                         | weekdays            | 1     |
| 🐑 PR Review Shepherd                   | weekdays            | 3     |
| 🧙 Ticket Triage Wizard                 | Mon & Thu           | 2     |
| 🧪 Flaky Test Whisperer                 | Wednesdays          | 4     |
| 🚀 Release Captain                      | every other Tuesday | 4     |
| 🌱 Dependency Gardener                  | 1st of the month    | 3     |
| 📚 Keeper of the Wiki                   | every other Friday  | 2     |
| 🤝 Onboarding Buddy                     | on demand           | 3     |
| 🔁 Retro Facilitator                    | every other Friday  | 2     |
| 💸 Cloud Bill Watchdog                  | last day of month   | 2     |
| 📝 Postmortem Author                    | on demand           | 3     |
| 🎂 Chief Vibes Officer                  | quarterly           | 1     |

It also holds catchphrases, superpowers, kryptonite, the on-call roster, the
FAQ, standup blockers and excuses. Use `$TEAM` and `$GUY` in any text and they
get filled in for you.

```yaml
team: "SIM"
duties:
  - id: release
    title: "Release Captain"
    emoji: "🚀"
    cadence: biweekly:tue       # see cadences below
    effort: 4                   # coffee cups, 1–5
    description: "Cuts the release, writes the notes, and never deploys on a Friday."
    checklist:
      - "Freeze the branch and announce it loudly"
    catchphrase: "T-minus one coffee and counting."
```

### Cadences

| Cadence          | Means                                       |
| ---------------- | ------------------------------------------- |
| `always`/`daily` | every day                                   |
| `weekdays`       | Monday–Friday                               |
| `weekly:mon,thu` | those days every week                       |
| `biweekly:fri`   | that day, every even ISO week               |
| `monthly:15`     | that day of the month (`monthly:last` too)  |
| `quarterly`      | first Monday of Jan/Apr/Jul/Oct             |
| `on-demand`      | only when summoned                          |

## Use your guy as a Claude Code agent 🤖

```bash
teamguy agent
```

This writes `.claude/agents/the-sim-guy.md`: a Claude Code subagent that knows
every duty, checklist, and FAQ answer. Then ask Claude Code to "ask the-sim-guy
who owns this service". This repo includes the generated
[TheSIMGuy agent](.claude/agents/the-sim-guy.md).

## Development

```bash
pip install -e '.[dev]'
pytest
```

The tests use the offline brain and a fake Claude client, so they cost nothing.

Want proof the real brain works end to end? The live smoke test births a
throwaway TheSMOKEGuy in a temp folder and runs onboard → work → standup with
Claude. It spends a few real tokens, and skips politely (exit 0) when there's no
SDK or no `ANTHROPIC_API_KEY` (`TEAMGUY_SMOKE_FORCE=1` runs it anyway, `KEEP=1`
keeps the folder):

```bash
scripts/live_smoke.sh
```

## License

Apache 2.0. TheSIMGuy is not liable for any Friday deploys.
