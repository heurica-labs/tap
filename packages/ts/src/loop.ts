// A small agent loop that shows how the pieces fit (API.md "Agent loop"). It runs actions only through the
// handlers the caller supplies, and reports results as observations.

import { buildBriefing } from "./briefing.ts";
import { validateTools } from "./catalog.ts";
import { describeParseError, formatObservation, formatResultLine } from "./observation.ts";
import { parse } from "./parse.ts";
import type { Action, ChatMessage, JSONValue, RunOptions, RunResult, ResultStatus } from "./types.ts";

/** Stop sequences for the model (SPEC 5.2). */
export const AGENT_STOPS: readonly string[] = ["<observation", "**Observation", "\nObservation:", "</observation>"];

const DEFAULT_MAX_STEPS = 20;

/**
 * Runs the loop: ask the model, parse its reply, run the actions in order (stopping at the first failure), send the
 * observation, and repeat until a reply is done or maxSteps is reached. Never throws for model or handler errors.
 */
export async function runAgent(options: RunOptions): Promise<RunResult> {
  validateTools(options.tools);
  const maxSteps = options.maxSteps ?? DEFAULT_MAX_STEPS;
  const messages: ChatMessage[] = [
    {
      role: "system",
      content: buildBriefing(options.tools, { instructions: options.instructions, name: options.name }),
    },
    { role: "user", content: options.task },
  ];

  for (let step = 1; step <= maxSteps; step++) {
    const text = await options.chat(messages, { stop: AGENT_STOPS });
    messages.push({ role: "assistant", content: text });

    const parsed = parse(text);
    if (!parsed.ok) {
      messages.push({
        role: "user",
        content: `<observation step="${step}">\n${describeParseError(parsed.error)}\n</observation>`,
      });
      continue;
    }

    const reply = parsed.reply;
    if (reply.actions.length === 0 && reply.done) {
      return { ok: true, answer: reply.say ?? "", steps: step, messages };
    }

    const lines: string[] = [];
    let skipped = 0;
    let stopped = false;
    for (let i = 0; i < reply.actions.length; i++) {
      const action = reply.actions[i]!;
      const [status, output] = await runOne(action, options);
      lines.push(formatResultLine(action.tool, shortArgs(action.args), status, output));
      if (status !== "ok") {
        skipped = reply.actions.length - i - 1;
        stopped = true;
        break;
      }
    }

    if (!stopped && reply.done) {
      return { ok: true, answer: reply.say ?? "", steps: step, messages };
    }
    messages.push({
      role: "user",
      content: formatObservation(step, lines, { skipped, ignoredBlocks: reply.ignoredBlocks }),
    });
  }

  return { ok: false, answer: null, steps: maxSteps, messages };
}

async function runOne(action: Action, options: RunOptions): Promise<[ResultStatus, string]> {
  if (options.approve) {
    const approved = await options.approve(action);
    if (!approved) return ["DECLINED", "the host did not approve this action"];
  }
  if (!Object.hasOwn(options.handlers, action.tool)) return ["FAILED", "unknown tool"];
  try {
    const result = await options.handlers[action.tool]!(action.args);
    if (typeof result === "string") return ["ok", result];
    return result.ok ? ["ok", result.output] : ["FAILED", result.output];
  } catch (error) {
    return ["FAILED", error instanceof Error ? error.message : String(error)];
  }
}

function shortArgs(args: { [key: string]: JSONValue }): string {
  const text = JSON.stringify(args);
  const chars = Array.from(text);
  return chars.length > 120 ? `${chars.slice(0, 117).join("")}...` : text;
}
