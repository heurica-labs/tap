"""Observations: the host's report of what ran (SPEC section 5.1 and 7)."""

from __future__ import annotations

from typing import Any, Iterable

STATUSES = ("ok", "FAILED", "DECLINED")


def format_result_line(
    tool: str,
    args_short: str,
    status: str,
    output: Any,
    *,
    one_line: bool = False,
    max_chars: int = 4000,
) -> str:
    """One line per action: `- <tool> <args> → <status>: <output>`.

    Output is kept as it is (newlines included) unless `one_line` is set. Output
    longer than `max_chars` is cut and followed by `… (N more characters)`.
    """
    if status not in STATUSES:
        raise ValueError("status must be one of %s, got %r" % (", ".join(STATUSES), status))
    text = "" if output is None else str(output)
    if one_line:
        text = " ".join(text.split())
    if max_chars is not None and len(text) > max_chars:
        text = "%s… (%d more characters)" % (text[:max_chars], len(text) - max_chars)
    head = "- %s" % tool
    if args_short:
        head += " %s" % args_short
    return "%s → %s: %s" % (head, status, text)


def format_observation(
    step: int,
    result_lines: Iterable[str],
    *,
    skipped: int = 0,
    ignored_blocks: int = 0,
) -> str:
    """The observation envelope from SPEC 5.1.

    `skipped` is the number of actions in the batch that did not run after a
    failure. `ignored_blocks` is the number of further JSON blocks in the reply.
    """
    lines = ['<observation step="%d">' % step, "results of your actions:"]
    result_lines = list(result_lines)
    if result_lines:
        lines.extend(result_lines)
    else:
        lines.append("(no actions were run)")
    if skipped > 0:
        lines.append("(the remaining %d action(s) in this batch were skipped)" % skipped)
    if ignored_blocks > 0:
        lines.append(
            "(your reply had %d more JSON block(s); only the first one ran)" % ignored_blocks
        )
    lines.append("</observation>")
    return "\n".join(lines)


def describe_parse_error(error: Any) -> str:
    """An observation-ready explanation of a failed parse (SPEC 7).

    Accepts a ParseError (or a ParseResult, whose error is used). The text
    never asks the model to run anything; it only asks for a corrected reply.
    """
    if hasattr(error, "error") and not hasattr(error, "kind"):
        error = error.error
    kind = getattr(error, "kind", "")
    message = getattr(error, "message", "") or ""
    if kind == "no_json":
        return (
            "Your reply did not contain a JSON block, so nothing was run. Reply with one "
            "short sentence, then exactly one fenced ```json block shaped like "
            '{"say": "...", "actions": [{"tool": "<tool name>", "args": {...}}], "done": false}. '
            "Send the reply again."
        )
    if kind == "invalid_json":
        detail = (" " + message) if message else ""
        return (
            "Your JSON block was not valid JSON, so nothing was run.%s Fix the JSON and send "
            "the reply again, in the same shape with say, actions and done." % detail
        )
    raise ValueError("unknown parse error kind: %r" % (kind,))
