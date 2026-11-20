"""Loading and validating team.yaml, and naming the legend."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional

import yaml

from .cadence import validate_cadence

TEMPLATE_PATH = Path(__file__).parent / "templates" / "team.yaml"


class TeamConfigError(ValueError):
    """team.yaml is missing something, or is malformed."""


def _words(team: str) -> List[str]:
    words = re.sub(r"[^0-9A-Za-z]+", " ", team).split()
    if not words:
        raise TeamConfigError(
            f"Team name {team!r} needs at least one letter or digit. "
            "Even 'TheGuy' needs a team."
        )
    return words


def guy_name(team: str) -> str:
    """'SIM' -> 'TheSIMGuy', 'data platform' -> 'TheDataPlatformGuy'."""
    return "The" + "".join(w[0].upper() + w[1:] for w in _words(team)) + "Guy"


def guy_slug(team: str) -> str:
    """'SIM' -> 'the-sim-guy'."""
    return "the-" + "-".join(w.lower() for w in _words(team)) + "-guy"


@dataclass
class Duty:
    id: str
    title: str
    cadence: str
    description: str
    emoji: str = "🛠️"
    effort: int = 1
    checklist: List[str] = field(default_factory=list)
    catchphrase: str = ""


@dataclass
class FAQ:
    q: str
    a: str
    keywords: List[str] = field(default_factory=list)


@dataclass
class Team:
    name: str
    guy: str
    slug: str
    mission: str
    emoji: str
    duties: List[Duty]
    catchphrases: List[str] = field(default_factory=list)
    superpowers: List[str] = field(default_factory=list)
    kryptonite: List[str] = field(default_factory=list)
    faq: List[FAQ] = field(default_factory=list)
    roster: List[str] = field(default_factory=list)
    rotation_start: Optional[dt.date] = None
    blockers: List[str] = field(default_factory=list)
    excuses: List[str] = field(default_factory=list)

    def duty(self, duty_id: str) -> Optional[Duty]:
        return next((d for d in self.duties if d.id == duty_id), None)


def _render(value: Any, tokens: Dict[str, str]) -> Any:
    """Recursively replace $TEAM / $GUY in every string."""
    if isinstance(value, str):
        return Template(value).safe_substitute(tokens)
    if isinstance(value, list):
        return [_render(v, tokens) for v in value]
    if isinstance(value, dict):
        return {k: _render(v, tokens) for k, v in value.items()}
    return value


def _str_list(raw: Dict[str, Any], key: str) -> List[str]:
    value = raw.get(key) or []
    if not isinstance(value, list):
        raise TeamConfigError(f"'{key}' should be a list.")
    return [str(v) for v in value]


def parse_team(raw: Any) -> Team:
    if not isinstance(raw, dict):
        raise TeamConfigError("team.yaml should be a mapping at the top level.")
    name = raw.get("team")
    if not name or not str(name).strip() or "{{" in str(name):
        raise TeamConfigError(
            "team.yaml needs a 'team:' name. Run `teamguy init <TEAM>` to make one."
        )
    name = str(name).strip()
    guy = guy_name(name)
    raw = _render(raw, {"TEAM": name, "GUY": guy})

    duties_raw = raw.get("duties") or []
    if not isinstance(duties_raw, list) or not duties_raw:
        raise TeamConfigError(f"{guy} has no duties?! Add at least one under 'duties:'.")
    duties: List[Duty] = []
    seen = set()
    for i, d in enumerate(duties_raw):
        if not isinstance(d, dict):
            raise TeamConfigError(f"duties[{i}] should be a mapping.")
        missing = [k for k in ("id", "title", "cadence", "description") if not d.get(k)]
        if missing:
            raise TeamConfigError(f"duties[{i}] is missing: {', '.join(missing)}")
        if d["id"] in seen:
            raise TeamConfigError(f"Duplicate duty id {d['id']!r}.")
        seen.add(d["id"])
        try:
            validate_cadence(str(d["cadence"]))
        except ValueError as exc:
            raise TeamConfigError(f"duty {d['id']!r}: {exc}") from None
        effort = int(d.get("effort", 1))
        if not 1 <= effort <= 5:
            raise TeamConfigError(f"duty {d['id']!r}: effort must be 1–5 coffees.")
        duties.append(
            Duty(
                id=str(d["id"]),
                title=str(d["title"]),
                cadence=str(d["cadence"]),
                description=str(d["description"]),
                emoji=str(d.get("emoji", "🛠️")),
                effort=effort,
                checklist=[str(c) for c in d.get("checklist") or []],
                catchphrase=str(d.get("catchphrase", "")),
            )
        )

    faq = []
    for i, f in enumerate(raw.get("faq") or []):
        if not isinstance(f, dict) or not f.get("q") or not f.get("a"):
            raise TeamConfigError(f"faq[{i}] needs both 'q' and 'a'.")
        faq.append(FAQ(q=str(f["q"]), a=str(f["a"]), keywords=[str(k) for k in f.get("keywords") or []]))

    oncall = raw.get("oncall") or {}
    rotation_start = oncall.get("rotation_start")
    if isinstance(rotation_start, str):
        try:
            rotation_start = dt.date.fromisoformat(rotation_start)
        except ValueError:
            raise TeamConfigError("oncall.rotation_start should be YYYY-MM-DD.") from None

    return Team(
        name=name,
        guy=guy,
        slug=guy_slug(name),
        mission=str(raw.get("mission", f"Keep {name} running.")),
        emoji=str(raw.get("emoji", "🦸")),
        duties=duties,
        catchphrases=_str_list(raw, "catchphrases"),
        superpowers=_str_list(raw, "superpowers"),
        kryptonite=_str_list(raw, "kryptonite"),
        faq=faq,
        roster=[str(p) for p in oncall.get("roster") or []],
        rotation_start=rotation_start,
        blockers=_str_list(raw, "blockers"),
        excuses=_str_list(raw, "excuses"),
    )


def load_team(path: Path) -> Team:
    if not path.exists():
        raise TeamConfigError(
            f"No {path} found. Summon your guy first: `teamguy init <TEAM>`"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TeamConfigError(f"{path} isn't valid YAML (probably a tab somewhere):\n{exc}") from None
    return parse_team(raw)


def render_template(team: str) -> str:
    guy_name(team)  # validates
    safe = team.strip().replace("\\", "").replace('"', "")
    return TEMPLATE_PATH.read_text(encoding="utf-8").replace("{{TEAM}}", safe)
