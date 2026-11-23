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
    ({"name": "x", "description": "x", "kind": "claude-code", "args": "--permission-mode acceptEdits"}, "not a shell string"),
    ({"name": "x", "description": "x", "kind": "claude-code", "args": ["-p"]}, "always runs headless"),
    ({"name": "x", "description": "x", "kind": "llm", "args": ["--verbose"]}, "is for kind 'claude-code'"),
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
    assert task["status"] == "review" and task["effort"] == 3
    first = client.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert {t["name"] for t in first["tools"]} >= {"delegate", "complete_task"}
    assert all(t["strict"] for t in first["tools"])
    # tool results are sent back with matching ids
    tool_results = client.requests[2]["messages"][-1]["content"]
    assert tool_results[0]["tool_use_id"] == "t1" and "missing test" in tool_results[0]["content"]
    assert state.xp == 100  # nothing until a human signs off
    state.accept_task(task)
    assert task["status"] == "done" and state.xp == 100 + 20 * 3 + 5


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


def test_claude_code_crew_gets_args_and_task_on_stdin(team, tmp_path):
    # A stand-in `claude` that reports the argv and stdin it was given.
    fake = tmp_path / "fake_claude.py"
    fake.write_text("import json, os, sys\nprint(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read(), 'env': os.environ['TEAMGUY_TASK']}))\n")
    member = CrewMember(
        name="cc", kind="claude-code", description="x",
        command=[sys.executable, str(fake)], args=["--permission-mode", "acceptEdits"],
    )
    out = run_member(member, "--dangerously-sneaky; rm -rf /", OfflineBrain(), team)
    import json

    got = json.loads(out.split("\n", 1)[1])
    assert got["argv"] == ["-p", "--permission-mode", "acceptEdits"]
    assert got["stdin"] == got["env"] == "--dangerously-sneaky; rm -rf /"


def test_template_claude_code_has_args(team):
    assert team.member("claude-code").args == ["--permission-mode", "acceptEdits"]


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


def test_work_file_saves_deliverable_transcript_and_tokens(team, state):
    graduate(state, 100)  # Intern: LLM crew unlocked
    task = state.add_task("review the auth PR!", 2)
    client = FakeClient([
        NS(stop_reason="tool_use", usage=NS(input_tokens=100, output_tokens=10),
           content=[tool_use("t1", "delegate", {"member": "reviewer", "instructions": "Review PR 42"})]),
        NS(stop_reason="end_turn", usage=NS(input_tokens=50, output_tokens=20), content=[text("One missing test.")]),
        NS(stop_reason="tool_use", usage=NS(input_tokens=200, output_tokens=5),
           content=[tool_use("t2", "complete_task", {"outcome": "done", "summary": "Reviewed.", "effort": 2})]),
        NS(stop_reason="end_turn", content=[text("Here are the review notes.")]),  # no usage: still fine
    ])
    report = work_on(team, state, ClaudeBrain(client=client), task, out=quiet)

    path = team.state_dir / "work" / "1-review-the-auth-pr.md"
    assert report.work_file == path and task["work_file"] == "work/1-review-the-auth-pr.md"
    assert report.tokens == task["tokens"] == {"input": 350, "output": 35}
    md = path.read_text()
    assert "## Deliverable\n\nHere are the review notes." in md
    assert "→ reviewer" in md and "> Review PR 42" in md and "> One missing test." in md
    assert "total: 385" in md


def test_offline_work_file_and_show(team, capsys, monkeypatch):
    f = str(team.base_dir / "team.yaml")
    monkeypatch.setenv("TEAMGUY_BRAIN", "offline")
    assert main(["-f", f, "work", "write", "release", "notes", "for", "v2"]) == 0
    assert "teamguy show 1" in capsys.readouterr().out
    assert main(["-f", f, "show", "1"]) == 0
    out = capsys.readouterr().out
    assert "# #1: write release notes for v2" in out and "release-notes" in out
    assert "free as in coffee" in out
    assert main(["-f", f, "backlog", "add", "untouched"]) == 0
    assert main(["-f", f, "show", "2"]) == 1
    assert main(["-f", f, "show", "99"]) == 1


