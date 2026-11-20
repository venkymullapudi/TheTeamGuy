"""The guy as a teammate: brains, crew, work, standups, onboarding, levels."""

import datetime as dt
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from teamguy.brain import ClaudeBrain, OfflineBrain, Tool, call_tool
from teamguy.cli import main
from teamguy.config import CrewMember, TeamConfigError, load_team, parse_team, render_template
from teamguy.crew import load_skills, run_member
from teamguy.levels import LADDER, level_for, max_steps
from teamguy.meeting import join_standup, parse_updates, render_update
from teamguy.onboarding import run_onboarding
from teamguy.state import ONBOARDING_QUESTS, State
from teamguy.work import offline_plan, work_on

REPO = Path(__file__).parent.parent
FRI = dt.date(2026, 11, 20)


@pytest.fixture
def team(tmp_path):
    shutil.copy(REPO / "team.yaml", tmp_path / "team.yaml")
    shutil.copytree(REPO / "skills", tmp_path / "skills")
    (tmp_path / "README.md").write_text("# SIM team\n## Deploys\nUse the button.\n")
    return load_team(tmp_path / "team.yaml")


@pytest.fixture
def state(team):
    return State.load(team)


def graduate(state, xp=0):
    for q in ONBOARDING_QUESTS:
        state.data["onboarding"][q] = "2026-01-01T00:00:00"
    state.data["xp"] = xp


quiet = lambda *_: None  # noqa: E731


# ─── levels ──────────────────────────────────────────────────────────────────


def test_level_requires_onboarding():
    assert level_for(99999, onboarded=False).number == 0
    assert level_for(100, onboarded=True).title == "Intern"
    assert level_for(10000, onboarded=True).number == 7
    assert max_steps(LADDER[4]) > max_steps(LADDER[0])


def test_award_reports_level_up(state):
    graduate(state, 95)
    award = state.award("kudos", 15, "nice")
    assert award.leveled_up and award.after.number == 1


# ─── config ──────────────────────────────────────────────────────────────────


def test_crew_parsed(team):
    assert {m.name for m in team.crew} >= {"reviewer", "scribe", "test-runner", "claude-code"}
    assert team.member("claude-code").min_level == 4


@pytest.mark.parametrize("bad, msg", [
    ({"name": "Bad Name", "description": "x"}, "lowercase"),
    ({"name": "x", "description": "x", "kind": "robot"}, "kind"),
    ({"name": "x", "description": "x", "kind": "command"}, "command list"),
    ({"name": "x", "description": "x", "kind": "command", "command": "rm -rf /"}, "not a shell string"),
])
def test_crew_validation(bad, msg):
    import yaml

    raw = yaml.safe_load(render_template("SIM"))
    raw["crew"] = [bad]
    with pytest.raises(TeamConfigError, match=msg):
        parse_team(raw)


def test_skills_load(team):
    names = {s.name for s in load_skills(team)}
    assert {"release-notes", "postmortem", "flaky-test-hunt", "ticket-triage"} <= names


# ─── brain plumbing ──────────────────────────────────────────────────────────


def _tool(handler=lambda i: "ok"):
    return Tool("ping", "", {"type": "object", "properties": {"n": {"type": "integer"}, "c": {"type": "string", "enum": ["a"]}},
                             "required": ["n"], "additionalProperties": False}, handler)


def test_call_tool_validates_and_catches():
    assert call_tool(_tool(), {"n": 1}).output == "ok"
    assert call_tool(_tool(), {}).is_error
    assert call_tool(_tool(), {"n": 1, "c": "z"}).is_error
    assert call_tool(_tool(), {"n": 1, "zzz": 1}).is_error
    assert call_tool(_tool(lambda i: 1 / 0), {"n": 1}).is_error
    assert call_tool(None, {}).is_error


