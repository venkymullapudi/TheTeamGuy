"""The guy's memory: XP, backlog, work log, onboarding progress, notes.

Stored as JSON in `.teamguy/state.json` next to team.yaml.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Team
from .levels import XP, Level, level_for

ONBOARDING_QUESTS = ("meet-the-team", "read-the-docs", "learn-the-duties", "meet-the-crew", "first-task")


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


@dataclass
class Award:
    xp: int
    before: Level
    after: Level

    @property
    def leveled_up(self) -> bool:
        return self.after.number > self.before.number


class State:
    def __init__(self, path: Path, data: Optional[Dict[str, Any]] = None):
        self.path = path
        self.data: Dict[str, Any] = data or {}
        self.data.setdefault("xp", 0)
        self.data.setdefault("onboarding", {})
        self.data.setdefault("tasks", [])
        self.data.setdefault("log", [])
        self.data.setdefault("knowledge", {})

    # ─── persistence ─────────────────────────────────────────────────────
    @classmethod
    def load(cls, team: Team) -> "State":
        path = team.state_dir / "state.json"
        if path.exists():
            return cls(path, json.loads(path.read_text(encoding="utf-8")))
        return cls(path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ─── XP & levels ─────────────────────────────────────────────────────
    @property
    def xp(self) -> int:
        return int(self.data["xp"])

    @property
    def onboarded(self) -> bool:
        return all(q in self.data["onboarding"] for q in ONBOARDING_QUESTS)

    @property
    def level(self) -> Level:
        return level_for(self.xp, self.onboarded)

    def award(self, kind: str, xp: int, summary: str, **extra: Any) -> Award:
        before = self.level
        self.data["xp"] = self.xp + xp
        self.data["log"].append({"at": _now(), "kind": kind, "xp": xp, "summary": summary, **extra})
        return Award(xp, before, self.level)

    def complete_quest(self, quest: str, xp: int, summary: str) -> Optional[Award]:
        if quest in self.data["onboarding"]:
            return None
        before = self.level
        self.data["onboarding"][quest] = _now()
        self.award("onboarding", xp, summary, quest=quest)
        return Award(xp, before, self.level)

    def log_since(self, since: dt.datetime) -> List[Dict[str, Any]]:
        return [e for e in self.data["log"] if dt.datetime.fromisoformat(e["at"]) >= since]

    def did_today(self, kind: str, day: dt.date) -> bool:
        """Was there a `kind` entry for `day`? Entries that carry their own `day`
        (a standup held for a given date) count for that date, not for when they
        were logged."""
        iso = day.isoformat()
        return any(e["kind"] == kind and e.get("day", e["at"][:10]) == iso for e in self.data["log"])

    # ─── backlog ─────────────────────────────────────────────────────────
    @property
    def tasks(self) -> List[Dict[str, Any]]:
        return self.data["tasks"]

    def add_task(self, title: str, effort: int = 2, source: str = "you") -> Dict[str, Any]:
        task = {
            "id": max((t["id"] for t in self.tasks), default=0) + 1,
            "title": title.strip(),
            "effort": max(1, min(5, int(effort))),
            "status": "todo",
            "source": source,
            "created": _now(),
        }
        self.tasks.append(task)
        return task

    def task(self, task_id: int) -> Optional[Dict[str, Any]]:
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def open_tasks(self) -> List[Dict[str, Any]]:
        return [t for t in self.tasks if t["status"] in ("todo", "blocked", "review")]

    def in_review(self) -> List[Dict[str, Any]]:
        return [t for t in self.tasks if t["status"] == "review"]

    @staticmethod
    def review_age(task: Dict[str, Any], today: Optional[dt.date] = None) -> int:
        """Whole days a task has been sitting in review (0 if not in review)."""
        if task.get("status") != "review" or not task.get("finished"):
            return 0
        today = today or dt.date.today()
        return max(0, (today - dt.date.fromisoformat(task["finished"][:10])).days)

    def next_task(self) -> Optional[Dict[str, Any]]:
        todo = [t for t in self.tasks if t["status"] == "todo"]
        return todo[0] if todo else None

    def bump_task(self, task: Dict[str, Any]) -> None:
        """Move a task to the front of the line so ``next_task`` picks it first."""
        self.tasks.remove(task)
        self.tasks.insert(0, task)

    def rename_task(self, task: Dict[str, Any], title: str) -> None:
        """Reword a task, keeping the old names so the history still makes sense."""
        task.setdefault("renamed", []).append({"at": _now(), "was": task["title"]})
        task["title"] = title.strip()

    def finish_task(self, task: Dict[str, Any], status: str, summary: str) -> None:
        task["status"] = status
        task["summary"] = summary
        task["finished"] = _now()

    # ─── review: XP is earned, not self-reported ─────────────────────────
    @staticmethod
    def task_xp(task: Dict[str, Any]) -> int:
        crew = task.get("crew_used") or []
        return XP["task_done_per_effort"] * int(task["effort"]) + XP["teamwork_per_member"] * len(crew)

    def accept_task(self, task: Dict[str, Any]) -> Award:
        """A human signs off: the task is done and the guy gets the XP."""
        if task["status"] != "review":
            raise ValueError(f"#{task['id']} is {task['status']}, not waiting for review")
        task["status"] = "done"
        task["accepted"] = _now()
        return self.award("task_done", self.task_xp(task), f"Shipped #{task['id']}: {task['title']}", task=task["id"])

    def reject_task(self, task: Dict[str, Any], why: str) -> Award:
        """Send it back with feedback; the next attempt sees every note."""
        if task["status"] != "review":
            raise ValueError(f"#{task['id']} is {task['status']}, not waiting for review")
        why = why.strip() or "Not quite. Try again."
        task["status"] = "todo"
        task.setdefault("feedback", []).append({"at": _now(), "why": why})
        return self.award("task_rejected", 0, f"Back to the drawing board on #{task['id']}: {why}", task=task["id"])

    def unblock_task(self, task: Dict[str, Any], note: str) -> Award:
        """Clear a blocker: back to todo with a note the next attempt sees."""
        if task["status"] != "blocked":
            raise ValueError(f"#{task['id']} is {task['status']}, not blocked")
        note = note.strip() or "The wall is gone. Go again."
        task["status"] = "todo"
        task.setdefault("unblocks", []).append({"at": _now(), "note": note})
        return self.award("task_unblocked", 0, f"Wall knocked down on #{task['id']}: {note}", task=task["id"])

    # ─── knowledge (what the guy learned) ────────────────────────────────
    def learn(self, topic: str, notes: str) -> None:
        self.data["knowledge"][topic] = notes.strip()

    def knowledge_text(self, limit: int = 6000) -> str:
        parts = [f"## {k}\n{v}" for k, v in self.data["knowledge"].items()]
        return "\n\n".join(parts)[:limit]


def stats(state: State) -> Tuple[int, int, int]:
    done = sum(1 for t in state.tasks if t["status"] == "done")
    standups = sum(1 for e in state.data["log"] if e["kind"] == "standup")
    return done, standups, len(state.open_tasks())
