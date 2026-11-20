"""`teamguy` — summon The<Team>Guy from the command line."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, persona
from .config import TeamConfigError, guy_name, guy_slug, load_team, render_template


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
    sub = p.add_subparsers(dest="cmd", metavar="<command>")

    s = sub.add_parser("init", help="create team.yaml and birth The<TEAM>Guy")
    s.add_argument("team", help="your team's name, e.g. SIM")
    s.add_argument("--force", action="store_true", help="overwrite an existing team.yaml")

    sub.add_parser("whoami", help="meet your guy")

    s = sub.add_parser("duties", help="list everything the guy does")
    s.add_argument("-v", "--verbose", action="store_true", help="include checklists")

    s = sub.add_parser("duty", help="details for a single duty")
    s.add_argument("id")

    for name, help_ in (("today", "what's on the guy's plate today"), ("standup", "auto-generated standup update")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--date", type=_date, default=dt.date.today())

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
            print(persona.standup(team, args.date))
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
