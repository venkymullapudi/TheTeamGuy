"""Streaks, badges and achievements: bragging rights computed from the work log.

Nothing here is stored. Everything is derived from `state.json` on the fly, so
old state files get their achievements retroactively.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Union

from .state import State

ON_FIRE_TASKS = 5  # accepted tasks in the last 7 days to be 🔥 on fire
ON_FIRE_DAYS = 7


def _prev_workday(day: dt.date) -> dt.date:
    day -= dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def standup_days(state: State) -> Set[dt.date]:
    """Days a standup was attended (the meeting day, not when it was logged)."""
    return {dt.date.fromisoformat(e.get("day", e["at"][:10])) for e in state.data["log"] if e["kind"] == "standup"}


def _runs(days: Set[dt.date]) -> List[List[dt.date]]:
    """Group days into streaks of consecutive workdays. Weekends don't break a streak."""
    runs: List[List[dt.date]] = []
    for day in sorted(days):
        if runs and _prev_workday(day) <= runs[-1][-1]:
            runs[-1].append(day)
        else:
            runs.append([day])
    return runs


def standup_streak(state: State, today: Optional[dt.date] = None) -> int:
    """Current streak: consecutive workdays with a standup, still alive if the last
    one was today or the previous workday."""
    today = today or dt.date.today()
    runs = _runs({d for d in standup_days(state) if d <= today})
    if not runs:
        return 0
    last = runs[-1]
    return len(last) if last[-1] >= _prev_workday(today) else 0


def best_streak(state: State) -> int:
    return max((len(r) for r in _runs(standup_days(state))), default=0)


def accepted_since(state: State, since: dt.date) -> int:
    return sum(1 for t in state.tasks if t["status"] == "done" and t.get("accepted", "")[:10] >= since.isoformat())


def on_fire(state: State, today: Optional[dt.date] = None) -> bool:
    """🔥 when a week's worth of accepted work landed in the last 7 days."""
    today = today or dt.date.today()
    return accepted_since(state, today - dt.timedelta(days=ON_FIRE_DAYS - 1)) >= ON_FIRE_TASKS


@dataclass
class Achievement:
    key: str
    emoji: str
    title: str
    blurb: str
    check: Callable[[State], bool]


def _kinds(state: State, kind: str) -> int:
    return sum(1 for e in state.data["log"] if e["kind"] == kind)


def _done(state: State) -> List[Dict]:
    return [t for t in state.tasks if t["status"] == "done"]


ACHIEVEMENTS: List[Achievement] = [
    Achievement("first-ship", "🚢", "First Ship", "Got a task accepted.", lambda s: bool(_done(s))),
    Achievement("comeback-kid", "🥊", "Comeback Kid", "Got a task accepted after it was rejected.",
                lambda s: any(t.get("feedback") for t in _done(s))),
    Achievement("crew-chief", "🧑‍✈️", "Crew Chief", "Shipped a task with 3+ crew members.",
                lambda s: any(len(t.get("crew_used") or []) >= 3 for t in _done(s))),
    Achievement("regular", "☕", "Regular", "Hit a 5-standup streak.", lambda s: best_streak(s) >= 5),
    Achievement("fan-favorite", "💌", "Fan Favorite", "Collected 3 kudos.", lambda s: _kinds(s, "kudos") >= 3),
    Achievement("ten-ships", "🏭", "Shipyard", "Got 10 tasks accepted.", lambda s: len(_done(s)) >= 10),
]


def unlocked(state: State) -> List[Achievement]:
    return [a for a in ACHIEVEMENTS if a.check(state)]


def streak_line(state: State, today: Optional[dt.date] = None) -> str:
    today = today or dt.date.today()
    cur, best = standup_streak(state, today), best_streak(state)
    if cur:
        flame = "🔥" * min(cur, 5)
        line = f"  {flame} Standup streak: {cur} workday{'s' if cur != 1 else ''} (best {best})"
    elif best:
        line = f"  🧊 Standup streak: 0 (best {best}). Show up tomorrow and relight it."
    else:
        line = "  🕯️  Standup streak: none yet. `teamguy standup --join` to start one."
    if on_fire(state, today):
        line += f"\n  🔥 ON FIRE: {accepted_since(state, today - dt.timedelta(days=ON_FIRE_DAYS - 1))} tasks accepted this week. Someone get this guy a fire extinguisher."
    return line


# ─── weekly recap ────────────────────────────────────────────────────────────

RECAP_DAYS = 7