def test_slugify():
    from teamguy.work import slugify
    assert slugify("Fix: the *build*  (again)") == "fix-the-build-again"
    assert slugify("!!!") == "task"
    assert len(slugify("word " * 30)) <= 40


def test_xp_is_earned_on_accept_not_self_reported(team, state):
    graduate(state, 100)
    task = state.add_task("write release notes for v2", 2)
    work_on(team, state, OfflineBrain(), task, out=quiet)
    assert task["status"] == "review" and state.xp == 100
    assert task in state.open_tasks() and "accept 1" in " ".join(render_update(team, state, FRI).split())
    award = state.accept_task(task)
    assert award.xp == State.task_xp(task) == 20 * 2 + 5 * len(task["crew_used"])
    assert task["status"] == "done" and state.xp == 100 + award.xp
    with pytest.raises(ValueError):
        state.accept_task(task)  # no double-dipping


def test_rejected_work_goes_back_with_feedback(team, state):
    task = state.add_task("fix the build", 1)
    work_on(team, state, OfflineBrain(), task, out=quiet)
    xp = state.xp
    state.reject_task(task, "the build is still red")
    assert task["status"] == "todo" and state.xp == xp
    assert task["feedback"][0]["why"] == "the build is still red"

    client = FakeClient([NS(stop_reason="refusal", content=[])])
    work_on(team, state, ClaudeBrain(client=client), task, out=quiet)
    assert "the build is still red" in client.requests[0]["messages"][0]["content"]


def test_blocked_work_unblocks_with_a_note(team, state):
    task = state.add_task("deploy to staging", 1)
    with pytest.raises(ValueError):
        state.unblock_task(task, "nope")  # todo isn't blocked
    state.finish_task(task, "blocked", "staging is down")
    xp = state.xp
    award = state.unblock_task(task, "staging is back up")
    assert task["status"] == "todo" and state.xp == xp and award.xp == 0
    assert task["unblocks"][0]["note"] == "staging is back up"
    assert not task.get("feedback")  # not a reject: no Comeback Kid freebie

    client = FakeClient([NS(stop_reason="refusal", content=[])])
    work_on(team, state, ClaudeBrain(client=client), task, out=quiet)
    assert "staging is back up" in client.requests[0]["messages"][0]["content"]
    assert "Unblock notes" in (team.state_dir / task["work_file"]).read_text()


def test_cli_unblock(team, capsys, monkeypatch):
    f = str(team.base_dir / "team.yaml")
    monkeypatch.setenv("TEAMGUY_BRAIN", "offline")
    run = lambda *a: main(["-f", f, *a])  # noqa: E731
    state = State.load(team)
    task = state.add_task("rotate the certs", 1)
    state.finish_task(task, "blocked", "need vault access")
    state.save()
    assert run("unblock", "1", "vault", "access", "granted") == 0
    assert "unblocked" in capsys.readouterr().out
    assert State.load(team).task(1)["status"] == "todo"
    assert run("unblock", "1", "again") == 1  # already todo
    assert run("unblock", "99", "x") == 1


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


def test_standup_attendance_is_per_meeting_day_not_wall_clock(team, state):
    # Standups for other days (past or future) each count once, whatever today is.
    mon, tue = dt.date(2020, 3, 2), dt.date(2031, 6, 3)
    join_standup(team, state, OfflineBrain(), [], mon, out=quiet)
    join_standup(team, state, OfflineBrain(), [], mon, out=quiet)
    assert state.xp == 10
    assert state.did_today("standup", mon)
    assert not state.did_today("standup", dt.date.today())
    join_standup(team, state, OfflineBrain(), [], tue, out=quiet)
    assert state.xp == 20


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
    capsys.readouterr()
    assert run("accept", "1") == 0
    assert "accepted" in capsys.readouterr().out
    assert run("accept", "1") == 1  # already done
    assert run("reject", "2", "add", "the", "on-call", "section") == 0
    assert State.load(team).task(2)["status"] == "todo"
    assert run("accept", "99") == 1
    for cmd in (["level"], ["crew"], ["skills"], ["journal"], ["backlog", "--all"], ["kudos", "nice"], ["standup"],
                ["onboard", "--status"], ["whoami"]):
        assert run(*cmd) == 0, cmd
    updates = team.base_dir / "updates.txt"
    updates.write_text("Alex: need a review\n")
    assert run("standup", "--join", "--updates", str(updates)) == 0
    assert "Help Alex" in capsys.readouterr().out


