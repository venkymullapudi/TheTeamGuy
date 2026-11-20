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
from .levels import Level, level_for

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
        return any(e["kind"] == kind and e["at"].startswith(day.isoformat()) for e in self.data["log"])

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
        return [t for t in self.tasks if t["status"] in ("todo", "blocked")]

    def next_task(self) -> Optional[Dict[str, Any]]:
        todo = [t for t in self.tasks if t["status"] == "todo"]
        return todo[0] if todo else None

    def finish_task(self, task: Dict[str, Any], status: str, summary: str) -> None:
        task["status"] = status
        task["summary"] = summary
        task["finished"] = _now()

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
