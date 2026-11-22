"""Streaks, badges and achievements: bragging rights computed from the work log.

Nothing here is stored. Everything is derived from `state.json` on the fly, so
old state files get their achievements retroactively.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set

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
