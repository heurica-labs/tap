"""Data types returned by the parser and the agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Action:
    """One tool call from a reply: `tool` is the normalized tool name."""

    tool: str
    args: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "args": self.args}


@dataclass
class Reply:
    """A parsed reply (SPEC 6.8)."""

    thought: str = ""
    say: Optional[str] = None
    actions: List[Action] = field(default_factory=list)
    done: bool = False
    explicit_done: bool = False
    plan: List[str] = field(default_factory=list)
    milestone: Optional[int] = None
    ignored_blocks: int = 0

    def as_dict(self) -> Dict[str, Any]:
        """The camelCase form used by conformance/vectors.json."""
        return {
            "thought": self.thought,
            "say": self.say,
            "actions": [action.as_dict() for action in self.actions],
            "done": self.done,
            "explicitDone": self.explicit_done,
            "plan": list(self.plan),
            "milestone": self.milestone,
            "ignoredBlocks": self.ignored_blocks,
        }


@dataclass
class ParseError:
    """Why a reply could not be used. `kind` is "no_json" or "invalid_json"."""

    kind: str
    message: str = ""

    def as_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"kind": self.kind}
        if self.message:
            data["message"] = self.message
        return data


@dataclass
class ParseResult:
    """Either a reply (ok is True) or an error (ok is False)."""

    ok: bool
    reply: Optional[Reply] = None
    error: Optional[ParseError] = None

    def as_dict(self) -> Dict[str, Any]:
        if self.ok:
            return {"ok": True, "reply": self.reply.as_dict()}
        return {"ok": False, "error": self.error.as_dict()}


@dataclass
class AgentResult:
    """Outcome of run_agent: the final answer (or None), the steps used and the transcript."""

    answer: Optional[str]
    steps: int
    messages: List[Dict[str, str]]
    ok: bool
