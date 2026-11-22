"""The career ladder. Every contribution earns XP; XP earns trust; trust earns tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Level:
    number: int
    title: str
    xp: int
    perk: str
    badge: str

    def name(self, guy: str) -> str:
        return self.title.replace("{guy}", guy)

    def perk_for(self, guy: str) -> str:
        return self.perk.replace("{guy}", guy)


LADDER: List[Level] = [
    Level(0, "New Hire", 0, "Reads docs and uses beginner skills. Must finish onboarding.", "🐣"),
    Level(1, "Intern", 100, "Can hand work to entry-level crew (LLM helpers).", "🎒"),
    Level(2, "Junior {guy}", 300, "Can run team commands like the test suite.", "🔧"),
    Level(3, "Teammate", 700, "Files follow-up tasks on their own backlog.", "🤝"),
    Level(4, "Senior {guy}", 1500, "More steps per task; unlocks senior crew like Claude Code.", "🧭"),
    Level(5, "Staff {guy}", 3000, "Picks up backlog work on their own (`teamguy work --next`).", "🏗️"),
    Level(6, "Principal {guy}", 6000, "Every crew member and skill, no questions asked.", "🔮"),
    Level(7, "Legendary {guy}", 10000, "Has become the one and only {guy}. Songs are sung.", "👑"),
]

FOLLOWUP_LEVEL = 3
AUTOPICK_LEVEL = 5

# XP table — what each contribution is worth.
XP = {
    "task_done_per_effort": 20,
    "task_blocked": 5,
    "teamwork_per_member": 5,
    "standup": 10,
    "standup_action_item": 5,
    "kudos": 15,
}


def level_for(xp: int, onboarded: bool) -> Level:
    if not onboarded:
        return LADDER[0]
    return [lvl for lvl in LADDER if xp >= lvl.xp][-1]


def next_level(level: Level) -> Optional[Level]:
    return LADDER[level.number + 1] if level.number + 1 < len(LADDER) else None


def max_steps(level: Level) -> int:
    """How many model turns the guy gets per task. Seniors get more rope."""
    return 4 + 2 * level.number


def token_budget(base: int, level: Level) -> int:
    """Tokens the guy may spend on one task: the base, plus half again per level. 0 = no limit."""
    return max(0, base) * (2 + level.number) // 2


def progress_bar(xp: int, level: Level, width: int = 24) -> str:
    nxt = next_level(level)
    if nxt is None:
        return "█" * width + "  MAX"
    span = nxt.xp - level.xp
    done = max(0, min(span, xp - level.xp))
    filled = round(done / span * width) if span else width
    return "█" * filled + "░" * (width - filled) + f"  {xp}/{nxt.xp} XP"