def as_of(state: State, cutoff: Union[dt.date, str]) -> State:
    """The guy's state as it stood before `cutoff`: later log entries are dropped
    and tasks accepted on or after it are back in review. Used to tell which
    achievements are new this week."""
    iso = cutoff if isinstance(cutoff, str) else cutoff.isoformat()  # a date or an ISO timestamp
    tasks = []
    for t in state.tasks:
        t = dict(t)
        if t["status"] == "done" and t.get("accepted", "") >= iso:
            t["status"] = "review"
        tasks.append(t)
    log = [e for e in state.data["log"] if e["at"] < iso and e.get("day", e["at"][:10]) < iso]
    return State(state.path, {**state.data, "tasks": tasks, "log": log})


def recap(guy: str, state: State, today: Optional[dt.date] = None, days: int = RECAP_DAYS) -> str:
    """A short, pasteable week-in-review for the team channel. Plain text, no colors."""
    today = today or dt.date.today()
    since = today - dt.timedelta(days=max(1, days) - 1)
    lo, hi = since.isoformat(), today.isoformat()
    in_window = lambda iso: lo <= iso[:10] <= hi  # noqa: E731

    shipped = [t for t in state.tasks if t["status"] == "done" and in_window(t.get("accepted", ""))]
    xp = sum(int(e.get("xp", 0)) for e in state.data["log"] if in_window(e["at"]))
    standups = sum(1 for d in standup_days(state) if since <= d <= today)
    kudos = sum(1 for e in state.data["log"] if e["kind"] == "kudos" and in_window(e["at"]))
    before = {a.key for a in unlocked(as_of(state, since))}
    new = [a for a in unlocked(state) if a.key not in before]
    streak = standup_streak(state, today)

    lines = [f"📰 {guy}'s week in review ({since:%b %d} – {today:%b %d})", ""]
    if shipped:
        lines.append(f"🚢 Shipped {len(shipped)} task{'s' if len(shipped) != 1 else ''}:")
        lines += [f"   • #{t['id']} {t['title']}" for t in shipped]
    else:
        lines.append("🚢 Shipped: nothing accepted this week. The backlog is plotting something.")
    lines.append(f"✨ XP earned: +{xp} (total {state.xp}, L{state.level.number} {state.level.name(guy)})")
    lines.append(f"☕ Standups: {standups} attended · streak {streak}" + (" 🔥" if streak >= 5 else ""))
    if kudos:
        lines.append(f"💌 Kudos received: {kudos}. Not that anyone's counting. (He's counting.)")
    if new:
        lines.append("🏆 New achievements: " + ", ".join(f"{a.emoji} {a.title}" for a in new))
    if on_fire(state, today):
        lines.append("🔥 Status: on fire. Please do not feed the guy more coffee.")
    review = state.in_review()
    waiting = len(review)
    if waiting:
        line = f"👀 Waiting on you: {waiting} task{'s' if waiting != 1 else ''} in review (`teamguy accept <id>`)."
        oldest = max(review, key=lambda t: State.review_age(t, today))
        age = State.review_age(oldest, today)
        if age >= 2:
            line += f" Oldest: #{oldest['id']}, {age} days."
        lines.append(line)
    if not (shipped or xp or standups):
        lines.append("")
        lines.append("Quiet week. He was definitely thinking very hard the whole time.")
    return "\n".join(lines)


# ─── standup brag ────────────────────────────────────────────────────────────


def _with_standup(state: State, day: dt.date) -> State:
    """The state as if he's at today's standup (the update is what he says there)."""
    if day in standup_days(state):
        return state
    entry = {"at": f"{day.isoformat()}T09:00:00", "kind": "standup", "xp": 0, "summary": "standup", "day": day.isoformat()}
    return State(state.path, {**state.data, "log": state.data["log"] + [entry]})


def brag_line(state: State, day: Optional[dt.date] = None) -> str:
    """One humble-ish line for the standup update: the streak this standup makes,
    plus achievements unlocked since the last standup. Empty when there's
    nothing to brag about."""
    day = day or dt.date.today()
    now = _with_standup(state, day)
    streak = standup_streak(now, day)
    earlier = sorted(
        (dt.date.fromisoformat(e.get("day", e["at"][:10])), e["at"]) for e in state.data["log"]
        if e["kind"] == "standup" and e.get("day", e["at"][:10]) < day.isoformat()
    )
    before: Set[str] = set()
    if earlier:  # what he had right when he last stood up (that standup included)
        last_day, last_at = earlier[-1]
        before = {a.key for a in unlocked(_with_standup(as_of(state, last_at), last_day))}
    new = [a for a in unlocked(now) if a.key not in before]
    bits = []
    if streak >= 2:
        bits.append(f"{'🔥' if streak >= 5 else '☕'} {streak} standups in a row")
    if new:
        bits.append("🏆 unlocked " + ", ".join(f"{a.emoji} {a.title}" for a in new))
    if not bits:
        return ""
    tail = " Not that I'm counting." if len(bits) == 1 else " Okay, I'm counting."
    return "Brag: " + " · ".join(bits) + "." + tail