class FakeClient:
    """Plays back scripted Claude responses and records requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def tool_use(id_, name, inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def text(t):
    return NS(type="text", text=t)


def test_claude_brain_tool_loop(team, state):
    graduate(state, 100)  # Intern: LLM crew unlocked
    task = state.add_task("review the auth PR", 2)
    client = FakeClient([
        NS(stop_reason="tool_use", content=[tool_use("t1", "delegate", {"member": "reviewer", "instructions": "Review PR 42"})]),
        # the reviewer crew member (an llm) answers through the same client
        NS(stop_reason="end_turn", content=[text("Looks good, one missing test.")]),
        NS(stop_reason="tool_use", content=[tool_use("t2", "complete_task", {"outcome": "done", "summary": "Reviewed; asked for a test.", "effort": 3})]),
        NS(stop_reason="end_turn", content=[text("Reviewed PR 42. Asked for one more test.")]),
    ])
    report = work_on(team, state, ClaudeBrain(client=client), task, out=quiet)

    assert report.status == "done" and report.crew_used == ["reviewer"]
    assert task["status"] == "done" and task["effort"] == 3
    first = client.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert {t["name"] for t in first["tools"]} >= {"delegate", "complete_task"}
    assert all(t["strict"] for t in first["tools"])
    # tool results are sent back with matching ids
    tool_results = client.requests[2]["messages"][-1]["content"]
    assert tool_results[0]["tool_use_id"] == "t1" and "missing test" in tool_results[0]["content"]
    assert state.xp == 100 + 20 * 3 + 5


def test_claude_brain_refusal_and_step_cap(team, state):
    task = state.add_task("something", 1)
    client = FakeClient([NS(stop_reason="refusal", content=[])])
    report = work_on(team, state, ClaudeBrain(client=client), task, out=quiet)
    assert report.status == "blocked" and report.result.stopped == "refusal"

    looping = FakeClient([NS(stop_reason="tool_use", content=[tool_use(f"t{i}", "use_skill", {"name": "ticket-triage"})])
                          for i in range(20)])
    task2 = state.add_task("loop forever", 1)
    report = work_on(team, state, ClaudeBrain(client=looping), task2, out=quiet)
    assert report.result.stopped == "max_steps"
    assert len(looping.requests) == max_steps(state.level)


# ─── crew ────────────────────────────────────────────────────────────────────


def test_command_crew_gets_task_on_stdin_not_argv(team):
    member = CrewMember(
        name="echo", kind="command", description="echo",
        command=[sys.executable, "-c", "import os,sys; print('stdin=' + sys.stdin.read() + ' env=' + os.environ['TEAMGUY_TASK'])"],
    )
    out = run_member(member, "hello; rm -rf /", OfflineBrain(), team)
    assert "ok" in out and "stdin=hello; rm -rf / env=hello; rm -rf /" in out


def test_unavailable_crew_raises(team):
    member = CrewMember(name="ghost", kind="command", description="x", command=["definitely-not-a-real-binary-xyz"])
    with pytest.raises(RuntimeError, match="unavailable"):
        run_member(member, "hi", OfflineBrain(), team)


def test_locked_crew_not_offered(team, state):
    task = state.add_task("run the tests", 2)
    assert all(c["tool"] != "delegate" for c in offline_plan(team, state, task))  # New Hire: no crew
    graduate(state, 300)  # Junior: test-runner unlocked
    members = [c["input"]["member"] for c in offline_plan(team, state, task) if c["tool"] == "delegate"]
    assert "test-runner" in members


# ─── work (offline) ──────────────────────────────────────────────────────────


def test_offline_work_and_first_task_quest(team, state):
    task = state.add_task("write release notes for v2", 2)
    report = work_on(team, state, OfflineBrain(), task, out=quiet)
    assert report.status == "done" and report.skills_used == ["release-notes"]
    assert "first-task" in state.data["onboarding"]
    assert State.load(team).xp == state.xp  # persisted


def test_followups_unlock_at_teammate(team, state):
    from teamguy.work import WorkReport, build_tools

    names = lambda: {t.name for t in build_tools(team, state, OfflineBrain(), WorkReport(task={"id": 1}), quiet)}  # noqa: E731
    assert "add_followup" not in names()
    graduate(state, 700)
    assert "add_followup" in names()


# ─── onboarding ──────────────────────────────────────────────────────────────


def test_onboarding_graduates_to_intern(team, state):
    awards = run_onboarding(team, state, OfflineBrain(), out=quiet)
    assert len(awards) == 4 and not state.onboarded
    assert "Deploys" in state.data["knowledge"]["docs"]
    task = state.add_task("triage tickets", 1)
    work_on(team, state, OfflineBrain(), task, out=quiet)
    assert state.onboarded and state.level.title == "Intern"


def test_onboarding_without_docs_files_a_task(team, state):
    (team.base_dir / "README.md").unlink()
    team.onboarding_docs = ["README.md"]
    run_onboarding(team, state, OfflineBrain(), out=quiet)
    assert any("onboarding docs" in t["title"] for t in state.tasks)


# ─── standup ─────────────────────────────────────────────────────────────────


def test_parse_updates():
    assert parse_updates("Alex: on it\n- Sam: blocked\nnoise") == [("Alex", "on it"), ("Sam", "blocked")]


def test_join_standup_volunteers_and_awards_once(team, state):
    updates = [("Alex", "blocked on review"), ("Sam", "all good"), ("Priya", "CI is flaky")]
    report = join_standup(team, state, OfflineBrain(), updates, FRI, out=quiet)
    assert [t["source"] for t in report.action_items] == ["standup:Alex", "standup:Priya"]
    assert state.xp == 10 + 2 * 5
    assert report.notes_path.exists()
    join_standup(team, state, OfflineBrain(), [], FRI, out=quiet)
    assert state.xp == 20  # attendance counts once per day


def test_standup_update_uses_real_work(team, state):
    task = state.add_task("fix the build", 1)
    work_on(team, state, OfflineBrain(), task, out=quiet)
    tomorrow = dt.date.today() + dt.timedelta(days=1)  # today always falls in tomorrow's "yesterday" window
    assert "fix the build" in render_update(team, state, tomorrow)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def test_cli_teammate_flow(team, capsys, monkeypatch):
    f = str(team.base_dir / "team.yaml")
    monkeypatch.setenv("TEAMGUY_BRAIN", "offline")
    run = lambda *a: main(["-f", f, *a])  # noqa: E731
    assert run("onboard") == 0
    assert run("work", "triage", "the", "tickets") == 0
    assert "LEVEL UP" in capsys.readouterr().out
    assert run("backlog", "add", "update", "the", "runbook") == 0
    assert run("work", "2") == 0
    assert run("work", "--next") == 1  # locked until Staff
    for cmd in (["level"], ["crew"], ["skills"], ["journal"], ["backlog", "--all"], ["kudos", "nice"], ["standup"],
                ["onboard", "--status"], ["whoami"]):
        assert run(*cmd) == 0, cmd
    updates = team.base_dir / "updates.txt"
    updates.write_text("Alex: need a review\n")
    assert run("standup", "--join", "--updates", str(updates)) == 0
    assert "Help Alex" in capsys.readouterr().out
