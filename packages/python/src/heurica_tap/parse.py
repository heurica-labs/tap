"""Lenient TAP reply parser (SPEC section 6).

This is a port of the reference parser (tools/oracle/ActionParser.swift and
JSON.swift). Behavior follows the reference, including its string-aware repairs,
its fence search order and its fallbacks. Where the reference differs from the
spec, the conformance vectors mark the case with divergesFromAnvil and this
module follows the spec.

Python-specific compatibility (the reference uses Foundation's JSONSerialization):

* NaN and Infinity literals are rejected.
* Duplicate object keys keep the first value.
* Lone surrogate escapes are rejected.
* Integers above 2**53 become floats, and whole numbers become ints.
* Raw control characters inside strings are rejected by the strict read, so
  the repair path runs (json.loads(strict=True)).
* Swift iterates by Character (grapheme cluster), Python by code point. The
  only place this matters for the repairs is CRLF, which is escaped here as the
  spec requires; grapheme counting for the 40-character rule is approximated.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, List, Optional, Tuple

from .aliases import normalize_tool_name
from .types import Action, ParseError, ParseResult, Reply

NAME_KEYS = ("tool", "action", "name", "type", "function", "cmd", "command_name")
ARG_KEYS = ("args", "arguments", "params", "parameters", "input", "inputs")
META_KEYS = frozenset(
    ("say", "thought", "thoughts", "reason", "reasoning", "risk", "why",
     "done", "status", "plan", "milestone")
)
COMPLETION_NAMES = frozenset(
    ("done", "finish", "final_answer", "answer", "complete", "attempt_completion")
)
REPLY_KEYS = frozenset(
    ("say", "actions", "done", "plan", "action", "tool", "steps", "tool_calls",
     "milestone", "message", "answer")
)
SAY_KEYS = ("say", "message", "answer", "reply", "response")
RESULT_TEXT_KEYS = ("message", "answer", "text", "say", "result")
POINTERS = (
    "answered below", "see below", "below", "as follows", "here you go",
    "here it is", "response below", "answer below", "details below",
    "here's the answer", "here is the answer",
)

_FENCE = re.compile(r"```(?:json|JSON|javascript)?[ \t]*\n?([\s\S]*?)```")
_SPACES = " \t               　"
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_HEX = re.compile(r"[+-]?0[xX][0-9a-fA-F]+")
_SURROGATE = re.compile("[\ud800-\udfff]")
_EXACT = 2 ** 53
_FAIL = object()


class _NoJSON(Exception):
    pass


class _Invalid(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------- JSON reading

def _reject_constant(name: str) -> Any:
    raise ValueError("%s is not valid JSON" % name)


def _parse_int(text: str) -> Any:
    value = int(text)
    if -_EXACT <= value <= _EXACT:
        return value
    return float(text)


def _parse_float(text: str) -> Any:
    value = float(text)
    if value.is_integer() and -_EXACT <= value <= _EXACT:
        return int(value)
    return value


def _first_wins(pairs: List[Tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key not in result:
            result[key] = value
    return result


def _has_lone_surrogate(value: Any) -> bool:
    if isinstance(value, str):
        return _SURROGATE.search(value) is not None
    if isinstance(value, list):
        return any(_has_lone_surrogate(item) for item in value)
    if isinstance(value, dict):
        return any(_has_lone_surrogate(k) or _has_lone_surrogate(v) for k, v in value.items())
    return False


def _strict_loads(text: str) -> Any:
    """Strict JSON read. Returns _FAIL when Foundation would reject the text."""
    try:
        value = json.loads(
            text,
            strict=True,
            parse_constant=_reject_constant,
            parse_int=_parse_int,
            parse_float=_parse_float,
            object_pairs_hook=_first_wins,
        )
    except (ValueError, RecursionError):
        return _FAIL
    if _has_lone_surrogate(value):
        return _FAIL
    return value


def _string(value: Any) -> Optional[str]:
    """JSON.string: strings as-is, numbers and booleans as text, otherwise nil."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        if abs(value) < 10 ** 15:
            return str(value)
        return _swift_double_text(float(value))
    if isinstance(value, float):
        if value == value and value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return _swift_double_text(value)
    return None


def _swift_double_text(value: float) -> str:
    if value != value:
        return "nan"
    if value in (float("inf"), float("-inf")):
        return "inf" if value > 0 else "-inf"
    return repr(value)


