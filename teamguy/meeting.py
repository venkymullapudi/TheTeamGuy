"""Standups. The guy gives a real update from their work log, listens to
teammates, and volunteers for action items."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .brain import Tool
from .config import Team
from .fun import brag_line
from .levels import XP
from .state import Award, State
from .work import Out, persona_system

HELP_WORDS = ("blocked", "stuck", "help", "need", "flaky", "review", "broken", "failing", "docs", "question", "slow")


def previous_workday(day: dt.date) -> dt.date:
    back = {0: 3, 6: 2}.get(day.weekday(), 1)
    return day - dt.timedelta(days=back)


def my_update(team: Team, state: State, day: dt.date) -> Dict[str, List[str]]:
    since = dt.datetime.combine(previous_workday(day), dt.time())
    until = dt.datetime.combine(day, dt.time())
    done = [
        e["summary"] for e in state.log_since(since)
        if e["kind"] in ("task_done", "task_review", "task_blocked", "onboarding", "kudos")
        and dt.datetime.fromisoformat(e["at"]) < until
    ]
    from .persona import due_on  # local import: persona imports nothing from here

    today = [f"#{t['id']} {t['title']}" for t in state.tasks if t["status"] == "todo"][:3]
    today += [f"{d.emoji} {d.title}" for d in due_on(team, day) if d.cadence not in ("always",)][:2]
    blockers = [f"#{t['id']} {t['title']}" for t in state.tasks if t["status"] == "blocked"]
    blockers += [f"#{t['id']} {t['title']} is waiting on your review (`teamguy accept {t['id']}`)"
                 for t in state.in_review()]
    return {"yesterday": done[-4:], "today": today, "blockers": blockers}


def render_update(team: Team, state: State, day: dt.date) -> str:
    u = my_update(team, state, day)
    lvl = state.level
    lines = [f"🎤 {team.guy}'s standup ({lvl.badge} L{lvl.number} {lvl.name(team.guy)}) — {day:%a %b %d}", "", "Yesterday:"]
    lines += [f"  • {x}" for x in u["yesterday"]] or ["  • Read docs, drank coffee, built context. (New here!)"]
    lines.append("Today:")
    lines += [f"  • {x}" for x in u["today"]] or ["  • Looking for something useful to pick up. Throw me a task!"]
    lines.append("Blockers:")
    lines += [f"  • {x}" for x in u["blockers"]] or ["  • None 🎉"]
    brag = brag_line(state, day)
    if brag:
        lines.append(brag)
    return "\n".join(lines)


def inbox_path(team: Team) -> Path:
    """Where teammates drop async 'Name: update' lines before standup."""
    return team.state_dir / "standups" / "inbox.md"


def parse_updates(text: str) -> List[Tuple[str, str]]:
    """'Alex: fixing the login bug, blocked on review' -> [('Alex', '...')]"""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]?\s*([^:]{1,40}):\s*(.+)$", line)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


@dataclass
class StandupReport:
    my_update: str
    reply: str
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    awards: List[Award] = field(default_factory=list)
    notes_path: Any = None


def join_standup(team: Team, state: State, brain, updates: List[Tuple[str, str]], day: dt.date, out: Out = print) -> StandupReport:
    mine = render_update(team, state, day)
    report = StandupReport(my_update=mine, reply="")

    def take_action_item(inp: Dict[str, Any]) -> str:
        task = state.add_task(inp["title"], inp["effort"], source=f"standup:{inp['teammate']}")
        report.action_items.append(task)
        out(f"   🙋 {team.guy} takes #{task['id']}: {task['title']} (for {inp['teammate']})")
        return f"Added to your backlog as #{task['id']}."

    tool = Tool(
        "take_action_item",
        "Volunteer for something a teammate mentioned. It goes on your backlog.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "teammate": {"type": "string"},
                "effort": {"type": "integer", "description": "1 (tiny) to 5 (huge)"},
            },
            "required": ["title", "teammate", "effort"],
            "additionalProperties": False,
        },
        take_action_item,
    )

    def plan():
        calls = []
        for name, text in updates:
            if any(w in text.lower() for w in HELP_WORDS):
                calls.append({"tool": "take_action_item", "input": {
                    "title": f"Help {name}: {text[:70]}", "teammate": name, "effort": 2}})
        return calls

    said = "\n".join(f"- {n}: {t}" for n, t in updates) or "(Nobody else showed up. Classic Friday.)"
    prompt = (
        f"It's standup on {day:%A}. Here's your own update, built from your work log:\n\n{mine}\n\n"
        f"Your teammates said:\n{said}\n\n"
        "Listen like a good teammate. Where you can genuinely help (blocked work, reviews, flaky tests, docs, "
        "questions), call take_action_item. Don't volunteer for everything. Then write what you'd say out loud: "
        "your update in two or three lines plus the help you're offering. Keep it short."
    )
    result = brain.run(persona_system(team, state), prompt, [tool], max_steps=4, plan=plan)
    offers = ", ".join(f"#{t['id']} for {t['source'].split(':', 1)[1]}" for t in report.action_items)
    report.reply = (
        result.text if brain.name != "offline"
        else mine + ("\n\nI can help: " + offers if offers else "\n\nNothing I can grab today, but ping me!")
    )

    if not state.did_today("standup", day):
        report.awards.append(state.award("standup", XP["standup"], f"Joined standup on {day:%b %d}",
                                         day=day.isoformat()))
    if report.action_items:
        report.awards.append(state.award(
            "standup_items", XP["standup_action_item"] * len(report.action_items),
            f"Volunteered for {len(report.action_items)} action item(s) at standup"))

    notes_dir = team.state_dir / "standups"
    notes_dir.mkdir(parents=True, exist_ok=True)
    report.notes_path = notes_dir / f"{day.isoformat()}.md"
    report.notes_path.write_text(
        f"# Standup {day.isoformat()}\n\n## Team\n{said}\n\n## {team.guy}\n{report.reply}\n", encoding="utf-8")
    state.save()
    return report
