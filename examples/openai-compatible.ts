// A minimal TAP agent for any OpenAI-compatible chat completions endpoint.
//
// Env: TAP_BASE_URL (e.g. https://api.openai.com/v1), TAP_API_KEY, TAP_MODEL.
// Run (after building the package): npx tsx examples/openai-compatible.ts "task in plain words"
// It has two tools: read_file, and shell (asks on stdin before each command unless TAP_YES=1).

import { readFile } from "node:fs/promises";
import { exec } from "node:child_process";
import { createInterface } from "node:readline/promises";
import { runAgent, type ChatMessage, type ToolDef } from "@heurica/tap";

const baseUrl = requiredEnv("TAP_BASE_URL").replace(/\/+$/, "");
const apiKey = requiredEnv("TAP_API_KEY");
const model = requiredEnv("TAP_MODEL");
const task = process.argv.slice(2).join(" ").trim();
if (task === "") {
  console.error('usage: TAP_BASE_URL=... TAP_API_KEY=... TAP_MODEL=... tsx openai-compatible.ts "task"');
  process.exit(1);
}

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    console.error(`missing environment variable ${name}`);
    process.exit(1);
  }
  return value;
}

const tools: ToolDef[] = [
  {
    name: "read_file",
    description: "Read a text file in the project. Returns its contents.",
    args: { path: { type: "string", required: true, description: "File path, relative to the project" } },
    readonly: true,
  },
  {
    name: "shell",
    description: "Run a shell command in the project folder. Returns its output.",
    args: { command: { type: "string", required: true, description: "The command line to run" } },
  },
];

const stdin = createInterface({ input: process.stdin, output: process.stdout });

/** Asks the user on stdin before a command runs. TAP_YES=1 skips the question. */
async function confirm(question: string): Promise<boolean> {
  if (process.env["TAP_YES"] === "1") return true;
  const answer = await stdin.question(`${question} [y/N] `);
  return answer.trim().toLowerCase() === "y";
}

/** Calls the chat completions endpoint and returns the text of the first choice. */
async function chat(messages: ChatMessage[], options: { stop: readonly string[] }): Promise<string> {
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model,
      messages,
      stop: [...options.stop],
      temperature: 0,
    }),
  });
  if (!response.ok) throw new Error(`chat request failed: ${response.status} ${await response.text()}`);
  const body = (await response.json()) as { choices?: { message?: { content?: string | null } }[] };
  return body.choices?.[0]?.message?.content ?? "";
}

const result = await runAgent({
  chat,
  tools,
  task,
  name: "a careful coding assistant",
  maxSteps: 15,
  handlers: {
    read_file: async (args) => readFile(String(args["path"]), "utf8"),
    shell: async (args) => {
      const command = String(args["command"]);
      if (!(await confirm(`Run: ${command}?`))) return { ok: false, output: "the user declined this command" };
      return new Promise((resolve) => {
        exec(command, { cwd: process.cwd(), timeout: 60_000, maxBuffer: 1 << 20 }, (error, stdout, stderr) => {
          const output = `${stdout}${stderr}`.trim() || "(no output)";
          resolve(error ? { ok: false, output: `${error.message}\n${output}` } : output);
        });
      });
    },
  },
  approve: async (action) => action.tool !== "shell" || (await confirm(`Allow shell: ${JSON.stringify(action.args)}?`)),
});

console.log(result.ok ? `\n${result.answer}` : "\nThe agent stopped before finishing.");
stdin.close();