def _double(value: Any) -> Optional[float]:
    """JSON.double: numbers, numeric strings and booleans (true is 1)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip(_SPACES)
        if _DECIMAL.fullmatch(text):
            return float(text)
        if _HEX.fullmatch(text):
            return float(int(text, 16))
    return None


def _int(value: Any) -> Optional[int]:
    """JSON.int: round half away from zero."""
    number = _double(value)
    if number is None or number != number or number in (float("inf"), float("-inf")):
        return None
    rounded = int(number)
    frac = abs(number - rounded)
    if frac >= 0.5:
        rounded += 1 if number > 0 else -1
    return rounded


def _bool(value: Any) -> Optional[bool]:
    """JSON.bool: true, numbers other than zero, and the strings true, yes, 1."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1")
    return None


def _array(value: Any) -> Optional[list]:
    return value if isinstance(value, list) else None


def _object(value: Any) -> Optional[dict]:
    return value if isinstance(value, dict) else None


# ------------------------------------------------------------- JSON repairs

def _normalize_json(text: str) -> str:
    """Outside strings: drop trailing commas and // comments, Python literals become
    JSON, curly quotes delimit strings. Inside strings: raw newlines, carriage
    returns and tabs are escaped; everything else is kept."""
    out: List[str] = []
    n = len(text)
    i = 0
    in_string = escaped = smart = False
    while i < n:
        c = text[i]
        if in_string:
            if escaped:
                escaped = False
                out.append(c)
            elif c == "\\":
                escaped = True
                out.append(c)
            elif (not smart and c == '"') or (smart and c == "”"):
                in_string = False
                out.append('"')
            elif smart and c == '"':
                out.append('\\"')
            elif c == "\n":
                out.append("\\n")
            elif c == "\r":
                out.append("\\r")
            elif c == "\t":
                out.append("\\t")
            else:
                out.append(c)
            i += 1
            continue
        if c == '"':
            in_string, smart = True, False
            out.append(c)
        elif c in ("“", "”"):
            in_string, smart = True, True
            out.append('"')
        elif c == ",":
            k = i + 1
            while k < n and text[k].isspace():
                k += 1
            if k < n and text[k] in "}]":
                i += 1
                continue
            out.append(c)
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif c.isalpha() and (i == 0 or not _is_word_char(text[i - 1])):
            k = i
            while k < n and _is_word_char(text[k]):
                k += 1
            word = text[i:k]
            out.append({"True": "true", "False": "false", "None": "null"}.get(word, word))
            i = k
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _is_word_char(c: str) -> bool:
    return c.isalpha() or c.isnumeric() or c == "_"


def _balanced_prefix(text: str) -> str:
    """The first balanced {...} or [...] at the start of text (string-aware)."""
    depth = 0
    in_string = escaped = False
    out: List[str] = []
    for c in text:
        out.append(c)
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                return "".join(out)
    return text


def _repair_structure(text: str) -> str:
    """Close the structural slips models make: a "{" where a key is expected means
    the previous object was never closed, a closer of the wrong kind means one is
    missing, and open containers and strings at the end are closed."""
    out: List[str] = []
    stack: List[str] = []
    expect_key = False
    in_string = escaped = False
    for c in text:
        if in_string:
            out.append(c)
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            if stack and stack[-1] == "{" and expect_key:
                expect_key = False
            out.append(c)
        elif c == "{":
            if stack and stack[-1] == "{" and expect_key and "," in out:
                comma = len(out) - 1 - out[::-1].index(",")
                out.insert(comma, "}")
                stack.pop()
            stack.append("{")
            expect_key = True
            out.append(c)
        elif c == "[":
            stack.append("[")
            expect_key = False
            out.append(c)
        elif c == "}":
            while stack and stack[-1] == "[":
                out.append("]")
                stack.pop()
            if stack:
                stack.pop()
            expect_key = False
            out.append(c)
        elif c == "]":
            while stack and stack[-1] == "{":
                out.append("}")
                stack.pop()
            if stack:
                stack.pop()
            expect_key = False
            out.append(c)
        elif c == ",":
            expect_key = bool(stack) and stack[-1] == "{"
            out.append(c)
        elif c == ":":
            expect_key = False
            out.append(c)
        else:
            out.append(c)
    if in_string:
        out.append('"')
    for opener in reversed(stack):
        out.append("}" if opener == "{" else "]")
    return "".join(out)


