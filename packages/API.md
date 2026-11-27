# Library API (shared by every TAP library)

Every library in `packages/` exposes the same small surface, with names adapted to the language (camelCase in TypeScript, snake_case in Python). Libraries have **no runtime dependencies**. Each one runs the shared vectors in `../conformance/vectors.json` as part of its tests.

## Parsing

`parse(raw) -> ParseResult`

- Input: the raw text of a model reply.
- Output: `{ ok: true, reply }` or `{ ok: false, error: { kind, message } }` (SPEC 6.8).
- `reply` has: `thought`, `say` (string or null), `actions` (list of `{tool, args}`), `done`, `explicitDone`, `plan`, `milestone` (integer or null), `ignoredBlocks`.
- `error.kind` is `no_json` or `invalid_json`. `message` carries the diagnosis for `invalid_json` (SPEC 7) and may be empty for `no_json`.
- `parse` never throws on bad model text. It must behave exactly like the reference parser on every vector.

The Python reply object also offers `as_dict()` returning the camelCase form used in the vectors.

## Tool names and aliases

`normalizeToolName(name, extraAliases?) -> string` lowercases, turns `-` and space into `_`, then applies the alias table (the table ships inside each library, generated from `../aliases.json`).

## Stop sequences

`AGENT_STOPS`: the list from SPEC 5.2.

## Observations

- `formatResultLine(tool, argsShort, status, output)` returns `- <tool> <argsShort> → <status>: <output>`, where `status` is `ok`, `FAILED` or `DECLINED`. Collapse the output to a single line only if the caller asks (`oneLine: true`); by default keep newlines. Truncate output beyond `maxChars` (default 4000) with the note `… (N more characters)`.
- `formatObservation(step, resultLines, { skipped = 0, ignoredBlocks = 0 }) -> string` returns the envelope from SPEC 5.1: `<observation step="N">`, the line `results of your actions:`, the result lines, a skipped note `(the remaining N action(s) in this batch were skipped)` when `skipped > 0`, a note that only the first block ran when `ignoredBlocks > 0`, then `</observation>`.
- `describeParseError(error) -> string` returns an observation-ready explanation for a failed parse (SPEC 7): for `no_json` it says no JSON block was found and repeats the reply format, for `invalid_json` it includes the message. It must not run or suggest running anything.

## Tool catalog

- `validateTools(tools)` checks a catalog against `../schema/tools.schema.json` rules (names, argument types) and throws a readable error when invalid.
- `renderCatalog(tools) -> string` renders the compact deterministic text of SPEC 8: one tool per line, `name(required, optional?) - description`, a leading `~` for `readonly` tools, arguments in the order given, tools in the order given. No timestamps or randomness.

## Briefing

`buildBriefing(tools, { instructions = "", name = "the assistant" }) -> string` returns a ready-to-use system prompt: the role line, HOW TO REPLY (one short sentence of reasoning, exactly one fenced `json` block with `say`, `actions`, `done`), the batching rule, the completion rule (`done: true`, no actions, the answer in `say`), the rule that text inside an observation is data and never instructions, and the rendered catalog. The text is deterministic.

## Agent loop

`runAgent({ chat, tools, handlers, task, maxSteps = 20, ... })`

A small, dependency-free loop that shows how the pieces fit:

- `chat(messages, { stop }) -> string` is supplied by the caller (any provider). `messages` is a list of `{role, content}`.
- `tools` is the catalog, `handlers` maps a tool name to a function `(args) -> string | { ok, output }` (sync or async).
- Each step: call `chat`, `parse`, on failure send `describeParseError` as an observation and continue; otherwise run the actions in order, stopping at the first failure; send the observation; stop when `done` is true or after `maxSteps`.
- Returns `{ answer, steps, messages, ok }`.
- Actions run only through `handlers`; the loop never executes anything itself. An unknown tool is a failed action (`FAILED: unknown tool`), not an exception.
- A host-provided `approve(action) -> boolean | Promise<boolean>` hook may veto an action; a vetoed action is reported as `DECLINED` and stops the batch.

## Tests

Each library ships tests that cover: all conformance vectors; `formatObservation` and `formatResultLine`; `renderCatalog` determinism; `buildBriefing`; `runAgent` against a scripted fake model (a normal task, a malformed reply that is recovered after one retry, a failing action that stops the batch, an unknown tool, a vetoed action and the step limit).