def test_standup_reads_and_clears_the_inbox(team, capsys, monkeypatch):
    f = str(team.base_dir / "team.yaml")
    monkeypatch.setenv("TEAMGUY_BRAIN", "offline")
    run = lambda *a: main(["-f", f, *a])  # noqa: E731
    inbox = team.state_dir / "standups" / "inbox.md"
    inbox.parent.mkdir(parents=True)
    inbox.write_text("Sam: stuck on a flaky test\nPriya: shipped the dashboard\n")
    assert run("standup") == 0
    assert "2 update(s) waiting" in capsys.readouterr().out
    assert inbox.read_text() != ""  # a preview never eats the inbox
    assert run("standup", "--join") == 0
    out = capsys.readouterr().out
    assert "Help Sam" in out and "Inbox cleared" in out
    assert inbox.read_text() == ""
    assert "Priya: shipped" in (team.state_dir / "standups" / f"{dt.date.today().isoformat()}.md").read_text()


def test_standup_updates_flag_beats_inbox_and_keep_inbox(team, capsys, monkeypatch):
    f = str(team.base_dir / "team.yaml")
    monkeypatch.setenv("TEAMGUY_BRAIN", "offline")
    run = lambda *a: main(["-f", f, *a])  # noqa: E731
    inbox = team.state_dir / "standups" / "inbox.md"
    inbox.parent.mkdir(parents=True)
    inbox.write_text("Sam: need a review\n")
    updates = team.base_dir / "updates.txt"
    updates.write_text("Alex: blocked on docs\n")
    assert run("standup", "--join", "--updates", str(updates)) == 0
    out = capsys.readouterr().out
    assert "Help Alex" in out and "Help Sam" not in out
    assert inbox.read_text() == "Sam: need a review\n"  # untouched
    assert run("standup", "--join", "--keep-inbox") == 0
    assert "Help Sam" in capsys.readouterr().out
    assert inbox.read_text() == "Sam: need a review\n"


def test_oauth_token_in_api_key_gets_a_clear_error(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    import httpx2

    from teamguy.brain import BrainError

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat01-not-a-real-token")
    resp = httpx2.Response(429, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))

    def boom(**_):
        raise anthropic.RateLimitError("Error", response=resp, body=None)

    brain = ClaudeBrain(client=NS(beta=NS(messages=NS(create=boom))))
    with pytest.raises(BrainError, match="OAuth token"):
        brain.complete("sys", "hi")


# ─── token budget ────────────────────────────────────────────────────────────

def test_token_budget_grows_with_level_and_parses(team):
    from teamguy.levels import token_budget
    assert team.task_token_budget == 200_000
    assert [token_budget(1000, LADDER[n]) for n in (0, 2, 7)] == [1000, 2000, 4500]
    assert token_budget(0, LADDER[7]) == 0
    raw = {"team": "SIM", "duties": [{"id": "x", "title": "X", "cadence": "daily", "description": "x"}]}
    assert parse_team({**raw, "brain": {"task_token_budget": 5}}).task_token_budget == 5
    for bad in ("lots", -1):
        with pytest.raises(TeamConfigError, match="task_token_budget"):
            parse_team({**raw, "brain": {"task_token_budget": bad}})


