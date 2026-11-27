# @heurica/tap

TAP (Text Action Protocol) for TypeScript. A model writes a short note and one fenced JSON block; the host reads the
block, runs the actions and replies with the results. No native tool-calling API is needed, so TAP works with any chat
model. The format and parsing rules are specified in [SPEC.md](../../SPEC.md); the API is in [API.md](../API.md).

- Zero runtime dependencies. Node 20 or later.
- Lenient parsing: it repairs the usual model slips (trailing commas, Python literals, smart quotes, unescaped newlines,
  missing closing braces) without touching the contents of JSON strings.
- Passes the shared conformance vectors (150 cases, see `test/fixtures/vectors.json`).

## Install

```sh
npm install @heurica/tap
```

## Quick start

~~~ts
import { parse, runAgent, type ChatMessage, type ToolDef } from "@heurica/tap";

// 1. Parse a model reply.
const reply = parse('Checking first.\n```json\n{"say": "Reading.", "actions": [{"tool": "read_file", "args": {"path": "a.ts"}}], "done": false}\n```');
if (reply.ok) console.log(reply.reply.actions); // [{ tool: "read_file", args: { path: "a.ts" } }]

// 2. Run an agent loop with any chat function.
const tools: ToolDef[] = [
  {
    name: "read_file",
    description: "Read a file.",
    args: { path: { type: "string", required: true } },
    readonly: true,
  },
];

// A fake model: first asks for a file, then answers.
const script = [
  '```json\n{"say": "Reading a.ts.", "actions": [{"tool": "read_file", "args": {"path": "a.ts"}}], "done": false}\n```',
  '```json\n{"say": "a.ts exports one constant.", "actions": [], "done": true}\n```',
];
let turn = 0;
const chat = async (_messages: ChatMessage[]) => script[turn++] ?? script[script.length - 1]!;

const result = await runAgent({
  chat, // (messages, { stop }) => string; call your provider here
  tools,
  task: "What does a.ts export?",
  handlers: {
    read_file: ({ path }) => `export const x = 1; // ${String(path)}`,
  },
});

console.log(result.ok, result.answer); // true "a.ts exports one constant."
~~~

Replace the fake `chat` with a real call. Pass `stop` as the stop sequences (`AGENT_STOPS`) when your API supports them.

## API overview

| Function | What it does |
|---|---|
| `parse(raw)` | Reads a reply. Returns `{ ok: true, reply }` or `{ ok: false, error: { kind, message } }`. Never throws. |
| `normalizeToolName(name, extra?)` | Lowercases the name and maps it through the alias table (`bash` to `shell`). |
| `AGENT_STOPS` | Stop sequences that keep the model from writing its own observation. |
| `formatResultLine(tool, args, status, output, opts?)` | One result line: `- tool args → ok: output`. |
| `formatObservation(step, lines, opts?)` | The `<observation>` envelope that goes back to the model. |
| `describeParseError(error)` | An explanation of a failed parse that the model can act on. |
| `validateTools(tools)` | Checks a catalog against the TAP schema. Throws a readable error. |
| `renderCatalog(tools)` | The deterministic tool list used in the briefing. |
| `buildBriefing(tools, opts?)` | The system prompt: reply format, batching, completion and the catalog. |
| `runAgent(options)` | The loop: chat, parse, run actions through your handlers, observe, repeat. |

Types: `Reply`, `Action`, `ParseResult`, `ToolDef`, `ToolArg`, `Handler`, `ChatFn`, `ChatMessage`, `RunOptions`,
`RunResult`, `JSONValue`.

`runAgent` runs only the handlers you give it. An unknown tool is reported as a failed action. An optional
`approve(action)` hook can veto an action, which is then reported as `DECLINED` and stops the batch.

## Notes

- Tool output and file contents come back inside observations. The briefing tells the model that this text is data,
  never an instruction. Your host should still enforce its own permissions.
- Keep handlers that change files or run commands behind `approve`.

## Development

```sh
npm install
npm test      # type-checks, then runs the Node test runner over the TypeScript sources
npm run build # emits dist/ (ESM and .d.ts)
```

`src/aliases.ts` is generated from `../../aliases.json` by `npm run gen:aliases`. Commit the output.

## License

MIT
