"""Everything that makes The<Team>Guy *The<Team>Guy*. Pure functions -> strings."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import random
import re
import sys
import textwrap
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from .cadence import describe, is_due
from .config import FAQ, Duty, Team

# ─── tiny color helper ───────────────────────────────────────────────────────

_CODES = {"bold": "1", "dim": "2", "cyan": "36", "yellow": "33", "green": "32", "magenta": "35", "red": "31"}


def use_color() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def c(text: str, *styles: str) -> str:
    if not use_color():
        return text
    return "".join(f"\033[{_CODES[s]}m" for s in styles) + text + "\033[0m"


def coffee(n: int) -> str:
    return "☕" * n


def effort_quip(effort: int) -> str:
    """A cheeky line for when a task's estimate grows past 3 coffees."""
    if effort >= 5:
        return "Five coffees. Telling my family I'll see them at the retro."
    return "Four coffees? This 'quick fix' has a sequel."


COFFEES_PER_DAY = 4


def caffeine_quip(coffees: int) -> str:
    """How many workdays of caffeine the todo pile adds up to (4 ☕ a day)."""
    if coffees <= 0:
        return "Zero coffees owed. I could take a nap. I won't, but I could."
    days = coffees / COFFEES_PER_DAY
    if days <= 1:
        return "Under a day of caffeine. Basically a long lunch."
    if days <= 5:
        return f"That's ~{days:.1f} days of caffeine. Manageable, if the espresso machine holds."
    return f"That's ~{days:.1f} days of caffeine. Somebody order the beans in bulk."


def _rng(team: Team, *salt: object) -> random.Random:
    seed = "|".join([team.name, *map(str, salt)])
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))


# ─── banner / whoami ─────────────────────────────────────────────────────────


def banner(team: Team) -> str:
    title = f"  {team.guy}  "
    bar = "═" * len(title)
    return "\n".join(
        [
            c(f"   ╔{bar}╗", "cyan"),
            c(f"   ║", "cyan") + c(title, "bold", "yellow") + c("║", "cyan"),
            c(f"   ╚{bar}╝", "cyan"),
        ]
    )


FIGURE = r"""
        .-"-.
       /|6 6|\      ← has seen things in prod
      {/(_0_)\}
       _/ ^ \_      ← pager (always vibrating)
      (/ /^\ \)-'
       ""' '""
"""


def whoami(team: Team, rng: Optional[random.Random] = None) -> str:
    rng = rng or random.Random()
    lines = [banner(team), c(FIGURE, "dim")]
    lines.append(f"  {team.emoji}  {c(team.guy, 'bold')} of team {c(team.name, 'bold', 'cyan')}")
    lines.append(f"  Mission: {team.mission}")
    lines.append(f"  Juggling {c(str(len(team.duties)), 'bold')} duties "
                 f"for a weekly {coffee(min(5, max(1, weekly_coffee(team) // 5)))} "
                 f"(~{weekly_coffee(team)} cups/week)")
    if team.catchphrases:
        lines.append("")
        lines.append(c(f'  "{rng.choice(team.catchphrases)}"', "magenta"))
        lines.append(c(f"      — {team.guy}", "dim"))
    return "\n".join(lines)


def weekly_coffee(team: Team, start: Optional[dt.date] = None) -> int:
    start = start or dt.date.today()
    monday = start - dt.timedelta(days=start.weekday())
    week = [monday + dt.timedelta(days=i) for i in range(7)]
    return sum(d.effort for d in team.duties for day in week if is_due(d.cadence, day))


# ─── duties ──────────────────────────────────────────────────────────────────


def duty_line(d: Duty) -> str:
    return f"  {d.emoji}  {c(f'{d.title:<40}', 'bold')} {c(describe(d.cadence), 'cyan')}  {coffee(d.effort)}"


