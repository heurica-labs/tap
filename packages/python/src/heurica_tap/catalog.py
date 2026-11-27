"""Tool catalog: validation and the compact text rendering (SPEC 8)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, List

ARG_TYPES = ("string", "integer", "number", "boolean", "array", "object")
_TOOL_KEYS = frozenset(("name", "description", "args", "readonly", "aliases"))
_ARG_KEYS = frozenset(("type", "required", "description"))
_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")


def validate_tools(tools: Any) -> None:
    """Check a catalog against schema/tools.schema.json. Raises ValueError with a
    readable message on the first problem; returns None when the catalog is valid."""
    if not isinstance(tools, (list, tuple)):
        raise ValueError("the tool catalog must be a list of tool objects")
    seen = set()
    for index, tool in enumerate(tools):
        where = "tools[%d]" % index
        if not isinstance(tool, Mapping):
            raise ValueError("%s must be an object" % where)
        unknown = set(tool) - _TOOL_KEYS
        if unknown:
            raise ValueError("%s has unknown keys: %s" % (where, ", ".join(sorted(unknown))))
        name = tool.get("name")
        if not isinstance(name, str) or not _NAME.match(name):
            raise ValueError("%s.name must match ^[a-z][a-z0-9_]*$, got %r" % (where, name))
        if name in seen:
            raise ValueError("%s.name %r is listed twice" % (where, name))
        seen.add(name)
        if not isinstance(tool.get("description"), str):
            raise ValueError("%s.description must be a string" % where)
        args = tool.get("args", {})
        if not isinstance(args, Mapping):
            raise ValueError("%s.args must be an object" % where)
        for arg_name, spec in args.items():
            arg_where = "%s.args.%s" % (where, arg_name)
            if not isinstance(spec, Mapping):
                raise ValueError("%s must be an object" % arg_where)
            unknown = set(spec) - _ARG_KEYS
            if unknown:
                raise ValueError("%s has unknown keys: %s" % (arg_where, ", ".join(sorted(unknown))))
            arg_type = spec.get("type", "string")
            if arg_type not in ARG_TYPES:
                raise ValueError("%s.type must be one of %s" % (arg_where, ", ".join(ARG_TYPES)))
            if not isinstance(spec.get("required", False), bool):
                raise ValueError("%s.required must be a boolean" % arg_where)
            if "description" in spec and not isinstance(spec["description"], str):
                raise ValueError("%s.description must be a string" % arg_where)
        if not isinstance(tool.get("readonly", False), bool):
            raise ValueError("%s.readonly must be a boolean" % where)
        aliases = tool.get("aliases", [])
        if not isinstance(aliases, (list, tuple)) or not all(isinstance(a, str) for a in aliases):
            raise ValueError("%s.aliases must be a list of strings" % where)


def render_catalog(tools: Any) -> str:
    """Render the catalog as compact, deterministic text: one tool per line,
    `name(required, optional?) - description`, with `~` before read-only tools.
    Argument and tool order are the order given. Descriptions are kept on one line."""
    validate_tools(tools)
    lines: List[str] = []
    for tool in tools:
        parts = []
        for arg_name, spec in tool.get("args", {}).items():
            parts.append(arg_name if spec.get("required", False) else arg_name + "?")
        signature = "%s(%s)" % (tool["name"], ", ".join(parts))
        if tool.get("readonly", False):
            signature = "~" + signature
        description = " ".join(tool["description"].split())
        lines.append("%s - %s" % (signature, description))
    return "\n".join(lines)
