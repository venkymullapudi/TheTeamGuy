"""When is a duty due? Tiny cadence language for team.yaml.

    always          every day, forever (sorry)
    daily           every day
    weekdays        Monday–Friday
    weekly:mon,thu  those weekdays
    biweekly:fri    that weekday, every even ISO week
    monthly:15      that day of the month (or `monthly:last`)
    quarterly       first Monday of Jan/Apr/Jul/Oct
    on-demand       only when summoned
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import List

DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _days(spec: str) -> List[int]:
    out = []
    for part in spec.split(","):
        part = part.strip().lower()[:3]
        if part not in DAYS:
            raise ValueError(f"unknown weekday {part!r} (use mon, tue, …)")
        out.append(DAYS[part])
    return out


def validate_cadence(cadence: str) -> None:
    c = cadence.strip().lower()
    if c in ("always", "daily", "weekdays", "quarterly", "on-demand"):
        return
    kind, _, arg = c.partition(":")
    if kind in ("weekly", "biweekly") and arg:
        _days(arg)
        return
    if kind == "monthly" and arg:
        if arg == "last" or (arg.isdigit() and 1 <= int(arg) <= 31):
            return
        raise ValueError(f"monthly needs a day 1–31 or 'last', got {arg!r}")
    raise ValueError(f"unknown cadence {cadence!r}")


def is_due(cadence: str, day: dt.date) -> bool:
    c = cadence.strip().lower()
    if c in ("always", "daily"):
        return True
    if c == "weekdays":
        return day.weekday() < 5
    if c == "on-demand":
        return False
    if c == "quarterly":
        return day.month in (1, 4, 7, 10) and day.weekday() == 0 and day.day <= 7
    kind, _, arg = c.partition(":")
    if kind == "weekly":
        return day.weekday() in _days(arg)
    if kind == "biweekly":
        return day.weekday() in _days(arg) and day.isocalendar()[1] % 2 == 0
    if kind == "monthly":
        last = calendar.monthrange(day.year, day.month)[1]
        target = last if arg == "last" else min(int(arg), last)
        return day.day == target
    raise ValueError(f"unknown cadence {cadence!r}")


def describe(cadence: str) -> str:
    c = cadence.strip().lower()
    simple = {
        "always": "24/7/365 (send help)",
        "daily": "every day",
        "weekdays": "every weekday",
        "quarterly": "every quarter",
        "on-demand": "when summoned",
    }
    if c in simple:
        return simple[c]
    kind, _, arg = c.partition(":")
    if kind in ("weekly", "biweekly"):
        names = "/".join(DAY_NAMES[d] for d in _days(arg))
        return f"{'every other' if kind == 'biweekly' else 'every'} {names}"
    if kind == "monthly":
        return "last day of the month" if arg == "last" else f"monthly on the {_ordinal(int(arg))}"
    return cadence


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
