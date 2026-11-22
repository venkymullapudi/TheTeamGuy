"""The guy's brain. Two flavors:

* ClaudeBrain  — real reasoning via the Claude API (Messages API, manual tool loop).
* OfflineBrain — a scripted, deterministic stand-in. No API key, no cost; great
  for demos and tests.

Both drive the same `Tool` objects, so the rest of the code never cares which
brain is in charge.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .config import DEFAULT_MODEL, Team

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class BrainError(RuntimeError):
    """The brain couldn't think (no credentials, network, refusal…)."""


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], str]

    def api_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "strict": True,
        }


@dataclass
class Step:
    tool: str
    input: Dict[str, Any]
    output: str
    is_error: bool = False


@dataclass
class RunResult:
    text: str
    steps: List[Step] = field(default_factory=list)
    stopped: str = "done"  # done | max_steps | refusal | budget


Plan = Callable[[], List[Dict[str, Any]]]


def validate_input(tool: Tool, data: Any) -> None:
    """Minimal schema check: object, required keys, enums, basic types."""
    if not isinstance(data, dict):
        raise ValueError("tool input must be an object")
    props = tool.input_schema.get("properties", {})
    for key in tool.input_schema.get("required", []):
        if key not in data:
            raise ValueError(f"missing required field {key!r}")
    for key, value in data.items():
        spec = props.get(key)
        if spec is None:
            raise ValueError(f"unexpected field {key!r}")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"{key} must be one of {spec['enum']}")
        expected = {"string": str, "integer": int}.get(spec.get("type", ""))
        if expected and not isinstance(value, expected):
            raise ValueError(f"{key} must be a {spec['type']}")


def call_tool(tool: Optional[Tool], data: Any) -> Step:
    if tool is None:
        return Step("?", data if isinstance(data, dict) else {}, "Unknown tool.", True)
    try:
        validate_input(tool, data)
        return Step(tool.name, data, tool.handler(data))
    except Exception as exc:  # tool failures go back to the model, not up the stack
        return Step(tool.name, data if isinstance(data, dict) else {}, f"{type(exc).__name__}: {exc}", True)


class OfflineBrain:
    """Follows a plan written by the caller. Deterministic and free."""

    name = "offline"

    def __init__(self) -> None:
        self.usage: Dict[str, int] = {"input": 0, "output": 0}  # free, always

    def run(self, system: str, prompt: str, tools: List[Tool], max_steps: int, plan: Optional[Plan] = None,
            budget: Optional[int] = None) -> RunResult:
        by_name = {t.name: t for t in tools}  # budget: nothing to spend, the offline brain is free
        calls = plan() if plan else []
        steps = [call_tool(by_name.get(c["tool"]), c["input"]) for c in calls[:max_steps]]
        stopped = "done" if len(calls) <= max_steps else "max_steps"
        return RunResult("(offline brain) Did my best with the playbook.", steps, stopped)

    def complete(self, system: str, prompt: str, model: Optional[str] = None, fallback: str = "") -> str:
        return fallback or f"(offline) Noted: {prompt.strip().splitlines()[0][:120]}"


