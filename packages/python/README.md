# heurica-tap

Python library for TAP, the Text Action Protocol. A model uses tools by writing a
short note and one fenced JSON block. No native tool-calling API is needed, so TAP
works with any chat model. The package has no runtime dependencies (standard
library only) and needs Python 3.9 or newer.

## Install

```sh
pip install heurica-tap          # once published
pip install -e packages/python   # from a checkout
```

## Quick start

```python
from heurica_tap import parse, run_agent

TOOLS = [{
    "name": "read_file",
    "description": "Read a file.",
    "args": {"path": {"type": "string", "required": True}},
    "readonly": True,
}]

def read_file(args):
    with open(args["path"], encoding="utf-8") as fh:
        return fh.read()

def fake_chat(messages, stop=None):
    """Stands in for a real model: returns one reply, then finishes."""
    if len(messages) == 2:  # only the briefing and the task so far
        return ('Reading the file first.\n```json\n'
                '{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "notes.txt"}}], "done": false}\n```')
    return '```json\n{"say": "The notes are read.", "actions": [], "done": true}\n```'

# parse() reads one reply on its own:
result = parse(fake_chat([{}, {}]))
print(result.ok, result.reply.actions[0].tool)   # True read_file

# run_agent() drives the whole loop:
outcome = run_agent(chat=fake_chat, tools=TOOLS, handlers={"read_file": read_file},
                    task="Summarize notes.txt")
print(outcome.ok, outcome.answer)
```

`chat` receives the message list and a `stop` keyword (the list `AGENT_STOPS`). It
returns the model's reply text. Use any provider here; see
`examples/openai_compatible.py` in the repository root for an OpenAI-compatible endpoint.

## API overview

| Name | Purpose |
|---|---|
| `parse(raw)` | Read a reply. Returns `ParseResult` with `ok`, `reply` or `error`. Never raises on model text. |
| `normalize_tool_name(name, extra_aliases=None)` | Lowercase, `-` and spaces to `_`, then the alias table. |
| `AGENT_STOPS` | Stop sequences for the model (SPEC 5.2). |
| `format_result_line(tool, args, status, output)` | One action's line in an observation. |
| `format_observation(step, lines, skipped=, ignored_blocks=)` | The `<observation>` envelope. |
| `describe_parse_error(error)` | Explanation sent back when a reply cannot be used. |
| `validate_tools(tools)` | Checks a catalog against `schema/tools.schema.json`. |
| `render_catalog(tools)` | Deterministic text rendering of the catalog. |
| `build_briefing(tools, instructions=, name=)` | The system prompt: reply format, rules and catalog. |
| `run_agent(...)` / `run_agent_async(...)` | The loop. Handlers and `chat` may be sync or async. |

Results are dataclasses (`Reply`, `Action`, `ParseError`, `ParseResult`, `AgentResult`).
`ParseResult.as_dict()` and `Reply.as_dict()` give the camelCase form used by the
conformance vectors.

## Behavior notes

- The parser follows the reference (Anvil's `ActionParser.swift`) and SPEC section 6.
  The conformance vectors in `conformance/vectors.json` define the exact results.
- Python's `json` differs from Foundation in a few places; the parser reproduces the
  reference: duplicate keys keep the first value, NaN and Infinity are rejected, lone
  surrogates are rejected, and integers above 2**53 become floats.
- Run `python3 -m unittest discover -s tests` from this folder to run the suite,
  including all conformance vectors.
- The alias table is generated: `python3 scripts/gen_aliases.py` rebuilds
  `src/heurica_tap/aliases.py` from `aliases.json`.
