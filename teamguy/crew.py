"""The guy's crew (other agents, LLMs and tools) and skills (playbooks).

Crew kinds:
  llm          another Claude persona with its own system prompt
  command      a fixed command (e.g. [pytest, -q]); the task arrives on stdin
               and in $TEAMGUY_TASK, never spliced into the command line
  claude-code  Claude Code in headless mode (`claude -p <task>`), which brings
               its own tools, subagents and skills

Skills are folders with a SKILL.md (frontmatter: name, description, min_level),
the same shape Claude Code skills use.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import yaml

from .config import CrewMember, Team


@dataclass
class Skill:
    name: str
    description: str
    body: str
    min_level: int = 0


def load_skills(team: Team) -> List[Skill]:
    root = team.base_dir / team.skills_dir
    skills: List[Skill] = []
    if not root.is_dir():
        return skills
    for path in sorted(root.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = {}, text
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
        if m:
            meta = yaml.safe_load(m.group(1)) or {}
            body = m.group(2)
        skills.append(
            Skill(
                name=str(meta.get("name", path.parent.name)),
                description=str(meta.get("description", "")),
                body=body.strip(),
                min_level=int(meta.get("min_level", 0)),
            )
        )
    return skills


def available(member: CrewMember) -> Optional[str]:
    """None if the member can be reached, else a reason why not."""
    if member.kind == "command":
        exe = member.command[0]
    elif member.kind == "claude-code":
        exe = (member.command or ["claude"])[0]
    else:
        return None
    return None if shutil.which(exe) else f"`{exe}` isn't installed"


def run_member(member: CrewMember, instructions: str, brain, team: Team) -> str:
    """Hand a piece of work to a crew member and return what they said."""
    if member.kind == "llm":
        system = member.system or f"You are {member.name}, a teammate on team {team.name}. {member.description}"
        return brain.complete(
            system=system,
            prompt=instructions,
            model=member.model,
            fallback=f"[{member.name}] (offline) Looked at it. Here's my take on: {instructions[:140]}",
        )

    reason = available(member)
    if reason:
        raise RuntimeError(f"{member.name} is unavailable: {reason}")

    if member.kind == "claude-code":
        argv = [*(member.command or ["claude"]), "-p", instructions]
        stdin = None
    else:
        argv = list(member.command)
        stdin = instructions
    env = {**os.environ, "TEAMGUY_TASK": instructions}
    try:
        proc = subprocess.run(
            argv, input=stdin, capture_output=True, text=True,
            timeout=member.timeout, cwd=team.base_dir, env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{member.name} timed out after {member.timeout}s") from None
    out = (proc.stdout or "")[-4000:]
    err = (proc.stderr or "")[-1500:]
    status = "ok" if proc.returncode == 0 else f"failed (exit {proc.returncode})"
    return f"[{member.name}: {status}]\n{out}" + (f"\n[stderr]\n{err}" if err.strip() else "")


def word_overlap(a: str, b: str) -> int:
    stop = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "it", "is", "with", "your", "this", "that"}
    wa = {w for w in re.findall(r"[a-z0-9]+", a.lower()) if w not in stop and len(w) > 2}
    wb = {w for w in re.findall(r"[a-z0-9]+", b.lower()) if w not in stop and len(w) > 2}
    return len(wa & wb)
