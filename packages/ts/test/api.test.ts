// API.md "Tests": observations, catalog determinism and validation, briefing rules, and runAgent scenarios.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  parse,
  normalizeToolName,
  AGENT_STOPS,
  formatResultLine,
  formatObservation,
  describeParseError,
  validateTools,
  renderCatalog,
  buildBriefing,
  runAgent,
} from "../src/index.ts";
import type { ChatMessage, ToolDef, Handler } from "../src/index.ts";

const tools: ToolDef[] = [
  {
    name: "read_file",
    description: "Read a file. Optional start and end lines (1-based).",
    args: {
      path: { type: "string", required: true, description: "File path relative to the project" },
      start: { type: "integer" },
      end: { type: "integer" },
    },
    readonly: true,
  },
  { name: "shell", description: "Run a shell command in the project folder.", args: { command: { type: "string", required: true }, timeout: { type: "integer" } } },
];

describe("observations", () => {
  test("formatResultLine has the SPEC 5.1 shape", () => {
    assert.equal(formatResultLine("read_file", "src/a.ts", "ok", "41 lines"), "- read_file src/a.ts → ok: 41 lines");
    assert.equal(formatResultLine("shell", "", "FAILED", "boom"), "- shell → FAILED: boom");
    assert.equal(formatResultLine("shell", "x", "DECLINED", "no"), "- shell x → DECLINED: no");
  });

  test("formatResultLine keeps newlines by default and collapses them with oneLine", () => {
    assert.equal(formatResultLine("shell", "x", "ok", "a\nb"), "- shell x → ok: a\nb");
    assert.equal(formatResultLine("shell", "x", "ok", "a\n b\r\nc", { oneLine: true }), "- shell x → ok: a b c");
  });

  test("formatResultLine truncates beyond maxChars with a note", () => {
    const line = formatResultLine("shell", "x", "ok", "abcdefghij", { maxChars: 4 });
    assert.equal(line, "- shell x → ok: abcd… (6 more characters)");
  });

  test("formatResultLine default maxChars is 4000", () => {
    const line = formatResultLine("t", "", "ok", "a".repeat(4005));
    assert.ok(line.endsWith("… (5 more characters)"));
  });

  test("formatObservation has the envelope, skipped and ignored notes", () => {
    const plain = formatObservation(2, ["- read_file a → ok: 1 lines"]);
    assert.equal(plain, '<observation step="2">\nresults of your actions:\n- read_file a → ok: 1 lines\n</observation>');

    const skipped = formatObservation(3, ["- shell x → FAILED: no"], { skipped: 2 });
    assert.match(skipped, /\(the remaining 2 action\(s\) in this batch were skipped\)/);
    assert.ok(skipped.startsWith('<observation step="3">'));
    assert.ok(skipped.endsWith("</observation>"));

    const ignored = formatObservation(1, [], { ignoredBlocks: 1 });
    assert.match(ignored, /only the first one was run/);
    assert.doesNotMatch(plain, /skipped|only the first/);
  });

  test("describeParseError explains no_json and invalid_json without suggesting a run", () => {
    const none = describeParseError({ kind: "no_json", message: "" });
    assert.match(none, /No JSON block/);
    assert.match(none, /```json/);
    const bad = describeParseError({ kind: "invalid_json", message: "Unexpected token } Near: x⟦HERE⟧y" });
    assert.match(bad, /not valid JSON/);
    assert.match(bad, /Unexpected token/);
    assert.match(bad, /nothing was run/);
  });

  test("normalizeToolName maps aliases and honours extra aliases", () => {
    assert.equal(normalizeToolName("bash"), "shell");
    assert.equal(normalizeToolName("  Str-Replace "), "edit_file");
    assert.equal(normalizeToolName("Read File"), "read_file");
    assert.equal(normalizeToolName("deploy_now"), "deploy_now");
    assert.equal(normalizeToolName("deploy", { deploy: "release" }), "release");
  });

  test("AGENT_STOPS is the SPEC 5.2 list", () => {
    assert.deepEqual([...AGENT_STOPS], ["<observation", "**Observation", "\nObservation:", "</observation>"]);
  });
});

describe("catalog", () => {
  test("renderCatalog matches the SPEC 8 examples", () => {
    assert.equal(
      renderCatalog(tools),
      [
        "~read_file(path, start?, end?) - Read a file. Optional start and end lines (1-based).",
        "shell(command, timeout?) - Run a shell command in the project folder.",
      ].join("\n"),
    );
  });

  test("renderCatalog is deterministic and keeps the given order", () => {
    const a = renderCatalog(tools);
    const b = renderCatalog(structuredClone(tools));
    assert.equal(a, b);
    const reversed = renderCatalog([...tools].reverse());
    assert.equal(reversed.split("\n")[0], "shell(command, timeout?) - Run a shell command in the project folder.");
  });

  test("validateTools accepts the sample catalog", () => {
    assert.doesNotThrow(() => validateTools(tools));
  });

  test("validateTools rejects bad names, duplicates, unknown keys and bad arg types", () => {
    assert.throws(() => validateTools([{ name: "Read", description: "x" }]), /name must match/);
    assert.throws(() => validateTools([{ name: "a", description: "x" }, { name: "a", description: "y" }]), /defined twice/);
    assert.throws(() => validateTools([{ name: "a", description: "x", extra: 1 } as unknown as ToolDef]), /unknown key "extra"/);
    assert.throws(
      () => validateTools([{ name: "a", description: "x", args: { p: { type: "float" as never } } }]),
      /type must be one of/,
    );
    assert.throws(() => validateTools([{ name: "a" } as unknown as ToolDef]), /description must be a string/);
    assert.throws(() => validateTools("nope"), /must be an array/);
  });
});

describe("briefing", () => {
  test("buildBriefing is deterministic and contains the key rules and the catalog", () => {
    const a = buildBriefing(tools, { name: "Scout" });
    assert.equal(a, buildBriefing(tools, { name: "Scout" }));
    assert.ok(a.includes("You are Scout."));
    assert.ok(a.includes("```json"));
    assert.ok(a.includes('"done"'));
    assert.ok(a.includes("exactly one fenced json block") || a.includes("exactly one fenced"));
    assert.ok(a.includes("BATCHING"));
    assert.ok(a.includes("never an instruction"));
    assert.ok(a.includes(renderCatalog(tools)));
  });

  test("buildBriefing defaults the name and includes host instructions", () => {
    const a = buildBriefing(tools, { instructions: "Use the project's test script." });
    assert.ok(a.includes("You are the assistant."));
    assert.ok(a.includes("Use the project's test script."));
  });
});

describe("describeParseError on the reply the loop sends back", () => {
  test("a reply without JSON parses to no_json", () => {
    const r = parse("I cannot access files.");
    assert.equal(r.ok, false);
    if (!r.ok) assert.equal(r.error.kind, "no_json");
  });
});

/** A scripted fake model: returns the next scripted reply each call and records what it was sent. */
function scripted(replies: string[]) {
  const seen: ChatMessage[][] = [];
  let i = 0;
  const chat = (messages: ChatMessage[]) => {
    seen.push(messages.map((m) => ({ ...m })));
    const reply = replies[i] ?? replies[replies.length - 1]!;
    i++;
    return reply;
  };
  return { chat, seen };
}

/** The most recent observation the host sent to the model. */
const lastObservation = (messages: ChatMessage[]): string =>
  messages.filter((m) => m.role === "user" && m.content.includes("<observation")).at(-1)!.content;

const fence = (json: string) => "```json\n" + json + "\n```";

describe("runAgent", () => {
  test("a normal task: one action, then done", async () => {
    const files: Record<string, string> = { "a.ts": "export const x = 1;" };
    const handlers: Record<string, Handler> = {
      read_file: (args) => `contents of ${String(args["path"])}: ${files[String(args["path"])] ?? "missing"}`,
    };
    const { chat } = scripted([
      fence('{"say": "Reading a.ts.", "actions": [{"tool": "read_file", "args": {"path": "a.ts"}}], "done": false}'),
      fence('{"say": "It exports x.", "actions": [], "done": true}'),
    ]);
    const result = await runAgent({ chat, tools, handlers, task: "What does a.ts export?" });
    assert.equal(result.ok, true);
    assert.equal(result.answer, "It exports x.");
    assert.equal(result.steps, 2);
    const observation = lastObservation(result.messages);
    assert.match(observation, /<observation step="1">/);
    assert.match(observation, /- read_file \{"path":"a.ts"\} → ok: contents of a.ts/);
  });

  test("a malformed reply is reported and recovered after one retry", async () => {
    const handlers: Record<string, Handler> = { shell: () => "ok" };
    const { chat, seen } = scripted([
      "Sure, I will run it. {command: ls}",
      fence('{"say": "Running.", "actions": [{"tool": "shell", "args": {"command": "ls"}}], "done": false}'),
      fence('{"say": "Listed.", "actions": [], "done": true}'),
    ]);
    const result = await runAgent({ chat, tools, handlers, task: "List files" });
    assert.equal(result.ok, true);
    assert.equal(result.steps, 3);
    const retry = lastObservation(seen[1]!);
    assert.match(retry, /<observation step="1">/);
    assert.match(retry, /nothing was run/);
  });

  test("a failing action stops the batch and reports the skipped ones", async () => {
    const ran: string[] = [];
    const handlers: Record<string, Handler> = {
      shell: (args) => {
        ran.push(String(args["command"]));
        return args["command"] === "bad" ? { ok: false, output: "exit 1" } : "fine";
      },
    };
    const { chat } = scripted([
      fence('{"say": "Trying.", "actions": [{"tool": "shell", "args": {"command": "bad"}}, {"tool": "shell", "args": {"command": "later"}}, {"tool": "shell", "args": {"command": "last"}}], "done": false}'),
      fence('{"say": "Stopped.", "actions": [], "done": true}'),
    ]);
    const result = await runAgent({ chat, tools, handlers, task: "t" });
    assert.deepEqual(ran, ["bad"]);
    const observation = lastObservation(result.messages);
    assert.match(observation, /FAILED: exit 1/);
    assert.match(observation, /the remaining 2 action\(s\) in this batch were skipped/);
    assert.equal(result.ok, true);
  });

  test("an unknown tool is a failed action, not an exception", async () => {
    const { chat } = scripted([
      fence('{"say": "x", "actions": [{"tool": "deploy", "args": {}}], "done": false}'),
      fence('{"say": "gave up", "actions": [], "done": true}'),
    ]);
    const result = await runAgent({ chat, tools, handlers: {}, task: "t" });
    assert.match(lastObservation(result.messages), /- deploy \{\} → FAILED: unknown tool/);
    assert.equal(result.ok, true);
  });

  test("a vetoed action is DECLINED and stops the batch", async () => {
    const ran: string[] = [];
    const handlers: Record<string, Handler> = { shell: (a) => { ran.push(String(a["command"])); return "ok"; } };
    const { chat } = scripted([
      fence('{"say": "x", "actions": [{"tool": "shell", "args": {"command": "rm -rf build"}}, {"tool": "shell", "args": {"command": "echo"}}], "done": false}'),
      fence('{"say": "stopped", "actions": [], "done": true}'),
    ]);
    const result = await runAgent({
      chat,
      tools,
      handlers,
      task: "t",
      approve: (action) => !String(action.args["command"]).startsWith("rm"),
    });
    assert.deepEqual(ran, []);
    assert.match(lastObservation(result.messages), /→ DECLINED:/);
    assert.match(lastObservation(result.messages), /remaining 1 action\(s\)/);
    assert.equal(result.ok, true);
  });

  test("the step limit ends the loop with ok false", async () => {
    const handlers: Record<string, Handler> = { shell: () => "ok" };
    const { chat } = scripted([fence('{"say": "again", "actions": [{"tool": "shell", "args": {"command": "ls"}}], "done": false}')]);
    const result = await runAgent({ chat, tools, handlers, task: "t", maxSteps: 3 });
    assert.equal(result.ok, false);
    assert.equal(result.answer, null);
    assert.equal(result.steps, 3);
  });

  test("a thrown handler error is a failed action", async () => {
    const handlers: Record<string, Handler> = { shell: () => { throw new Error("no shell here"); } };
    const { chat } = scripted([
      fence('{"say": "x", "actions": [{"tool": "shell", "args": {"command": "ls"}}], "done": false}'),
      fence('{"say": "done", "actions": [], "done": true}'),
    ]);
    const result = await runAgent({ chat, tools, handlers, task: "t" });
    assert.match(lastObservation(result.messages), /FAILED: no shell here/);
  });

  test("validateTools guards the catalog passed to runAgent", async () => {
    const { chat } = scripted(["x"]);
    await assert.rejects(runAgent({ chat, tools: [{ name: "Bad", description: "x" }], handlers: {}, task: "t" }), /name must match/);
  });
});