def test_task_stops_gracefully_past_token_budget(team, state):
    graduate(state, 100)  # Intern: budget 200k * 1.5 = 300k, LLM crew unlocked
    team.task_token_budget = 100  # L1 → 150
    task = state.add_task("review the auth PR!", 2)
    client = FakeClient([
        NS(stop_reason="tool_use", usage=NS(input_tokens=100, output_tokens=10),
           content=[tool_use("t1", "delegate", {"member": "reviewer", "instructions": "Review PR 42"})]),
        NS(stop_reason="end_turn", usage=NS(input_tokens=50, output_tokens=20), content=[text("Looks fine.")]),
        NS(stop_reason="tool_use", usage=NS(input_tokens=999, output_tokens=1),
           content=[tool_use("t2", "use_skill", {"name": "ticket-triage"})]),
    ])
    report = work_on(team, state, ClaudeBrain(client=client), task, out=quiet)
    assert report.budget == 150
    assert report.result.stopped == "budget" and len(client.requests) == 2  # never sent turn 3
    assert report.status == task["status"] == "blocked"
    assert "Out of token budget (180 of 150)" in report.summary
    assert "Token budget for this task: 150" in client.requests[0]["messages"][0]["content"]
    md = report.work_file.read_text()
    assert "- budget: 180 of 150 (120%)  🪙 ran out, task parked" in md


def test_llm_crew_is_skipped_once_budget_is_spent(team, state):
    graduate(state, 100)
    team.task_token_budget = 10  # L1 → 15
    task = state.add_task("review the auth PR!", 2)
    client = FakeClient([
        NS(stop_reason="tool_use", usage=NS(input_tokens=20, output_tokens=0),
           content=[tool_use("t1", "delegate", {"member": "reviewer", "instructions": "Review PR 42"})]),
    ])
    report = work_on(team, state, ClaudeBrain(client=client), task, out=quiet)
    assert len(client.requests) == 1  # reviewer never called, next turn refused
    assert report.transcript[0]["reply"] == "(skipped: token budget spent)"
    assert report.result.stopped == "budget"


def test_zero_budget_means_no_limit_and_offline_reports_it(team, state):
    team.task_token_budget = 0
    report = work_on(team, state, OfflineBrain(), state.add_task("write release notes", 1), out=quiet)
    assert report.budget == 0 and report.status == "done"
    assert "no limit (living dangerously)" in report.work_file.read_text()


# ─── streaks & achievements ──────────────────────────────────────────────────


def _standup_on(state, day):
    state.award("standup", 10, f"Joined standup on {day}", day=day.isoformat())


def test_standup_streak_skips_weekends_and_breaks_on_a_gap(state):
    from teamguy import fun

    mon = dt.date(2026, 11, 16)
    for d in range(5):  # Mon..Fri
        _standup_on(state, mon + dt.timedelta(days=d))
    next_mon = mon + dt.timedelta(days=7)
    _standup_on(state, next_mon)
    assert fun.standup_streak(state, next_mon) == 6  # the weekend doesn't count against him
    assert fun.standup_streak(state, next_mon + dt.timedelta(days=1)) == 6  # still alive on Tuesday
    assert fun.standup_streak(state, next_mon + dt.timedelta(days=2)) == 0  # missed Tuesday: broken
    assert fun.best_streak(state) == 6
    assert "best 6" in fun.streak_line(state, next_mon + dt.timedelta(days=3))
    assert "none yet" in fun.streak_line(State(state.path), FRI)


def test_on_fire_and_achievements(state):
    from teamguy import fun

    assert fun.unlocked(state) == []
    today = dt.date(2026, 11, 22)
    for i in range(5):
        t = state.add_task(f"ship {i}")
        t.update(status="done", accepted=f"2026-11-2{i % 3}T10:00:00", crew_used=["a", "b", "c"] if i == 0 else [])
    state.tasks[1]["feedback"] = [{"at": "x", "why": "more tests"}]
    assert fun.on_fire(state, today)
    assert not fun.on_fire(state, today + dt.timedelta(days=10))
    keys = {a.key for a in fun.unlocked(state)}
    assert {"first-ship", "comeback-kid", "crew-chief"} <= keys
    assert "regular" not in keys and "ten-ships" not in keys
    assert "ON FIRE" in fun.streak_line(state, today)


