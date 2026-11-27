// Observations: what the host sends back to the model after running (or refusing) its actions (SPEC 5.1, 7).

import type { ParseErrorInfo, ResultStatus } from "./types.ts";

export interface FormatResultOptions {
  /** Collapse newlines in the output to single spaces. Default false. */
  oneLine?: boolean;
  /** Output longer than this (in code points) is truncated with a note. Default 4000. */
  maxChars?: number;
}

/**
 * One result line: `- <tool> <argsShort> → <status>: <output>`.
 * Output beyond `maxChars` is cut and followed by `… (N more characters)`, where N counts code points.
 */
export function formatResultLine(
  tool: string,
  argsShort: string,
  status: ResultStatus,
  output: string,
  options: FormatResultOptions = {},
): string {
  const maxChars = options.maxChars ?? 4000;
  let text = options.oneLine ? output.replace(/\s*(?:\r\n|\r|\n)\s*/g, " ").trim() : output;
  const chars = Array.from(text);
  if (chars.length > maxChars) {
    text = `${chars.slice(0, maxChars).join("")}… (${chars.length - maxChars} more characters)`;
  }
  const head = [tool, argsShort].filter((part) => part !== "").join(" ");
  return `- ${head} → ${status}: ${text}`;
}

export interface FormatObservationOptions {
  /** Actions in the batch that did not run because an earlier one failed or was declined. */
  skipped?: number;
  /** Further JSON blocks in the reply that were ignored. */
  ignoredBlocks?: number;
}

/**
 * The observation envelope (SPEC 5.1). Result lines are passed in already formatted.
 */
export function formatObservation(
  step: number,
  resultLines: readonly string[],
  options: FormatObservationOptions = {},
): string {
  const skipped = options.skipped ?? 0;
  const ignoredBlocks = options.ignoredBlocks ?? 0;
  const lines = [`<observation step="${step}">`, "results of your actions:", ...resultLines];
  if (skipped > 0) lines.push(`(the remaining ${skipped} action(s) in this batch were skipped)`);
  if (ignoredBlocks > 0) {
    lines.push(
      `(this reply had ${ignoredBlocks} more JSON block(s); only the first one was run. Send one block per reply.)`,
    );
  }
  lines.push("</observation>");
  return lines.join("\n");
}

const REPLY_FORMAT = [
  "Reply in this format: one short sentence of reasoning, then exactly one fenced json block:",
  "```json",
  '{"say": "what to tell the user", "actions": [{"tool": "<tool name>", "args": {...}}], "done": false}',
  "```",
  "Use an empty actions list when you need no action. Set done to true, with no actions, when the task is complete.",
].join("\n");

/**
 * An observation-ready explanation of a failed parse (SPEC 7). It never runs anything and never suggests running
 * anything.
 */
export function describeParseError(error: ParseErrorInfo): string {
  if (error.kind === "no_json") {
    return ["No JSON block was found in your reply, so nothing was run.", REPLY_FORMAT].join("\n");
  }
  const detail = error.message ? `\nDiagnosis: ${error.message}` : "";
  return [
    `The JSON block in your reply is not valid JSON, so nothing was run.${detail}`,
    "Send the reply again with a corrected json block.",
    REPLY_FORMAT,
  ].join("\n");
}
