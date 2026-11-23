"""`teamguy` — summon The<Team>Guy from the command line."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, persona
from .brain import BrainError, make_brain
from .config import Team, TeamConfigError, guy_name, guy_slug, load_team, render_template
from .levels import AUTOPICK_LEVEL, LADDER, XP, next_level, progress_bar
from .state import Award, State, stats


def _date(value: str) -> dt.date:
    if value == "tomorrow":
        return dt.date.today() + dt.timedelta(days=1)
    if value == "today":
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD, 'today' or 'tomorrow'") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="teamguy",
        description="Every team has a guy. Summon yours. (Reads team.yaml.)",
    )
    p.add_argument("--version", action="version", version=f"teamguy {__version__}")
    p.add_argument("-f", "--file", type=Path, default=Path("team.yaml"), help="path to team.yaml (default: ./team.yaml)")
    p.add_argument("--brain", choices=["claude", "offline"], help="override brain.provider from team.yaml")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    s = sub.add_parser("init", help="create team.yaml and birth The<TEAM>Guy")
    s.add_argument("team", help="your team's name, e.g. SIM")
    s.add_argument("--force", action="store_true", help="overwrite an existing team.yaml")

    sub.add_parser("whoami", help="meet your guy")

    s = sub.add_parser("duties", help="list everything the guy does")
    s.add_argument("-v", "--verbose", action="store_true", help="include checklists")

    s = sub.add_parser("duty", help="details for a single duty")
    s.add_argument("id")

    s = sub.add_parser("today", help="what's on the guy's plate today")
    s.add_argument("--date", type=_date, default=dt.date.today())

    s = sub.add_parser("standup", help="the guy's standup update; --join to attend with the team")
    s.add_argument("--date", type=_date, default=dt.date.today())
    s.add_argument("--join", action="store_true", help="attend: hear teammates' updates and volunteer for action items")
    s.add_argument("--updates", type=Path,
                   help="file of 'Name: update' lines (default: .teamguy/standups/inbox.md if it has any, else stdin)")
    s.add_argument("--keep-inbox", action="store_true", help="don't clear the inbox after reading it")

    s = sub.add_parser("work", help="give the guy a task (text or backlog #id) and watch them get it done")
    s.add_argument("task", nargs="*", help='e.g. "write release notes for v2.3" or 4')
    s.add_argument("--next", action="store_true", help="pick the next backlog task (Staff+ only)")
    s.add_argument("--effort", type=int, default=2, help="1 (tiny) to 5 (huge), for new tasks")

    s = sub.add_parser("accept", help="sign off on finished work and grant the XP")
    s.add_argument("id", type=int)
    s = sub.add_parser("reject", help="send finished work back to todo with feedback")
    s.add_argument("id", type=int)
    s.add_argument("why", nargs="+", help="what to fix; the next attempt sees it")

    s = sub.add_parser("unblock", help="send blocked work back to todo with a note that clears the way")
    s.add_argument("id", type=int)
    s.add_argument("note", nargs="+", help="what changed or how to get past it; the next attempt sees it")

    s = sub.add_parser("show", help="print a task's work file: deliverable, crew transcript, tokens")
    s.add_argument("id", type=int)

    s = sub.add_parser("backlog", help="the guy's task list")
    bsub = s.add_subparsers(dest="backlog_cmd", metavar="<action>")
    b = bsub.add_parser("add", help="add a task")
    b.add_argument("title", nargs="+")
    b.add_argument("--effort", type=int, default=2)
    b = bsub.add_parser("drop", help="remove a task")
    b.add_argument("id", type=int)
    b = bsub.add_parser("bump", help="move a task to the top so work --next picks it first")
    b.add_argument("id", type=int)
    b = bsub.add_parser("effort", help="re-estimate a todo task: 1 (tiny) to 5 (huge) coffees")
    b.add_argument("id", type=int)
    b.add_argument("effort", type=int)
    b = bsub.add_parser("rename", help="reword a todo or blocked task")
    b.add_argument("id", type=int)
    b.add_argument("title", nargs="+")
    b = bsub.add_parser("note", help="pin extra context to a todo task; the next attempt reads it")
    b.add_argument("id", type=int)
    b.add_argument("note", nargs="+")
    b = bsub.add_parser("find", help="search tasks of any status by title or summary")
    b.add_argument("words", nargs="+")
    s.add_argument("--all", action="store_true", help="include finished tasks")
    s.add_argument("--stats", action="store_true", help="counts by status and coffees left in todo")

    s = sub.add_parser("onboard", help="run the guy's onboarding quests")
    s.add_argument("--status", action="store_true", help="just show progress")

    sub.add_parser("level", help="career level, XP and what unlocks next")
    sub.add_parser("crew", help="the agents, LLMs and tools the guy works with")
    sub.add_parser("skills", help="the team playbooks the guy can use")
    s = sub.add_parser("kudos", help="say thanks (+XP)")
    s.add_argument("message", nargs="*")
    s = sub.add_parser("recap", help="the last week in one pasteable post for the team channel")
    s.add_argument("--days", type=int, default=7, help="how many days back (default 7)")
    s.add_argument("--date", type=_date, default=dt.date.today(), help="last day of the recap")
    s = sub.add_parser("journal", help="recent contributions")
    s.add_argument("-n", type=int, default=15)

    s = sub.add_parser("oncall", help="who's holding the pager")
    s.add_argument("--date", type=_date, default=dt.date.today())
    s.add_argument("--weeks", type=int, default=4, help="how many weeks to show")

    s = sub.add_parser("ask", help="ask the guy a question")
    s.add_argument("question", nargs="+")

    sub.add_parser("excuse", help="a battle-tested excuse")
    sub.add_parser("card", help="the guy's collectible trading card")

    s = sub.add_parser("agent", help="export the guy as a Claude Code subagent")
    s.add_argument("-o", "--output", type=Path, help="default: .claude/agents/<the-team-guy>.md")
    s.add_argument("--stdout", action="store_true", help="print instead of writing a file")

    sub.add_parser("validate", help="check team.yaml for problems")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0

    try:
        if args.cmd == "init":
            return _init(args)

        team = load_team(args.file)

        if args.cmd == "whoami":
            print(persona.whoami(team))
        elif args.cmd == "duties":
            print(persona.duties_list(team, verbose=args.verbose))
        elif args.cmd == "duty":
            duty = team.duty(args.id)
            if not duty:
                print(f"{team.guy} doesn't do {args.id!r}. Yet. Known: {', '.join(d.id for d in team.duties)}", file=sys.stderr)
                return 1
            print(persona.duty_detail(duty))
        elif args.cmd == "today":
            print(persona.today(team, args.date))
        elif args.cmd == "standup":
            return _standup(team, args)
        elif args.cmd in ("work", "accept", "reject", "unblock", "show", "backlog", "onboard", "level", "crew", "skills", "kudos", "journal", "recap"):
            return _teammate(team, args)
        elif args.cmd == "oncall":
            print(persona.oncall(team, args.date, max(1, args.weeks)))
        elif args.cmd == "ask":
            print(persona.ask(team, " ".join(args.question)))
        elif args.cmd == "excuse":
            print(persona.excuse(team))
        elif args.cmd == "card":
            print(persona.card(team))
        elif args.cmd == "agent":
            md = persona.agent_markdown(team)
            if args.stdout:
                print(md)
            else:
                out = args.output or Path(".claude/agents") / f"{team.slug}.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(md, encoding="utf-8")
                print(f"🤖 {team.guy} has been uploaded to {out}. Ask Claude Code for '{team.slug}'.")
        elif args.cmd == "validate":
            print(f"✅ {args.file} looks great. {team.guy} has {len(team.duties)} duties and {len(team.faq)} FAQs.")
    except TeamConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except BrainError as exc:
        print(f"🧠❌ {exc}", file=sys.stderr)
        return 3
    return 0


# ─── teammate commands ───────────────────────────────────────────────────────


def _level_line(team: Team, state: State) -> str:
    lvl = state.level
    return f"  {lvl.badge}  L{lvl.number} {lvl.name(team.guy)}   {progress_bar(state.xp, lvl)}"


def _announce(team: Team, awards: List[Optional[Award]]) -> None:
    awards = [a for a in awards if a]
    total = sum(a.xp for a in awards)
    if total:
        print(persona.c(f"\n✨ +{total} XP", "bold", "green"))
    for a in awards:
        if a.leveled_up:
            print(persona.level_up(team, a.after))


def _new_achievements(state: State, had: set) -> None:
    from . import fun

    for a in fun.unlocked(state):
        if a.key not in had:
            print(persona.c(f"🏆 Achievement unlocked: {a.emoji} {a.title}. {a.blurb}", "bold", "magenta"))


def _standup(team: Team, args: argparse.Namespace) -> int:
    from .meeting import inbox_path, join_standup, parse_updates, render_update

    state = State.load(team)
    inbox = inbox_path(team)
    waiting = parse_updates(inbox.read_text(encoding="utf-8")) if inbox.is_file() else []
    if not args.join:
        print(render_update(team, state, args.date))
        if waiting:
            print(persona.c(f"\n  📬 {len(waiting)} update(s) waiting in the inbox from "
                            f"{', '.join(sorted({n for n, _ in waiting}))}.", "dim"))
        print(persona.c("\n  (Preview. `teamguy standup --join` to actually attend.)", "dim"))
        return 0
    from_inbox = False
    if args.updates:
        text = args.updates.read_text(encoding="utf-8")
    elif waiting:
        text = inbox.read_text(encoding="utf-8")
        from_inbox = True
        print(persona.c(f"📬 {len(waiting)} update(s) from the inbox. The async crowd has spoken.", "dim"))
    elif sys.stdin.isatty():
        print("Teammates, go! One 'Name: update' per line, blank line to finish.")
        lines = []
        for line in iter(input, ""):
            lines.append(line)
        text = "\n".join(lines)
    else:
        text = sys.stdin.read()
    brain = make_brain(team, args.brain)
    report = join_standup(team, state, brain, parse_updates(text), args.date)
    print()
    print(report.reply)
    print(persona.c(f"\n  📝 Notes saved to {report.notes_path}", "dim"))
    if from_inbox and not args.keep_inbox:
        inbox.write_text("", encoding="utf-8")
        print(persona.c(f"  📭 Inbox cleared ({inbox}). Fresh for tomorrow.", "dim"))
    _announce(team, report.awards)
    return 0


def _teammate(team: Team, args: argparse.Namespace) -> int:
    from . import fun
    from .crew import available, load_skills
    from .onboarding import quest_status, run_onboarding
    from .work import budget_line, work_on

    state = State.load(team)

    if args.cmd == "level":
        lvl = state.level
        done, standups, open_ = stats(state)
        print(persona.c(f"{team.guy}'s career", "bold"))
        print(_level_line(team, state))
        print(f"  {lvl.perk_for(team.guy)}")
        nxt = next_level(lvl)
        if not state.onboarded:
            print(persona.c("  🔒 Finish onboarding (`teamguy onboard`) to leave New Hire.", "yellow"))
        elif nxt:
            print(persona.c(f"  Next: L{nxt.number} {nxt.name(team.guy)} → {nxt.perk_for(team.guy)}", "dim"))
        print(f"\n  Tasks shipped: {done}   Standups: {standups}   Open tasks: {open_}")
        print(fun.streak_line(state))
        got = {a.key for a in fun.unlocked(state)}
        print(persona.c(f"\n  Achievements ({len(got)}/{len(fun.ACHIEVEMENTS)})", "bold"))
        for a in fun.ACHIEVEMENTS:
            if a.key in got:
                print(f"  {a.emoji} {a.title:<14} {persona.c(a.blurb, 'dim')}")
            else:
                print(persona.c(f"  🔒 {a.title:<14} {a.blurb}", "dim"))
        print()
        for l in LADDER:
            mark = "▶" if l.number == lvl.number else ("✓" if l.number < lvl.number else " ")
            print(persona.c(f"  {mark} {l.badge} L{l.number} {l.name(team.guy):<26} {l.xp:>6} XP", "bold" if mark == "▶" else "dim"))
        return 0

    if args.cmd == "onboard":
        if not args.status and not state.onboarded:
            print(persona.c(f"🎒 Day one for {team.guy}. Badge photo: terrible. Enthusiasm: maximum.", "bold"))
            _announce(team, run_onboarding(team, state, make_brain(team, args.brain)))
        print(persona.c("\nOnboarding checklist", "bold"))
        for quest, done in quest_status(state):
            print(f"  {'✅' if done else '⬜'} {quest.emoji} {quest.title:<20} +{quest.xp} XP  {persona.c(quest.blurb, 'dim')}")
        if state.onboarded:
            print(persona.c(f"\n🎓 {team.guy} is fully onboarded.", "green"))
        elif "first-task" not in state.data["onboarding"]:
            print(persona.c('\n  Last step: give them a real task, e.g. teamguy work "triage the open tickets"', "yellow"))
        return 0

    if args.cmd == "crew":
        lvl = state.level.number
        print(persona.c(f"{team.guy}'s crew", "bold"))
        if not team.crew:
            print("  Nobody yet. Add agents and tools under `crew:` in team.yaml.")
        for m in team.crew:
            lock = "🔓" if m.min_level <= lvl else f"🔒 L{m.min_level}"
            reason = available(m)
            print(f"  {lock:<6} {persona.c(m.name, 'bold'):<14} {m.kind:<12} {m.description}"
                  + (persona.c(f"  ({reason})", "yellow") if reason else ""))
            if m.args:
                print(persona.c(f"         ↳ runs with: {' '.join(m.args)}", "dim"))
        return 0

    if args.cmd == "skills":
        skills = load_skills(team)
        print(persona.c(f"Playbooks in {team.skills_dir}/", "bold"))
        if not skills:
            print("  None yet. Add skills/<name>/SKILL.md files.")
        for sk in skills:
            lock = "🔓" if sk.min_level <= state.level.number else f"🔒 L{sk.min_level}"
            print(f"  {lock:<6} {persona.c(sk.name, 'bold')}: {sk.description}")
        return 0

    if args.cmd == "kudos":
        msg = " ".join(args.message) or "Great job!"
        had = {a.key for a in fun.unlocked(state)}
        award = state.award("kudos", XP["kudos"], f"Kudos: {msg}")
        state.save()
        print(f"🥹 {team.guy}: Thank you! That means a lot. (Saving this one for my promo packet.)")
        _announce(team, [award])
        _new_achievements(state, had)
        return 0

    if args.cmd == "recap":
        print(fun.recap(team.guy, state, args.date, args.days))
        return 0

    if args.cmd == "journal":
        print(persona.c(f"{team.guy}'s journal", "bold"))
        for e in state.data["log"][-args.n:]:
            print(f"  {e['at'][:16].replace('T', ' ')}  +{e['xp']:<4} {e['summary']}")
        if not state.data["log"]:
            print("  Empty. Try `teamguy onboard`.")
        return 0

    if args.cmd in ("accept", "reject"):
        t = state.task(args.id)
        if not t:
            print(f"No task #{args.id}.", file=sys.stderr)
            return 1
        if t["status"] != "review":
            print(f"#{t['id']} isn't waiting for review (it's {t['status']}).", file=sys.stderr)
            return 1
        if args.cmd == "accept":
            had = {a.key for a in fun.unlocked(state)}
            award = state.accept_task(t)
            state.save()
            print(f"🚢 #{t['id']} accepted! {team.guy}: \"Reviewed by a real human. Framing this.\"")
            _announce(team, [award])
            _new_achievements(state, had)
            if fun.on_fire(state):
                print(persona.c("🔥 On fire this week. `teamguy level` for the receipts.", "bold", "yellow"))
        else:
            why = " ".join(args.why)
            state.reject_task(t, why)
            state.save()
            print(f"↩️  #{t['id']} is back on the backlog. {team.guy}: \"Fair. Taking notes: {why}\"")
            print(persona.c(f"   Try again: teamguy work {t['id']}", "dim"))
        return 0

    if args.cmd == "unblock":
        t = state.task(args.id)
        if not t:
            print(f"No task #{args.id}.", file=sys.stderr)
            return 1
        if t["status"] != "blocked":
            print(f"#{t['id']} isn't blocked (it's {t['status']}). Nothing to knock down.", file=sys.stderr)
            return 1
        note = " ".join(args.note)
        state.unblock_task(t, note)
        state.save()
        print(f"🧱💥 #{t['id']} is unblocked and back on the backlog. {team.guy}: \"Oh, THAT's the trick. Noted: {note}\"")
        print(persona.c(f"   Go again: teamguy work {t['id']}", "dim"))
        return 0

    if args.cmd == "show":
        t = state.task(args.id)
        if not t:
            print(f"No task #{args.id}.", file=sys.stderr)
            return 1
        path = team.state_dir / t["work_file"] if t.get("work_file") else None
        if not path or not path.exists():
            print(f"#{t['id']} has no work file yet ({t['status']}). {team.guy} hasn't touched it. Try: teamguy work {t['id']}")
            return 1
        print(path.read_text(encoding="utf-8"))
        print(persona.c(f"\n  📄 {path}", "dim"))
        return 0

    if args.cmd == "backlog":
        if args.backlog_cmd == "add":
            t = state.add_task(" ".join(args.title), args.effort)
            state.save()
            print(f"📌 Added #{t['id']}: {t['title']}")
            return 0
        if args.backlog_cmd == "drop":
            t = state.task(args.id)
            if not t:
                print(f"No task #{args.id}.", file=sys.stderr)
                return 1
            state.tasks.remove(t)
            state.save()
            print(f"🗑️  Dropped #{t['id']}: {t['title']}")
            return 0
        if args.backlog_cmd == "bump":
            t = state.task(args.id)
            if not t:
                print(f"No task #{args.id}.", file=sys.stderr)
                return 1
            if t["status"] != "todo":
                print(f"#{t['id']} is {t['status']}, not todo. Only todo tasks can cut the line.", file=sys.stderr)
                return 1
            if state.next_task() is t:
                print(f"☝️  #{t['id']} is already first in line. {team.guy}: \"On it next, promise.\"")
                return 0
            state.bump_task(t)
            state.save()
            print(f"⏫ Bumped #{t['id']} to the top: {t['title']}. {team.guy}: \"Say no more, that's next.\"")
            return 0
        if args.backlog_cmd == "effort":
            t = state.task(args.id)
            if not t:
                print(f"No task #{args.id}.", file=sys.stderr)
                return 1
            if t["status"] != "todo":
                print(f"#{t['id']} is {t['status']}, not todo. Too late to re-estimate, the coffee's been drunk.",
                      file=sys.stderr)
                return 1
            if not 1 <= args.effort <= 5:
                print("Effort goes from 1 (tiny) to 5 (huge). ☕ to ☕☕☕☕☕", file=sys.stderr)
                return 1
            old, old_xp = int(t["effort"]), State.task_xp(t)
            if args.effort == old:
                print(f"🤷 #{t['id']} is already {persona.coffee(old)}. {team.guy}: \"Nailed the estimate the first time.\"")
                return 0
            t["effort"] = args.effort
            state.save()
            arrow = "📈" if args.effort > old else "📉"
            print(f"{arrow} Re-estimated #{t['id']} {t['title']}: {persona.coffee(old)} → {persona.coffee(args.effort)}"
                  f"  (+{old_xp} → +{State.task_xp(t)} XP)")
            if args.effort > 3 and args.effort > old:
                print(persona.c(f"   {team.guy}: \"{persona.effort_quip(args.effort)}\"", "yellow"))
            elif args.effort < old:
                print(persona.c(f"   {team.guy}: \"Smaller than it looked. My favourite kind.\"", "dim"))
            return 0
        if args.backlog_cmd == "rename":
            t = state.task(args.id)
            if not t:
                print(f"No task #{args.id}.", file=sys.stderr)
                return 1
            if t["status"] not in ("todo", "blocked"):
                print(f"#{t['id']} is {t['status']}, not todo or blocked. The work's already got its name on it.",
                      file=sys.stderr)
                return 1
            new = " ".join(args.title).strip()
            if not new:
                print("A task needs a name. Even \"stuff\" is a name.", file=sys.stderr)
                return 1
            old = t["title"]
            if new == old:
                print(f"🤷 #{t['id']} is already called that. {team.guy}: \"Good name. Keeping it.\"")
                return 0
            state.rename_task(t, new)
            state.save()
            print(f"✏️  Renamed #{t['id']}: {old} → {new}. {team.guy}: \"Ah, so THAT's what we meant.\"")
            return 0
        if args.backlog_cmd == "note":
            t = state.task(args.id)
            if not t:
                print(f"No task #{args.id}.", file=sys.stderr)
                return 1
            if t["status"] != "todo":
                hint = {"blocked": f' Try: teamguy unblock {t["id"]} "..."',
                        "review": f' Try: teamguy reject {t["id"]} "..."'}.get(t["status"], "")
                print(f"#{t['id']} is {t['status']}, not todo. Notes go on work that hasn't started yet.{hint}",
                      file=sys.stderr)
                return 1
            note = " ".join(args.note).strip()
            if not note:
                print("An empty note? Bold. Say something useful, even \"good luck\".", file=sys.stderr)
                return 1
            state.note_task(t, note)
            state.save()
            n = len(t["notes"])
            print(f"📎 Pinned a note to #{t['id']} {t['title']} ({n} note{'s' if n != 1 else ''}). "
                  f"{team.guy}: \"Got it, reading that before I start.\"")
            return 0
        icons = {"todo": "⬜", "doing": "🔄", "blocked": "🧱", "review": "👀", "done": "✅"}
        if args.backlog_cmd == "find":
            query = " ".join(args.words).strip()
            hits = state.find_tasks(query.split())
            if not hits:
                print(f"🔍 Nothing matches \"{query}\". {team.guy}: \"Either it never happened, or I'm very good at forgetting.\"")
                return 0
            print(persona.c(f"🔍 {len(hits)} task{'s' if len(hits) != 1 else ''} matching \"{query}\"", "bold"))
            for t in hits:
                print(f"  {icons.get(t['status'], '?')} #{t['id']:<3} {t['title']}  " + persona.c(t["status"], "dim"))
                if t.get("summary"):
                    summary = " ".join(str(t["summary"]).split())
                    print(persona.c(f"        {summary[:100] + '…' if len(summary) > 100 else summary}", "dim"))
            return 0
        if args.stats:
            order = ["todo", "doing", "blocked", "review", "done"]
            counts = {k: 0 for k in order}
            for t in state.tasks:
                counts[t["status"]] = counts.get(t["status"], 0) + 1
            print(persona.c(f"📊 {team.guy}'s backlog by the numbers", "bold"))
            for k in order + sorted(set(counts) - set(order)):
                print(f"  {icons.get(k, '?')} {k:<8} {counts[k]}")
            print(f"  🧮 total    {len(state.tasks)}")
            coffees = sum(int(t.get("effort") or 0) for t in state.tasks if t["status"] == "todo")
            print(f"  ☕ {coffees} coffee{'s' if coffees != 1 else ''} left in todo. "
                  f"{team.guy}: \"{persona.caffeine_quip(coffees)}\"")
            return 0
        shown = state.tasks if args.all else state.open_tasks()
        print(persona.c(f"{team.guy}'s backlog", "bold"))
        for t in shown:
            nag = persona.review_nag(State.review_age(t))
            n_notes = len(t.get("notes") or []) if t["status"] == "todo" else 0
            clip = f"📎{n_notes}  " if n_notes else ""
            print(f"  {icons.get(t['status'], '?')} #{t['id']:<3} {t['title']}  {persona.coffee(t['effort'])}  {clip}"
                  + persona.c(f"from {t['source']}", "dim")
                  + (persona.c(f"  {nag}", "yellow") if nag else ""))
        if not shown:
            print("  Empty! Add one: teamguy backlog add \"...\"")
        return 0

    # work
    if args.next:
        if state.level.number < AUTOPICK_LEVEL:
            print(f"🔒 Picking their own work unlocks at L{AUTOPICK_LEVEL}. For now, hand {team.guy} a task id or text.")
            return 1
        task = state.next_task()
        if not task:
            print("Backlog is empty. 🏖️")
            return 0
    elif len(args.task) == 1 and args.task[0].isdigit():
        task = state.task(int(args.task[0]))
        if not task:
            print(f"No task #{args.task[0]}.", file=sys.stderr)
            return 1
    elif args.task:
        task = state.add_task(" ".join(args.task), args.effort)
    else:
        print('Give me something to do: teamguy work "..." (or a backlog #id)', file=sys.stderr)
        return 1
    report = work_on(team, state, make_brain(team, args.brain), task)
    verdict = "👀 Ready for review" if report.status == "done" else "🧱 Blocked"
    print(f"\n{verdict}: {report.summary}")
    if report.result and report.result.text and report.result.text != report.summary:
        print(persona.c("\n" + report.result.text, "dim"))
    print(persona.c(f"\n   🪙 Tokens: in {report.tokens.get('input', 0):,} · out {report.tokens.get('output', 0):,}"
                    f" · budget {budget_line(report)}", "dim"))
    if report.work_file:
        print(persona.c(f"\n   📄 Work saved to {report.work_file}  (teamguy show {task['id']})", "dim"))
    if report.status == "done":
        xp = State.task_xp(task)
        print(persona.c(f"\n   Worth +{xp} XP once you sign off: teamguy accept {task['id']}"
                        f'  (or: teamguy reject {task["id"]} "what to fix")', "dim"))
    elif task["status"] == "blocked":
        print(persona.c(f'\n   Know the way past it? teamguy unblock {task["id"]} "what changed"', "dim"))
    _announce(team, report.awards)
    return 0


def _init(args: argparse.Namespace) -> int:
    path: Path = args.file
    if path.exists() and not args.force:
        print(f"❌ {path} already exists. Use --force to replace your guy (cold).", file=sys.stderr)
        return 1
    content = render_template(args.team)
    path.write_text(content, encoding="utf-8")
    guy = guy_name(args.team)
    print(f"✨ A wild {guy} appeared! ({guy_slug(args.team)})")
    print(f"   Wrote {path}. Edit it to teach {guy} everything they do,")
    print("   then try: teamguy whoami · teamguy today · teamguy card")
    return 0


if __name__ == "__main__":
    sys.exit(main())