def test_level_shows_achievements_and_kudos_unlocks_one(team, capsys):
    f = str(team.base_dir / "team.yaml")
    for _ in range(3):
        assert main(["-f", f, "kudos", "nice"]) == 0
    out = capsys.readouterr().out
    assert out.count("Achievement unlocked") == 1 and "Fan Favorite" in out
    assert main(["-f", f, "level"]) == 0
    out = capsys.readouterr().out
    assert "Achievements (1/" in out and "Standup streak" in out and "🔒 First Ship" in out


# ─── weekly recap ────────────────────────────────────────────────────────────


def test_recap_counts_only_this_week_and_spots_new_achievements(team, state):
    from teamguy import fun

    today = dt.date(2026, 11, 22)
    old = state.add_task("ancient history")
    old.update(status="done", accepted="2026-11-01T10:00:00")
    state.data["log"].append({"at": "2026-11-01T10:00:00", "kind": "task_done", "xp": 40, "summary": "old"})
    new = state.add_task("fix the flaky test")
    new.update(status="done", accepted="2026-11-20T10:00:00", feedback=[{"at": "x", "why": "more tests"}])
    state.data["log"].append({"at": "2026-11-20T10:00:00", "kind": "task_done", "xp": 25, "summary": "new"})
    for d in ("2026-11-19", "2026-11-20"):
        state.data["log"].append({"at": f"{d}T09:30:00", "kind": "standup", "xp": 10, "summary": "standup", "day": d})
    state.add_task("waiting").update(status="review")

    out = fun.recap(team.guy, state, today)
    assert "Nov 16 – Nov 22" in out
    assert "#2 fix the flaky test" in out and "ancient history" not in out
    assert "+45" in out  # 25 XP task + 2 x 10 XP standups; the old 40 XP doesn't count
    assert "Standups: 2 attended" in out
    assert "Comeback Kid" in out and "First Ship" not in out  # first ship happened weeks ago
    assert "1 task in review" in out
    assert "\033[" not in out  # pasteable: no colors


def test_recap_quiet_week_and_cli(team, capsys):
    from teamguy import fun

    out = fun.recap(team.guy, State(team.state_dir / "state.json"), dt.date(2026, 11, 22))
    assert "nothing accepted" in out and "Quiet week" in out
    assert main(["-f", str(team.base_dir / "team.yaml"), "recap", "--days", "3"]) == 0
    assert "week in review" in capsys.readouterr().out


# ─── standup brag ────────────────────────────────────────────────────────────


def test_standup_brags_about_streak_and_new_achievements(team, state):
    from teamguy import fun

    def stood_up(day):
        state.data["log"].append({"at": f"{day}T09:30:00", "kind": "standup", "xp": 10,
                                  "summary": "standup", "day": day.isoformat()})

    mon = dt.date(2026, 11, 16)
    assert fun.brag_line(state, mon) == ""  # first standup, nothing to brag about
    assert "Brag:" not in render_update(team, state, mon)
    stood_up(mon)
    t = state.add_task("ship it")
    t.update(status="done", accepted="2026-11-16T15:00:00")
    state.data["log"].append({"at": "2026-11-16T15:00:00", "kind": "task_done", "xp": 20, "summary": "shipped"})

    tue = mon + dt.timedelta(days=1)
    line = fun.brag_line(state, tue)
    assert "2 standups in a row" in line and "🚢 First Ship" in line
    assert line in render_update(team, state, tue)

    stood_up(tue)
    wed = tue + dt.timedelta(days=1)
    line = fun.brag_line(state, wed)
    assert "3 standups in a row" in line and "First Ship" not in line  # already bragged on Tuesday

    for d in (wed, wed + dt.timedelta(days=1)):
        stood_up(d)
    fri = mon + dt.timedelta(days=4)
    line = fun.brag_line(state, fri)
    assert "🔥 5 standups in a row" in line and "☕ Regular" in line  # today's standup unlocks it
    stood_up(fri)
    assert "Regular" not in fun.brag_line(state, mon + dt.timedelta(days=7))


