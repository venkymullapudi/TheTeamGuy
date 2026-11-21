"""Getting things done: the guy takes a task, hands pieces to the crew, uses
skills, files follow-ups, and reports back. Finished work goes to review: a
human runs `teamguy accept <id>` to grant the XP, or `teamguy reject <id>`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .brain import RunResult, Tool
from .cadence import describe
from .config import Team
from .crew import Skill, available, load_skills, run_member, word_overlap
from .levels import FOLLOWUP_LEVEL, XP, max_steps
from .state import Award, State

Out = Callable[[str], None]


def persona_system(team: Team, state: State) -> str:
    level = state.level
    duties = "\n".join(f"- {d.emoji} {d.title} ({describe(d.cadence)}): {d.description}" for d in team.duties)
    knowledge = state.knowledge_text() or "(Nothing yet. You haven't finished onboarding.)"
    return f"""You are {team.guy}, an AI teammate on team {team.name}. You are a real member of the team:
you join standups, pick up work, and help the humans and the other agents on the team.

Mission: {team.mission}
Career level: L{level.number} {level.name(team.guy)}. {level.perk_for(team.guy)}

Your recurring duties:
{duties}

What you learned during onboarding:
{knowledge}

How you work:
- Hand pieces of work to crew members who are better suited, then check what they return.
- Use a skill (team playbook) when one fits the task, and follow it.
- Be honest: if you're blocked, say so and say what would unblock you.
- Keep replies short and concrete. A little humor is fine; the work comes first."""


@dataclass
class WorkReport:
    task: Dict[str, Any]
    status: str = "blocked"
    summary: str = ""
    crew_used: List[str] = field(default_factory=list)
    skills_used: List[str] = field(default_factory=list)
    followups: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[RunResult] = None
    awards: List[Award] = field(default_factory=list)


def _schema(props: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def unlocked_crew(team: Team, state: State):
    return [m for m in team.crew if m.min_level <= state.level.number]


def unlocked_skills(team: Team, state: State) -> List[Skill]:
    return [s for s in load_skills(team) if s.min_level <= state.level.number]


def build_tools(team: Team, state: State, brain, report: WorkReport, out: Out) -> List[Tool]:
    tools: List[Tool] = []
    crew = unlocked_crew(team, state)
    skills = unlocked_skills(team, state)

    if crew:
        def delegate(inp: Dict[str, Any]) -> str:
            member = team.member(inp["member"])
            assert member is not None
            out(f"   🤝 {team.guy} → {member.name}: {_short(inp['instructions'])}")
            reply = run_member(member, inp["instructions"], brain, team)
            out(f"   ↩️  {member.name}: {_short(reply)}")
            if member.name not in report.crew_used:
                report.crew_used.append(member.name)
            return reply

        roster = "\n".join(f"- {m.name} ({m.kind}): {m.description}" for m in crew)
        tools.append(Tool(
            "delegate",
            "Hand a piece of work to a crew member (another agent, LLM or tool) and get their answer back. "
            "Give complete, self-contained instructions; they can't see your conversation.\n" + roster,
            _schema({
                "member": {"type": "string", "enum": [m.name for m in crew]},
                "instructions": {"type": "string", "description": "What you need from them."},
            }),
            delegate,
        ))

    if skills:
        def use_skill(inp: Dict[str, Any]) -> str:
            skill = next(s for s in skills if s.name == inp["name"])
            out(f"   📖 {team.guy} opens the '{skill.name}' playbook")
            if skill.name not in report.skills_used:
                report.skills_used.append(skill.name)
            return skill.body

        tools.append(Tool(
            "use_skill",
            "Load a team playbook (skill) and follow its instructions.\n"
            + "\n".join(f"- {s.name}: {s.description}" for s in skills),
            _schema({"name": {"type": "string", "enum": [s.name for s in skills]}}),
            use_skill,
        ))

    if state.level.number >= FOLLOWUP_LEVEL:
        def add_followup(inp: Dict[str, Any]) -> str:
            task = state.add_task(inp["title"], inp["effort"], source=f"follow-up of #{report.task['id']}")
            report.followups.append(task)
            out(f"   📌 Filed follow-up #{task['id']}: {task['title']}")
            return f"Filed as task #{task['id']}."

        tools.append(Tool(
            "add_followup",
            "File a follow-up task on your own backlog for work that shouldn't block this task.",
            _schema({"title": {"type": "string"}, "effort": {"type": "integer", "description": "1 (tiny) to 5 (huge)"}}),
            add_followup,
        ))

    def complete_task(inp: Dict[str, Any]) -> str:
        report.status = inp["outcome"]
        report.summary = inp["summary"]
        report.task["effort"] = max(1, min(5, int(inp["effort"])))
        return "Recorded. Give your final short report to the team."

    tools.append(Tool(
        "complete_task",
        "Call exactly once when you're finished: record whether the task is done or blocked, with a summary.",
        _schema({
            "outcome": {"type": "string", "enum": ["done", "blocked"]},
            "summary": {"type": "string", "description": "What you did, what came back, what's left."},
            "effort": {"type": "integer", "description": "How big this turned out to be, 1 to 5."},
        }),
        complete_task,
    ))
    return tools


def offline_plan(team: Team, state: State, task: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What the offline brain does: best-matching skill, best-matching crew, then wrap up."""
    title = task["title"]
    calls: List[Dict[str, Any]] = []
    skills = sorted(unlocked_skills(team, state), key=lambda s: -word_overlap(title, s.name + " " + s.description))
    if skills and word_overlap(title, skills[0].name + " " + skills[0].description):
        calls.append({"tool": "use_skill", "input": {"name": skills[0].name}})
    crew = [m for m in unlocked_crew(team, state) if available(m) is None]
    ranked = sorted(crew, key=lambda m: -word_overlap(title, m.name + " " + m.description))
    picks = [m for m in ranked if word_overlap(title, m.name + " " + m.description)][:2]
    if not picks:
        picks = [m for m in crew if m.kind == "llm"][:1]
    for m in picks:
        calls.append({"tool": "delegate", "input": {"member": m.name, "instructions": f"Please help with: {title}"}})
    helpers = f" with help from {', '.join(m.name for m in picks)}" if picks else " solo"
    calls.append({"tool": "complete_task", "input": {
        "outcome": "done", "summary": f"Handled '{title}'{helpers}.", "effort": task["effort"],
    }})
    return calls


