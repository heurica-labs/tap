"""heurica_tap: the Text Action Protocol (TAP) for Python.

Public API (see packages/API.md):

    parse(raw) -> ParseResult
    normalize_tool_name(name, extra_aliases=None) -> str
    AGENT_STOPS
    format_result_line, format_observation, describe_parse_error
    validate_tools, render_catalog, build_briefing
    run_agent, run_agent_async
"""

from .aliases import normalize_tool_name
from .briefing import build_briefing
from .catalog import render_catalog, validate_tools
from .loop import AGENT_STOPS, run_agent, run_agent_async
from .observation import describe_parse_error, format_observation, format_result_line
from .parse import parse
from .types import Action, AgentResult, ParseError, ParseResult, Reply

__version__ = "0.1.0"

__all__ = [
    "Action",
    "AgentResult",
    "AGENT_STOPS",
    "ParseError",
    "ParseResult",
    "Reply",
    "build_briefing",
    "describe_parse_error",
    "format_observation",
    "format_result_line",
    "normalize_tool_name",
    "parse",
    "render_catalog",
    "run_agent",
    "run_agent_async",
    "validate_tools",
    "__version__",
]