def test_backlog_bump_puts_a_task_first_in_line(team, state, capsys):
    f = str(team.base_dir / "team.yaml")
    run = lambda *a: main(["-f", f, *a])  # noqa: E731
    for title in ("one", "two", "three"):
        state.add_task(title)
    state.data["tasks"][0]["status"] = "review"
    state.save()
    assert State.load(team).next_task()["title"] == "two"
    assert run("backlog", "bump", "3") == 0
    assert "Bumped #3" in capsys.readouterr().out
    loaded = State.load(team)
    assert loaded.next_task()["id"] == 3
    assert [t["id"] for t in loaded.tasks] == [3, 1, 2]
    assert run("backlog", "bump", "3") == 0
    assert "already first" in capsys.readouterr().out
    assert run("backlog", "bump", "1") == 1  # in review, can't cut the line
    assert run("backlog", "bump", "99") == 1
    assert loaded.add_task("four")["id"] == 4  # ids stay unique after reordering


def test_backlog_effort_reestimates_a_todo(team, state, capsys):
    f = str(team.base_dir / "team.yaml")
    run = lambda *a: main(["-f", f, *a])  # noqa: E731
    state.add_task("quick fix", 2)
    state.add_task("shipped thing", 2)["status"] = "review"
    state.save()
    xp_before = State.task_xp(State.load(team).task(1))

    assert run("backlog", "effort", "1", "3") == 0
    out = capsys.readouterr().out
    assert "☕☕ → ☕☕☕" in out and "XP" in out and "sequel" not in out
    assert State.load(team).task(1)["effort"] == 3
    assert State.task_xp(State.load(team).task(1)) > xp_before

    assert run("backlog", "effort", "1", "4") == 0
    assert "sequel" in capsys.readouterr().out  # past 3 coffees gets cheeky
    assert run("backlog", "effort", "1", "5") == 0
    assert "retro" in capsys.readouterr().out
    assert run("backlog", "effort", "1", "1") == 0
    assert "Smaller than it looked" in capsys.readouterr().out
    assert run("backlog", "effort", "1", "1") == 0
    assert "already" in capsys.readouterr().out

    assert run("backlog", "effort", "1", "9") == 1  # out of range
    assert run("backlog", "effort", "2", "3") == 1  # in review: too late
    assert run("backlog", "effort", "99", "3") == 1
    assert State.load(team).task(1)["effort"] == 1
    assert State.load(team).task(2)["effort"] == 2


def test_stale_reviews_get_nagged(team, state, capsys):
    from teamguy import fun

    mon = dt.date(2026, 11, 16)
    fresh, stale, ancient = (state.add_task(t) for t in ("fresh", "stale", "ancient"))
    fresh.update(status="review", finished="2026-11-16T09:00:00")
    stale.update(status="review", finished="2026-11-13T09:00:00")
    ancient.update(status="review", finished="2026-11-09T09:00:00")
    assert [State.review_age(t, mon) for t in (fresh, stale, ancient)] == [0, 3, 7]
    assert State.review_age({"status": "todo", "finished": "2026-11-01T00:00:00"}, mon) == 0

    blockers = render_update(team, state, mon)
    assert "#1 fresh is waiting on your review (`teamguy accept 1`)\n" in blockers
    assert "#2 stale is waiting on your review (`teamguy accept 2`) ⏳ 3 days and counting" in blockers
    assert "🕸️ 7 days, cobwebs forming" in blockers

    recap = fun.recap(team.guy, state, mon)
    assert "3 tasks in review" in recap and "Oldest: #3, 7 days." in recap

    fresh["finished"] = dt.datetime.now().isoformat(timespec="seconds")  # backlog ages from the real today
    state.save()
    assert main(["-f", str(team.base_dir / "team.yaml"), "backlog"]) == 0
    out = capsys.readouterr().out
    assert "cobwebs forming" in out and out.count("days") == 2  # the fresh one isn't nagged
