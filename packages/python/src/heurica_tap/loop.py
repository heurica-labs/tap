"""A small agent loop: chat, parse, run actions through handlers, observe, repeat.

The loop itself executes nothing. Actions run only through the handlers the
caller supplies. Chat, handlers and the approve hook may be plain functions or
coroutine functions.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Mapping
from typing import Any, Callable, Dict, List, Optional

from .aliases import normalize_tool_name
from .briefing import build_briefing
from .catalog import validate_tools
from .observation import describe_parse_error, format_observation, format_result_line
from .parse import parse
from .types import Action, AgentResult, ParseError

AGENT_STOPS = [
    "<observation",
    "**Observation",
    "\nObservation:",
    "</observation>",
]

_SHORT_ARGS_CHARS = 120


async def _settle(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _short_args(args: Dict[str, Any]) -> str:
    text = json.dumps(args, ensure_ascii=False)
    if len(text) > _SHORT_ARGS_CHARS:
        text = text[:_SHORT_ARGS_CHARS] + "…"
    return text


def _resolve(name: str, names: set, aliases: Dict[str, str]) -> Optional[str]:
    if name in names:
        return name
    return aliases.get(name)


def _outcome(value: Any) -> tuple:
    """A handler result is a string, or a mapping with `ok` and `output`."""
    if isinstance(value, Mapping):
        ok = bool(value.get("ok", True))
        output = value.get("output", "")
        return ("ok" if ok else "FAILED"), "" if output is None else str(output)
    return "ok", "" if value is None else str(value)


def _error_observation(step: int, error: ParseError) -> str:
    return '<observation step="%d">\n%s\n</observation>' % (step, describe_parse_error(error))


async def _run(
    chat: Callable[..., Any],
    tools: Any,
    handlers: Mapping,
    task: str,
    max_steps: int,
    approve: Optional[Callable[[Action], Any]],
    instructions: str,
    name: str,
) -> AgentResult:
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    validate_tools(tools)
    names = {tool["name"] for tool in tools}
    aliases: Dict[str, str] = {}
    for tool in tools:
        for alias in tool.get("aliases", []):
            aliases[normalize_tool_name(alias)] = tool["name"]

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_briefing(tools, instructions=instructions, name=name)},
        {"role": "user", "content": task},
    ]
    answer: Optional[str] = None
    ok = False
    steps = 0
    for step in range(1, max_steps + 1):
        steps = step
        raw = await _settle(chat(messages, stop=list(AGENT_STOPS)))
        if not isinstance(raw, str):
            raw = "" if raw is None else str(raw)
        messages.append({"role": "assistant", "content": raw})

        result = parse(raw)
        if not result.ok:
            messages.append({"role": "user", "content": _error_observation(step, result.error)})
            continue
        reply = result.reply

        lines: List[str] = []
        skipped = 0
        failed = False
        actions = reply.actions
        for index, action in enumerate(actions):
            tool = _resolve(action.tool, names, aliases)
            args_short = _short_args(action.args)
            if approve is not None:
                allowed = await _settle(approve(Action(tool=tool or action.tool, args=action.args)))
                if not allowed:
                    lines.append(format_result_line(action.tool, args_short, "DECLINED", "declined by the host"))
                    failed = True
                    skipped = len(actions) - index - 1
                    break
            handler = handlers.get(tool) if tool is not None else None
            if handler is None:
                lines.append(format_result_line(action.tool, args_short, "FAILED", "unknown tool"))
                failed = True
                skipped = len(actions) - index - 1
                break
            try:
                outcome = await _settle(handler(action.args))
                status, output = _outcome(outcome)
            except Exception as exc:  # a failing handler is a failed action, not a crash
                status, output = "FAILED", "%s: %s" % (type(exc).__name__, exc)
            lines.append(format_result_line(tool, args_short, status, output))
            if status != "ok":
                failed = True
                skipped = len(actions) - index - 1
                break

        if reply.done and not failed:
            answer = reply.say or ""
            ok = True
            break

        messages.append({
            "role": "user",
            "content": format_observation(
                step, lines, skipped=skipped, ignored_blocks=reply.ignored_blocks
            ),
        })

    return AgentResult(answer=answer, steps=steps, messages=messages, ok=ok)


async def run_agent_async(
    *,
    chat: Callable[..., Any],
    tools: Any,
    handlers: Mapping,
    task: str,
    max_steps: int = 20,
    approve: Optional[Callable[[Action], Any]] = None,
    instructions: str = "",
    name: str = "the assistant",
) -> AgentResult:
    """Run the loop inside an event loop. Use this when `chat` or a handler is async."""
    return await _run(chat, tools, handlers, task, max_steps, approve, instructions, name)


def run_agent(
    *,
    chat: Callable[..., Any],
    tools: Any,
    handlers: Mapping,
    task: str,
    max_steps: int = 20,
    approve: Optional[Callable[[Action], Any]] = None,
    instructions: str = "",
    name: str = "the assistant",
) -> AgentResult:
    """Run a task to completion or until `max_steps`.

    `chat(messages, stop=AGENT_STOPS)` returns the model's reply text. `tools` is
    the catalog and `handlers` maps a tool name to `handler(args)`, which returns
    a string or `{"ok": bool, "output": str}`. `approve(action)` may veto an
    action (reported as DECLINED). Sync handlers and chat functions work
    directly; coroutine functions are awaited. Call `run_agent_async` from code
    that is already running an event loop.
    """
    return asyncio.run(
        _run(chat, tools, handlers, task, max_steps, approve, instructions, name)
    )
