import datetime as dt
from pathlib import Path

import pytest
import yaml

from teamguy import persona
from teamguy.cadence import describe, is_due, validate_cadence
from teamguy.cli import main
from teamguy.config import TeamConfigError, guy_name, guy_slug, load_team, parse_team, render_template

FRI = dt.date(2026, 11, 20)  # Friday, ISO week 47 (odd, so no biweekly duties)


@pytest.fixture
def team():
    return parse_team(yaml.safe_load(render_template("SIM")))


# ─── naming ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "team_name, guy, slug",
    [
        ("SIM", "TheSIMGuy", "the-sim-guy"),
        ("data platform", "TheDataPlatformGuy", "the-data-platform-guy"),
        ("k8s-infra", "TheK8sInfraGuy", "the-k8s-infra-guy"),
        ("iOS", "TheIOSGuy", "the-ios-guy"),
    ],
)
def test_guy_name(team_name, guy, slug):
    assert guy_name(team_name) == guy
    assert guy_slug(team_name) == slug


def test_guy_name_needs_letters():
    with pytest.raises(TeamConfigError):
        guy_name("!!!")


# ─── config ──────────────────────────────────────────────────────────────────


def test_template_tokens_are_rendered(team):
    assert team.guy == "TheSIMGuy"
    assert "TheSIMGuy" in team.roster
    assert all("$GUY" not in f.a and "$TEAM" not in f.a for f in team.faq)
    assert "#SIM-incidents" in team.duty("oncall").checklist[2]


def test_repo_team_yaml_is_valid():
    t = load_team(Path(__file__).parent.parent / "team.yaml")
    assert t.guy == "TheSIMGuy"
    assert len(t.duties) >= 10


def test_unrendered_template_is_rejected():
    from teamguy.config import TEMPLATE_PATH

    with pytest.raises(TeamConfigError, match="teamguy init"):
        parse_team(yaml.safe_load(TEMPLATE_PATH.read_text()))


@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda r: r.update(duties=[]), "no duties"),
        (lambda r: r["duties"][0].update(cadence="hourly"), "unknown cadence"),
        (lambda r: r["duties"][0].update(effort=9), "effort"),
        (lambda r: r["duties"].append(dict(r["duties"][0])), "Duplicate"),
        (lambda r: r["duties"][0].pop("title"), "missing: title"),
    ],
)
def test_validation_errors(mutate, msg):
    raw = yaml.safe_load(render_template("SIM"))
    mutate(raw)
    with pytest.raises(TeamConfigError, match=msg):
        parse_team(raw)


# ─── cadence ─────────────────────────────────────────────────────────────────


def test_cadences():
    mon, sat = dt.date(2026, 11, 16), dt.date(2026, 11, 21)
    assert is_due("always", sat)
    assert is_due("weekdays", mon) and not is_due("weekdays", sat)
    assert is_due("weekly:mon,thu", mon) and not is_due("weekly:mon,thu", FRI)
    assert is_due("monthly:1", dt.date(2026, 12, 1))
    assert is_due("monthly:last", dt.date(2026, 2, 28))
    assert is_due("monthly:31", dt.date(2026, 2, 28))  # clamps to month end
    assert is_due("quarterly", dt.date(2026, 1, 5)) and not is_due("quarterly", dt.date(2026, 2, 2))
    assert not is_due("on-demand", mon)
    tue_even, tue_odd = dt.date(2026, 11, 24), dt.date(2026, 11, 17)  # ISO weeks 48, 47
    assert is_due("biweekly:tue", tue_even) and not is_due("biweekly:tue", tue_odd)


def test_cadence_validation_and_describe():
    with pytest.raises(ValueError):
        validate_cadence("weekly:funday")
    with pytest.raises(ValueError):
        validate_cadence("monthly:40")
    assert describe("biweekly:fri") == "every other Fri"
    assert describe("monthly:2") == "monthly on the 2nd"


# ─── persona ─────────────────────────────────────────────────────────────────


def test_today_lists_due_duties(team):
    out = persona.today(team, FRI)
    assert "On-Call Firefighter" in out
    assert "Flaky Test Whisperer" not in out  # Wednesdays only
    assert "If summoned" in out


def test_standup_is_deterministic(team):
    assert persona.standup(team, FRI) == persona.standup(team, FRI)
    assert "Blockers:" in persona.standup(team, FRI)


def test_ask_finds_answers(team):
    assert "DNS" in persona.ask(team, "why is my build red?")
    assert "Tuesday" in persona.ask(team, "can I deploy on a friday")
    assert "❝" not in persona.ask(team, "what is the airspeed of an unladen swallow")


def test_oncall_rotation(team):
    start = dt.date(2026, 1, 5)
    assert persona.oncall_for(team, start) == "TheSIMGuy"
    assert persona.oncall_for(team, start + dt.timedelta(days=7)) == "Alex"
    assert persona.oncall_for(team, start + dt.timedelta(days=6)) == "TheSIMGuy"
    assert persona.oncall_for(team, start + dt.timedelta(weeks=4)) == "TheSIMGuy"


def test_oncall_defaults_to_the_guy(team):
    team.roster = []
    assert persona.oncall_for(team, FRI) == "TheSIMGuy"


def test_card_and_whoami(team):
    assert "TheSIMGuy" in persona.card(team)
    assert persona.card(team) == persona.card(team)  # stats are stable
    assert "Mission" in persona.whoami(team)


def test_agent_markdown(team):
    md = persona.agent_markdown(team)
    assert md.startswith("---\nname: the-sim-guy\n")
    assert "Release Captain" in md


# ─── CLI ─────────────────────────────────────────────────────────────────────


def test_cli_end_to_end(tmp_path, capsys):
    f = tmp_path / "team.yaml"
    assert main(["-f", str(f), "init", "Data Platform"]) == 0
    assert "TheDataPlatformGuy" in capsys.readouterr().out
    assert main(["-f", str(f), "init", "Again"]) == 1  # no clobbering

    for cmd in (["whoami"], ["duties", "-v"], ["duty", "oncall"], ["today", "--date", "2026-11-20"],
                ["standup"], ["oncall"], ["ask", "where", "are", "docs"], ["excuse"], ["card"], ["validate"]):
        assert main(["-f", str(f), *cmd]) == 0, cmd

    out = tmp_path / "agent.md"
    assert main(["-f", str(f), "agent", "-o", str(out)]) == 0
    assert "the-data-platform-guy" in out.read_text()

    assert main(["-f", str(f), "duty", "nope"]) == 1


def test_cli_missing_file(tmp_path, capsys):
    assert main(["-f", str(tmp_path / "nope.yaml"), "whoami"]) == 2
    assert "teamguy init" in capsys.readouterr().err