class ClaudeBrain:
    """Real reasoning on the Claude API with a hand-rolled agent loop.

    A manual loop (instead of the SDK tool runner) lets us cap turns per career
    level, narrate every hand-off live, and share tools with the offline brain.
    """

    name = "claude"

    def __init__(self, model: str = DEFAULT_MODEL, client: Any = None):
        self.model = model
        if client is None:
            try:
                import anthropic
            except ImportError:
                raise BrainError(
                    "The Claude brain needs the SDK: pip install 'teamguy[claude]' (Python 3.10+). "
                    "Or use --brain offline."
                ) from None
            client = anthropic.Anthropic()
        self.client = client
        self.usage: Dict[str, int] = {"input": 0, "output": 0}

    def _count(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.usage["input"] += int(getattr(usage, "input_tokens", 0) or 0)
        self.usage["output"] += int(getattr(usage, "output_tokens", 0) or 0)

    def _create(self, model: Optional[str] = None, **kwargs: Any) -> Any:
        try:
            import anthropic
        except ImportError:  # fake clients in tests
            anthropic = None  # type: ignore[assignment]
        try:
            response = self.client.beta.messages.create(
                model=model or self.model,
                max_tokens=16000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                **kwargs,
            )
            self._count(response)
            return response
        except Exception as exc:
            if anthropic is None or not isinstance(exc, anthropic.AnthropicError):
                raise
            if isinstance(exc, (anthropic.AuthenticationError, anthropic.RateLimitError)) and _oauth_token_as_api_key():
                raise BrainError(
                    "ANTHROPIC_API_KEY holds an OAuth token (sk-ant-oat…, e.g. from `claude setup-token`), "
                    "which is for Claude Code, not direct API calls. Create an API key (sk-ant-api…) at "
                    "console.anthropic.com, or use --brain offline."
                ) from None
            if isinstance(exc, anthropic.AuthenticationError):
                raise BrainError("No Claude credentials. Run `ant auth login` or set ANTHROPIC_API_KEY, or use --brain offline.") from None
            if isinstance(exc, anthropic.RateLimitError):
                raise BrainError(f"Rate limited by the Claude API ({exc.message}). Coffee break, then retry.") from None
            if isinstance(exc, anthropic.APIStatusError):
                raise BrainError(f"Claude API error {exc.status_code}: {exc.message}") from None
            if isinstance(exc, anthropic.APIConnectionError):
                raise BrainError("Couldn't reach the Claude API. Check the network (or the VPN, it's always the VPN).") from None
            raise BrainError(str(exc)) from None

    @staticmethod
    def _text(response: Any) -> str:
        return "\n".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()

    def spent(self) -> int:
        return self.usage["input"] + self.usage["output"]

    def run(self, system: str, prompt: str, tools: List[Tool], max_steps: int, plan: Optional[Plan] = None,
            budget: Optional[int] = None) -> RunResult:
        """`budget` caps the tokens this run may spend (its own turns plus LLM crew
        calls made from its tools). Checked before every turn after the first."""
        by_name = {t.name: t for t in tools}
        api_tools = [t.api_definition() for t in tools]
        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
        steps: List[Step] = []
        start = self.spent()
        for turn in range(max_steps):
            used = self.spent() - start
            if budget and turn and used >= budget:
                return RunResult(
                    f"🪙 Out of token budget ({used:,} of {budget:,}). Parking this before the bill gets spicy.",
                    steps, "budget")
            response = self._create(system=system, messages=messages, tools=api_tools)
            if response.stop_reason == "refusal":
                return RunResult(self._text(response) or "I can't help with that one.", steps, "refusal")
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                return RunResult(self._text(response), steps, "done")
            results = []
            for block in response.content:
                if getattr(block, "type", "") != "tool_use":
                    continue
                step = call_tool(by_name.get(block.name), block.input)
                steps.append(step)
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": step.output, "is_error": step.is_error}
                )
            messages.append({"role": "user", "content": results})
        return RunResult("I ran out of steps for this one. Seniority will fix that.", steps, "max_steps")

    def complete(self, system: str, prompt: str, model: Optional[str] = None, fallback: str = "") -> str:
        response = self._create(model=model, system=system, messages=[{"role": "user", "content": prompt}])
        if response.stop_reason == "refusal":
            return fallback or "I'll pass on that one."
        return self._text(response) or fallback


def _oauth_token_as_api_key() -> bool:
    return os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-oat")


def make_brain(team: Team, override: Optional[str] = None):
    provider = override or os.environ.get("TEAMGUY_BRAIN") or team.brain_provider
    if provider == "offline":
        return OfflineBrain()
    if provider == "claude":
        return ClaudeBrain(team.model)
    try:  # auto: Claude if the SDK is installed, otherwise offline
        return ClaudeBrain(team.model)
    except BrainError:
        return OfflineBrain()