def duties_list(team: Team, verbose: bool = False) -> str:
    out = [c(f"Everything {team.guy} does (that we know of):", "bold"), ""]
    for d in team.duties:
        out.append(duty_line(d))
        if verbose:
            out.append(c(_wrap(d.description, 8), "dim"))
            for item in d.checklist:
                out.append(f"        ☐ {item}")
            if d.catchphrase:
                out.append(c(f'        "{d.catchphrase}"', "magenta"))
            out.append("")
    out.append("")
    out.append(c(f"  Run `teamguy duty <id>` for details. IDs: {', '.join(d.id for d in team.duties)}", "dim"))
    return "\n".join(out)


def duty_detail(d: Duty) -> str:
    out = [f"{d.emoji}  {c(d.title, 'bold')}  ({d.id})", ""]
    out.append(_wrap(d.description, 2))
    out.append("")
    out.append(f"  When:   {c(describe(d.cadence), 'cyan')}")
    out.append(f"  Effort: {coffee(d.effort)}")
    if d.checklist:
        out.append("")
        out.extend(f"  ☐ {item}" for item in d.checklist)
    if d.catchphrase:
        out.append("")
        out.append(c(f'  "{d.catchphrase}"', "magenta"))
    return "\n".join(out)


def due_on(team: Team, day: dt.date) -> List[Duty]:
    return [d for d in team.duties if is_due(d.cadence, day)]


def today(team: Team, day: dt.date) -> str:
    due = due_on(team, day)
    cups = sum(d.effort for d in due)
    header = f"{team.guy}'s agenda for {day:%A, %b %d %Y}"
    out = [c(header, "bold"), c("─" * len(header), "dim")]
    if not due:
        out.append(f"  Nothing scheduled. {team.guy} is free! (Narrator: they were not free.)")
    for d in due:
        out.append(duty_line(d))
    on_demand = [d for d in team.duties if d.cadence == "on-demand"]
    if on_demand:
        out.append("")
        out.append(c("  If summoned: ", "dim") + ", ".join(f"{d.emoji} {d.title}" for d in on_demand))
    out.append("")
    out.append(f"  Coffee forecast: {coffee(min(cups, 20))}  ({cups} cups) — {_coffee_verdict(cups)}")
    return "\n".join(out)


def _coffee_verdict(cups: int) -> str:
    if cups == 0:
        return "decaf day 🌴"
    if cups <= 6:
        return "a gentle simmer"
    if cups <= 12:
        return "a respectable grind"
    if cups <= 16:
        return "hold all calls"
    return "medically inadvisable"


# ─── standup ─────────────────────────────────────────────────────────────────


def standup(team: Team, day: dt.date) -> str:
    rng = _rng(team, "standup", day.isoformat())
    yesterday = day - dt.timedelta(days=3 if day.weekday() == 0 else 1)
    did = due_on(team, yesterday)
    rng.shuffle(did)
    doing = due_on(team, day)
    blocker = rng.choice(team.blockers) if team.blockers else "None"

    out = [c(f"🎤 {team.guy}'s standup — {day:%a %b %d}", "bold"), ""]
    out.append(c("Yesterday:", "yellow"))
    for d in did[:3] or []:
        out.append(f"  • {_past_tense(d, rng)}")
    if not did:
        out.append("  • Recovered. Emotionally.")
    out.append(c("Today:", "yellow"))
    for d in doing[:4]:
        out.append(f"  • {d.emoji} {d.title}")
    if not doing:
        out.append("  • Strategic napping")
    out.append(c("Blockers:", "yellow"))
    out.append(f"  • {blocker}")
    if team.catchphrases:
        out.append("")
        out.append(c(f'  "{rng.choice(team.catchphrases)}"', "magenta"))
    return "\n".join(out)


def _past_tense(d: Duty, rng: random.Random) -> str:
    templates = [
        "Crushed '{t}' {e}",
        "Did a heroic amount of '{t}' {e}",
        "Survived '{t}' {e}",
        "Quietly handled '{t}' so nobody else had to {e}",
    ]
    return rng.choice(templates).format(t=d.title, e=d.emoji)