def _parse_lenient(text: str, repair: bool = True) -> Any:
    """Strict read, then the repairs in order. Returns _FAIL if nothing parses."""
    value = _strict_loads(text)
    if value is not _FAIL:
        return value
    normalized = _normalize_json(text)
    value = _strict_loads(normalized)
    if value is not _FAIL:
        return value
    value = _strict_loads(_balanced_prefix(normalized))
    if value is not _FAIL:
        return value
    if repair:
        # The reference reads the repaired text with its tolerant parser, which
        # accepts a trailing comma left in front of a closer added by the repair.
        return _strict_loads(_normalize_json(_repair_structure(normalized)))
    return _FAIL


def _diagnose(text: str) -> str:
    """Where the JSON broke, for the retry message (SPEC 7)."""
    normalized = _normalize_json(text)
    try:
        json.loads(normalized)
    except json.JSONDecodeError as exc:
        pos = exc.pos
        lo, hi = max(0, pos - 80), min(len(normalized), pos + 40)
        return "%s around character %d. Near: …%s⟦HERE⟧%s…" % (
            exc.msg, pos, normalized[lo:pos], normalized[pos:hi])
    except ValueError:
        return ""
    return ""


# ------------------------------------------------------------ text helpers

def _grapheme_count(text: str) -> int:
    """Approximate count of grapheme clusters (Swift Character count)."""
    count = 0
    prev = ""
    regional_in_cluster = 0
    for ch in text:
        cp = ord(ch)
        joins = False
        if count == 0:
            joins = False
        elif prev == "\r" and ch == "\n":
            joins = True
        elif prev == "‍":
            joins = True
        elif ch == "‍":
            joins = True
        elif unicodedata.category(ch).startswith("M"):
            joins = True
        elif 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF or 0x1F3FB <= cp <= 0x1F3FF:
            joins = True
        elif 0x1F1E6 <= cp <= 0x1F1FF and regional_in_cluster == 1:
            joins = True
        if not joins:
            count += 1
            regional_in_cluster = 0
        if 0x1F1E6 <= cp <= 0x1F1FF:
            regional_in_cluster += 1
        prev = ch
    return count


def _is_pointer(say: Optional[str]) -> bool:
    """A say that is empty or only points elsewhere (SPEC 6.6)."""
    text = (say or "").strip().lower()
    if text == "":
        return True
    if _grapheme_count(text) > 40:
        return False
    for pointer in POINTERS:
        if text.startswith(pointer) or text in (pointer, pointer + ".", pointer + ":"):
            return True
    return False


# ------------------------------------------------------- reply structure

def _action_from(obj: Any) -> Optional[Action]:
    """An action object, or None when it has no tool name (SPEC 6.4)."""
    if not isinstance(obj, dict):
        return None
    name_key = next((k for k in NAME_KEYS if _string(obj.get(k)) is not None), None)
    if name_key is None:
        return None
    name = _string(obj[name_key])
    arg_key = next((k for k in ARG_KEYS if k in obj), None)
    if arg_key is not None:
        args: Any = obj[arg_key]
        if isinstance(args, str):
            inner = _parse_lenient(args)
            if inner is not _FAIL and isinstance(inner, dict):
                args = inner
    else:
        args = {k: v for k, v in obj.items() if k != name_key and k not in META_KEYS}
    if not isinstance(args, dict):
        args = {"value": args}
    return Action(tool=normalize_tool_name(name), args=args)


def _is_reply(value: Any) -> bool:
    """Shaped like a reply (SPEC 6.2)."""
    if isinstance(value, list):
        return any(_action_from(item) is not None for item in value)
    if isinstance(value, dict):
        return not REPLY_KEYS.isdisjoint(value.keys())
    return False


def _actions_from_list(items: list) -> List[Action]:
    return [a for a in (_action_from(item) for item in items) if a is not None]


