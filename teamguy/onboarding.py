"""Day one. Every new hire gets onboarded, and so does The<Team>Guy.

Quests: meet the team → read the docs → learn the duties → meet the crew →
ship a first task. Finishing them all graduates the guy to L1 Intern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .cadence import describe
from .crew import available
from .config import Team
from .state import Award, State
from .work import Out, persona_system


@dataclass
class Quest:
    id: str
    title: str
    emoji: str
    xp: int
    blurb: str
    run: Optional[Callable[[Team, State, object], str]] = None  # None = completed elsewhere


def _meet_the_team(team: Team, state: State, brain) -> str:
    people = sorted({p for p in team.roster if p != team.guy}) or ["(roster is empty — suspicious)"]
    crew = ", ".join(m.name for m in team.crew) or "nobody yet"
    state.learn("team", f"Teammates: {', '.join(people)}. Crew (agents/tools): {crew}.")
    return brain.complete(
        system=persona_system(team, state),
        prompt=(f"You just joined team {team.name}. Your human teammates: {', '.join(people)}. "
                f"Your crew of agents and tools: {crew}. Write a short, warm, slightly funny hello "
                "(3 sentences max) to post in the team channel."),
        fallback=(f"Hi team {team.name}! 👋 I'm {team.guy}, your newest teammate. "
                  f"Looking forward to working with {', '.join(people)}, and yes, I already know where the coffee is."),
    )


def _read_the_docs(team: Team, state: State, brain) -> str:
    docs = []
    for rel in team.onboarding_docs:
        path = (team.base_dir / rel)
        if path.is_file():
            docs.append((rel, path.read_text(encoding="utf-8", errors="replace")[:30000]))
    if not docs:
        task = state.add_task("Write the onboarding docs nobody wrote", 3, source="onboarding")
        state.learn("docs", "There were no docs. Classic.")
        return f"Found no docs at {', '.join(team.onboarding_docs)}. Filed #{task['id']} to write them. 📝"
    bundle = "\n\n".join(f'<doc path="{p}">\n{t}\n</doc>' for p, t in docs)
    headings = [
        line.lstrip("# ").strip()
        for p, t in docs if p.endswith(".md")
        for line in t.splitlines() if line.startswith("#") and line.lstrip("# ").strip()
    ]
    notes = brain.complete(
        system=persona_system(team, state),
        prompt=("Here are the team's docs. Write notes for future you: what the team does, key commands, "
                "where things live, gotchas. Bullets, under 200 words.\n\n" + bundle),
        fallback="Skimmed: " + "; ".join(headings[:12]) if headings else "Skimmed the docs. Lots of words.",
    )
    state.learn("docs", notes)
    return notes


def _learn_the_duties(team: Team, state: State, brain) -> str:
    listing = "\n".join(f"- {d.title} ({describe(d.cadence)}, effort {d.effort}/5)" for d in team.duties)
    notes = brain.complete(
        system=persona_system(team, state),
        prompt=("These are the duties you own. In under 120 words, say how you'll approach your first two weeks: "
                "what you'll start with, what you'll shadow, and what you'll ask about.\n\n" + listing),
        fallback=("First two weeks: shadow on-call, host standup, sweep PRs daily, and save the "
                  f"{sum(1 for d in team.duties if d.cadence == 'on-demand')} on-demand duties for when I'm summoned."),
    )
    state.learn("duties", notes)
    return notes


def _meet_the_crew(team: Team, state: State, brain) -> str:
    if not team.crew:
        return "No crew configured yet. Add agents and tools under `crew:` in team.yaml."
    lines = []
    for m in team.crew:
        reason = available(m)
        status = "✅ ready" if reason is None else f"⚠️  {reason}"
        lines.append(f"  {m.name:<14} {m.kind:<12} unlocks at L{m.min_level}   {status}")
    state.learn("crew", "\n".join(f"{m.name} ({m.kind}, L{m.min_level}+): {m.description}" for m in team.crew))
    return "Shook hands with the crew:\n" + "\n".join(lines)


QUESTS: List[Quest] = [
    Quest("meet-the-team", "Meet the team", "👋", 25, "Say hi and learn who's who.", _meet_the_team),
    Quest("read-the-docs", "Read the docs", "📚", 50, "Read the onboarding docs and take notes.", _read_the_docs),
    Quest("learn-the-duties", "Learn the duties", "🗂️", 25, "Study every duty in team.yaml.", _learn_the_duties),
    Quest("meet-the-crew", "Meet the crew", "🤖", 25, "Check in with every agent and tool on the team.", _meet_the_crew),
    Quest("first-task", "Ship a first task", "🚢", 50, "Finish a real task: `teamguy work \"...\"`."),
]


def quest_status(state: State) -> List[tuple]:
    return [(q, q.id in state.data["onboarding"]) for q in QUESTS]


def run_onboarding(team: Team, state: State, brain, out: Out = print) -> List[Award]:
    awards: List[Award] = []
    for quest, done in quest_status(state):
        if done or quest.run is None:
            continue
        out(f"\n{quest.emoji}  Quest: {quest.title} (+{quest.xp} XP)")
        result = quest.run(team, state, brain)
        out("\n".join("   " + line for line in result.splitlines()))
        award = state.complete_quest(quest.id, quest.xp, f"Onboarding: {quest.title}")
        if award:
            awards.append(award)
        state.save()
    return awards