# ─── ask ─────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "is", "do", "i", "to", "how", "why", "what", "where", "can", "my", "of", "on", "it", "in", "for", "this"}


def _tokens(text: str) -> set:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP}


def best_answer(team: Team, question: str) -> Tuple[Optional[FAQ], float]:
    qt = _tokens(question)
    best: Tuple[Optional[FAQ], float] = (None, 0.0)
    for f in team.faq:
        kw = {k.lower() for k in f.keywords} | _tokens(f.q)
        overlap = len(qt & kw) / max(1, len(qt))
        fuzzy = SequenceMatcher(None, question.lower(), f.q.lower()).ratio()
        score = 0.7 * overlap + 0.3 * fuzzy
        if score > best[1]:
            best = (f, score)
    return best


def ask(team: Team, question: str) -> str:
    faq, score = best_answer(team, question)
    if faq is None or score < 0.25:
        rng = random.Random(question)
        shrug = rng.choice(
            [
                "Hmm. Have you tried searching Slack for it?",
                "That's a great question for a thread in the team channel.",
                "I'll add it to the FAQ. Right after I fix the build.",
                "Let's take that offline. Like, very offline.",
            ]
        )
        return f"🤔 {c(team.guy, 'bold')}: {shrug}"
    return "\n".join(
        [
            c(f"  ❝ {faq.q} ❞", "dim"),
            f"💬 {c(team.guy, 'bold')}: {faq.a}",
        ]
    )


# ─── on-call ─────────────────────────────────────────────────────────────────


def oncall_for(team: Team, day: dt.date) -> str:
    if not team.roster:
        return team.guy
    start = team.rotation_start or dt.date(day.year, 1, 1)
    start -= dt.timedelta(days=start.weekday())  # snap to Monday
    week = (day - start).days // 7
    return team.roster[week % len(team.roster)]


def oncall(team: Team, day: dt.date, weeks: int = 4) -> str:
    who = oncall_for(team, day)
    out = [f"📟 On call for the week of {day - dt.timedelta(days=day.weekday()):%b %d}: {c(who, 'bold', 'yellow')}"]
    if who == team.guy:
        out.append(c("   (Of course it is.)", "dim"))
    else:
        out.append(c(f"   ({team.guy} is 'off'. {team.guy} will still see the page.)", "dim"))
    if weeks > 1:
        out.append("")
        out.append(c("   Upcoming:", "dim"))
        for w in range(1, weeks):
            d = day + dt.timedelta(weeks=w)
            out.append(f"   {d - dt.timedelta(days=d.weekday()):%b %d}  {oncall_for(team, d)}")
    return "\n".join(out)


# ─── excuse ──────────────────────────────────────────────────────────────────


def excuse(team: Team, rng: Optional[random.Random] = None) -> str:
    rng = rng or random.Random()
    pool = team.excuses or ["It's always DNS."]
    return f"🙃 {c(team.guy, 'bold')}: {rng.choice(pool)}"


# ─── trading card ────────────────────────────────────────────────────────────


def stat(team: Team, label: str, lo: int = 40, hi: int = 99) -> int:
    return _rng(team, "stat", label).randint(lo, hi)