def _build_reply(value: Any, before: str, after: str, extra: int) -> Reply:
    reply = Reply(thought=before, ignored_blocks=extra)
    if isinstance(value, list):
        reply.actions = _actions_from_list(value)
        done_absent = True
    elif isinstance(value, dict):
        reply.explicit_done = "done" in value or "status" in value
        done_absent = "done" not in value
        reply.say = _string(next((value[k] for k in SAY_KEYS if k in value), None))

        done = _bool(value.get("done"))
        if done is None:
            status = _string(value.get("status"))
            done = status is not None and status.lower() in ("done", "complete", "finished")
        reply.done = done

        plan_source = _array(value.get("plan"))
        if plan_source is None:
            plan_source = _array(value.get("milestones")) or []
        plan = []
        for entry in plan_source:
            text = _string(entry)
            if text is None and isinstance(entry, dict):
                text = _string(entry.get("title"))
                if text is None:
                    text = _string(entry.get("step"))
            if text is not None:
                text = text.strip()
                if text:
                    plan.append(text)
        reply.plan = plan
        reply.milestone = _int(value.get("milestone"))

        first_list_key = next((k for k in ("actions", "steps", "tool_calls") if k in value), None)
        listed = _array(value[first_list_key]) if first_list_key else None
        if listed is not None:
            reply.actions = _actions_from_list(listed)
        else:
            single = _object(value.get("action"))
            if single is None:
                single = _object(value.get("tool"))
            if single is not None:
                action = _action_from(single)
                reply.actions = [action] if action is not None else []
            else:
                action = _action_from(value)
                if action is not None:
                    reply.actions = [action]
    else:
        raise _Invalid("top level must be an object")

    # A completion action is a signal, not a tool (SPEC 6.5).
    index = next((i for i, a in enumerate(reply.actions) if a.tool in COMPLETION_NAMES), None)
    if index is not None:
        completion = reply.actions[index]
        message = None
        for key in RESULT_TEXT_KEYS:
            message = _string(completion.args.get(key))
            if message is not None:
                break
        if message:
            reply.say = message
        reply.actions = reply.actions[:index]
        reply.done = True
        reply.explicit_done = True

    if not reply.actions and reply.say is not None and done_absent and not reply.plan:
        reply.done = True

    # The answer written as prose after the block (SPEC 6.7).
    if not reply.actions and after and _grapheme_count(after) > 40 and _is_pointer(reply.say):
        reply.say = after
        if done_absent:
            reply.done = True
    return reply


# ----------------------------------------------------------- extraction

def _extract(raw: str) -> Tuple[Any, str, str, int]:
    """Find the reply's JSON (SPEC 6.1). Returns (value, text before, text after,
    number of further valid blocks). Raises _NoJSON or _Invalid."""
    matches = list(_FENCE.finditer(raw))

    # Step 1: the first fence whose body is valid JSON and shaped like a reply.
    valid = []
    for match in matches:
        body = match.group(1).strip()
        if body[:1] in ("{", "["):
            value = _parse_lenient(body, repair=False)
            if value is not _FAIL and _is_reply(value):
                valid.append((match, value))
    if valid:
        match, value = valid[0]
        return value, raw[:match.start()].strip(), raw[match.end():].strip(), len(valid) - 1

    def attempt(text: str, before: str) -> Optional[Tuple[Any, str, str, int]]:
        # The first candidate found decides: if it cannot be read, the result is
        # invalid_json (as in the reference). A readable value that is not
        # shaped like a reply is skipped (SPEC 6.1, 6.2).
        value = _parse_lenient(text)
        if value is _FAIL:
            raise _Invalid(_diagnose(text))
        if not _is_reply(value):
            return None
        return value, before, "", 0

    # Step 2: a json fence whose body holds nested fences; take everything up to the last close.
    opener = raw.find("```json")
    if opener < 0:
        opener = raw.find("```JSON")
    if opener >= 0:
        body = raw[opener + len("```json"):]
        close = body.rfind("\n```")
        if close < 0:
            close = body.rfind("```")
        if close >= 0:
            body = body[:close]
        body = body.strip()
        if body[:1] in ("{", "["):
            found = attempt(body, raw[:opener].strip())
            if found is not None:
                return found

    # Step 3: a single fence whose body starts with "{".
    if len(matches) == 1:
        body = matches[0].group(1).strip()
        if body[:1] == "{":
            found = attempt(body, raw[:matches[0].start()].strip())
            if found is not None:
                return found

    # Step 4: the outermost {...} in the text.
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        found = attempt(raw[start:end + 1], raw[:start].strip())
        if found is not None:
            return found

    # Step 5: from the first "{" to the end (a reply cut off before its closing brace).
    if start >= 0:
        found = attempt(raw[start:], raw[:start].strip())
        if found is not None:
            return found

    raise _NoJSON()


# -------------------------------------------------------------- public API

def parse(raw: str) -> ParseResult:
    """Parse the raw text of a model reply. Never raises on bad model text."""
    if not isinstance(raw, str):
        raw = "" if raw is None else str(raw)
    try:
        value, before, after, extra = _extract(raw)
        reply = _build_reply(value, before, after, extra)
    except _NoJSON:
        return ParseResult(ok=False, error=ParseError(kind="no_json"))
    except _Invalid as exc:
        return ParseResult(ok=False, error=ParseError(kind="invalid_json", message=exc.message))
    return ParseResult(ok=True, reply=reply)