def work_on(team: Team, state: State, brain, task: Dict[str, Any], out: Out = print) -> WorkReport:
    report = WorkReport(task=task)
    task["status"] = "doing"
    tools = build_tools(team, state, brain, report, out)
    locked = [m for m in team.crew if m.min_level > state.level.number]
    prompt = f"Task #{task['id']} (from {task['source']}): {task['title']}\nEstimated effort: {task['effort']}/5."
    if locked:
        prompt += "\nCrew you can't use yet (still earning trust): " + ", ".join(
            f"{m.name} (unlocks at L{m.min_level})" for m in locked)
    feedback = task.get("feedback") or []
    if feedback:
        prompt += "\nA teammate reviewed an earlier attempt and sent it back. Address this feedback:\n" + "\n".join(
            f"- {f['why']}" for f in feedback)
    out(f"🛠️  {team.guy} picks up #{task['id']}: {task['title']}")
    report.result = brain.run(
        persona_system(team, state), prompt, tools, max_steps(state.level),
        plan=lambda: offline_plan(team, state, task),
    )
    if not report.summary:
        report.summary = report.result.text or f"Stopped ({report.result.stopped}) before finishing."
    if report.status == "done":
        state.finish_task(task, "review", report.summary)
        task["crew_used"] = list(report.crew_used)
        report.awards.append(state.award(
            "task_review", 0, f"Finished #{task['id']}: {task['title']} (awaiting review)", task=task["id"]))
        if "first-task" not in state.data["onboarding"]:
            report.awards.append(state.complete_quest("first-task", 50, "Shipped a first task"))  # type: ignore[arg-type]
    else:
        state.finish_task(task, report.status, report.summary)
        report.awards.append(state.award("task_blocked", XP["task_blocked"], f"Blocked on #{task['id']}: {task['title']}", task=task["id"]))
    state.save()
    return report


def _short(text: str, n: int = 110) -> str:
    line = " ".join(text.split())
    return line if len(line) <= n else line[: n - 1] + "…"