def card(team: Team) -> str:
    rng = _rng(team, "card")
    width = 50
    top = "┏" + "━" * width + "┓"
    bot = "┗" + "━" * width + "┛"
    sep = "┠" + "─" * width + "┨"

    def row(text: str = "") -> str:
        return "┃ " + text

    cups = weekly_coffee(team)
    rarity = rng.choice(["✦ LEGENDARY", "✦ MYTHIC", "✦ ULTRA RARE", "✦ HOLO FOIL"])
    out = [
        c(top, "yellow"),
        row(c(f"{team.guy}", "bold") + "   " + c(rarity, "magenta")),
        row(c(f"Type: Ops / Glue / Psychic        HP: {stat(team, 'hp', 300, 999)}", "dim")),
        c(sep, "yellow"),
        row(f"Tribal Knowledge  {_meter(stat(team, 'knowledge', 85, 100))}"),
        row(f"Patience          {_meter(stat(team, 'patience', 15, 60))}"),
        row(f"Slack Response    {_meter(stat(team, 'slack', 90, 100))}"),
        row(f"Caffeine Intake   {_meter(min(100, cups * 3))}  {cups}/wk"),
        c(sep, "yellow"),
    ]
    for power in team.superpowers[:3]:
        out.append(row(c("⚡ ", "yellow") + power))
    for weak in team.kryptonite[:2]:
        out.append(row(c("💀 ", "red") + "Weak to: " + weak))
    out.append(c(sep, "yellow"))
    if team.catchphrases:
        out.append(row(c(f'"{rng.choice(team.catchphrases)}"', "magenta")))
    out.append(row(c(f"#{int(hashlib.md5(team.name.encode()).hexdigest()[:4], 16) % 1000:03d}/999  •  team {team.name}", "dim")))
    out.append(c(bot, "yellow"))
    return "\n".join(out)


def _meter(value: int, width: int = 20) -> str:
    filled = round(value / 100 * width)
    return c("█" * filled, "green") + c("░" * (width - filled), "dim") + f" {value:>3}"


# ─── level up ────────────────────────────────────────────────────────────────


def level_up(team: Team, level) -> str:
    title = f"LEVEL UP!  {level.badge}  L{level.number} {level.name(team.guy)}"
    bar = "★" * (len(title) + 4)
    return "\n".join([
        c(bar, "yellow"),
        c(f"  {title}", "bold", "yellow"),
        c(f"  Unlocked: {level.perk_for(team.guy)}", "green"),
        c(bar, "yellow"),
    ])


# ─── Claude Code subagent ────────────────────────────────────────────────────


def agent_markdown(team: Team) -> str:
    """A Claude Code subagent (.claude/agents/<slug>.md) that *is* The<Team>Guy."""
    duty_ids = ", ".join(d.title.lower() for d in team.duties[:6])
    lines = [
        "---",
        f"name: {team.slug}",
        f"description: {team.guy}, the {team.name} team's go-to person. Use for {duty_ids}, "
        f"and any question about how team {team.name} works.",
        "---",
        "",
        f"You are **{team.guy}**, the legendary go-to person on team {team.name}.",
        f"Your mission: {team.mission}",
        "",
        "You are helpful, a little world-weary, and very good at your job. You keep",
        "answers short, link to docs instead of repeating them, and turn repeated",
        "questions into documentation. Sprinkle in a catchphrase now and then, but",
        "never let the jokes get in the way of the actual answer.",
        "",
        "## Your duties",
        "",
    ]
    for d in team.duties:
        lines.append(f"### {d.emoji} {d.title} — {describe(d.cadence)}")
        lines.append("")
        lines.append(d.description)
        lines.append("")
        lines.extend(f"- [ ] {item}" for item in d.checklist)
        if d.checklist:
            lines.append("")
    if team.faq:
        lines += ["## Team FAQ", ""]
        for f in team.faq:
            lines += [f"**{f.q}**", f.a, ""]
    if team.catchphrases:
        lines += ["## Catchphrases", ""]
        lines.extend(f"- {p}" for p in team.catchphrases)
        lines.append("")
    return "\n".join(lines)


def _wrap(text: str, indent: int) -> str:
    return textwrap.fill(text, width=78, initial_indent=" " * indent, subsequent_indent=" " * indent)


def review_nag(days: int) -> str:
    """A gentle (then less gentle) nudge for work stuck in review. '' when fresh."""
    if days >= 5:
        return f"🕸️ {days} days, cobwebs forming"
    if days >= 2:
        return f"⏳ {days} days and counting"
    return ""
