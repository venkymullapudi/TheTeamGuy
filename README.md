# TheTeamGuy 🦸

> Every team has one. The person who knows where the wiki is, why the build is
> red, and which Slack channel the deploy bot moved to.
>
> Now they have a CLI.

`teamguy` reads a `team.yaml` describing **everything your team's go-to person
does** and turns it into a persona named after your team:

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
pip install -e .
```

Requires Python 3.9+ (and PyYAML, which gets installed for you).

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
| `teamguy whoami`            | Banner, mission, and a catchphrase                              |
| `teamguy duties [-v]`       | Everything the guy does (`-v` adds checklists)                  |
| `teamguy duty <id>`         | One duty in detail, e.g. `teamguy duty release`                 |
| `teamguy today [--date]`    | Today's agenda plus a ☕ coffee forecast                         |
| `teamguy standup [--date]`  | An auto-generated standup (same day = same standup)             |
| `teamguy oncall [--weeks]`  | Who's holding the pager this week and the next few              |
| `teamguy ask "<question>"`  | Answers from the team FAQ                                       |
| `teamguy excuse`            | A battle-tested excuse for when things break                    |
| `teamguy card`              | A collectible trading card with very scientific stats           |
| `teamguy agent`             | Exports the guy as a **Claude Code subagent**                   |
| `teamguy validate`          | Checks `team.yaml` for mistakes                                 |

Use `-f path/to/team.yaml` to point at a different team. Set `NO_COLOR=1` to
turn colors off.

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

## License

Apache 2.0. TheSIMGuy is not liable for any Friday deploys.
