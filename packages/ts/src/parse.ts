// Port of Anvil's ActionParser.swift and JSON.swift (tools/oracle), with the spec fixes listed in
// conformance/QUIRKS.md "Resolutions". Scanners iterate by code point (Array.from / for-of), the
// closest JS equivalent of Swift's Character iteration. A CRLF pair is escaped as \r\n inside strings.

import { normalizeToolName } from "./aliases.ts";
import type { Action, JSONValue, ParseErrorInfo, ParseResult, Reply } from "./types.ts";

type Obj = { [key: string]: JSONValue };
type Parsed = { v: JSONValue } | null;

const NAME_KEYS = ["tool", "action", "name", "type", "function", "cmd", "command_name"];
const ARG_KEYS = ["args", "arguments", "params", "parameters", "input", "inputs"];
const META_KEYS = new Set([
  "say", "thought", "thoughts", "reason", "reasoning", "risk", "why", "done", "status", "plan", "milestone",
]);
const COMPLETION_NAMES = new Set(["done", "finish", "final_answer", "answer", "complete", "attempt_completion"]);
const REPLY_KEYS = ["say", "actions", "done", "plan", "action", "tool", "steps", "tool_calls", "milestone", "message", "answer"];
const POINTERS = [
  "answered below", "see below", "below", "as follows", "here you go", "here it is", "response below",
  "answer below", "details below", "here's the answer", "here is the answer",
];
const PYTHON_LITERALS: Readonly<Record<string, string>> = { True: "true", False: "false", None: "null" };

const FENCE = /```(?:json|JSON|javascript)?[ \t]*\n?([\s\S]*?)```/g;

const SEGMENTER = new Intl.Segmenter(undefined, { granularity: "grapheme" });

/** Swift String.count: the number of extended grapheme clusters. */
function characterCount(s: string): number {
  let n = 0;
  for (const _ of SEGMENTER.segment(s)) n++;
  return n;
}

/** Swift trimmingCharacters(in: .whitespacesAndNewlines) and (in: .whitespaces). Written as escapes. */
const NL_CLASS = "\\t\\n\\v\\f\\r \\u0085\\u00A0\\u1680\\u2000-\\u200A\\u2028\\u2029\\u202F\\u205F\\u3000";
const SP_CLASS = "\\t \\u00A0\\u1680\\u2000-\\u200A\\u202F\\u205F\\u3000";
const WS_AND_NEWLINES = new RegExp(`^[${NL_CLASS}]+|[${NL_CLASS}]+$`, "g");
const WS_ONLY = new RegExp(`^[${SP_CLASS}]+|[${SP_CLASS}]+$`, "g");

function trimAll(s: string): string {
  return s.replace(WS_AND_NEWLINES, "");
}

function trimSpaces(s: string): string {
  return s.replace(WS_ONLY, "");
}

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** The value under `key` if the key is present (null counts as present), else undefined. */
function field(o: Obj, key: string): JSONValue | undefined {
  return Object.hasOwn(o, key) ? o[key] : undefined;
}

/** The first present key's value, or undefined. Mirrors Swift `a ?? b ?? c` over JSON subscripts. */
function firstPresent(o: Obj, keys: readonly string[]): JSONValue | undefined {
  for (const k of keys) {
    const v = field(o, k);
    if (v !== undefined) return v;
  }
  return undefined;
}

// ---- JSON value coercions (JSON.swift) -------------------------------------------------------

/** Swift Double.description for a value that does not print as a plain integer. */
function swiftDouble(n: number): string {
  if (Number.isNaN(n)) return "nan";
  if (n === Infinity) return "inf";
  if (n === -Infinity) return "-inf";
  const a = Math.abs(n);
  if (a !== 0 && (a < 1e-4 || a >= 2 ** 53)) {
    const m = /^(-?[\d.]+)e([+-])(\d+)$/.exec(n.toExponential());
    if (!m) return n.toExponential();
    return `${m[1]}e${m[2]}${m[3]!.padStart(2, "0")}`;
  }
  const s = String(n);
  return s.includes(".") ? s : `${s}.0`;
}

/** JSON.swift `.string` on a number: integers below 1e15 print as integers. */
function numberToString(n: number): string {
  if (Number.isInteger(n) && Math.abs(n) < 1e15) return String(n === 0 ? 0 : n);
  return swiftDouble(n);
}

/** `.string`: strings, numbers and booleans have text; everything else is nil. */
function asString(v: JSONValue | undefined): string | null {
  if (typeof v === "string") return v;
  if (typeof v === "number") return numberToString(v);
  if (typeof v === "boolean") return v ? "true" : "false";
  return null;
}

/** Swift Double(String) for the forms a model might send. Anything else is nil. */
function parseSwiftDouble(text: string): number | null {
  const t = trimSpaces(text);
  if (/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(t)) return Number(t);
  if (/^[+-]?(?:inf|infinity)$/i.test(t)) return t.startsWith("-") ? -Infinity : Infinity;
  if (/^[+-]?nan$/i.test(t)) return NaN;
  const hex = /^([+-]?)0x([0-9a-f]+)$/i.exec(t);
  if (hex) {
    const v = parseInt(hex[2]!, 16);
    return hex[1] === "-" ? -v : v;
  }
  return null;
}

/** `.double` */
function asDouble(v: JSONValue | undefined): number | null {
  if (typeof v === "number") return v;
  if (typeof v === "string") return parseSwiftDouble(v);
  if (typeof v === "boolean") return v ? 1 : 0;
  return null;
}

/** Swift Double.rounded() rounds half away from zero. */
function roundHalfAway(x: number): number {
  return Math.sign(x) * Math.round(Math.abs(x));
}

/** `.int` */
function asInt(v: JSONValue | undefined): number | null {
  const d = asDouble(v);
  if (d === null || !Number.isFinite(d)) return null;
  return roundHalfAway(d);
}

/** `.bool` */
function asBool(v: JSONValue | undefined): boolean | null {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v !== 0;
  if (typeof v === "string") return ["true", "yes", "1"].includes(v.toLowerCase());
  return null;
}

/** `.object`, or undefined when the value is not an object. */
function asObj(v: JSONValue | undefined): Obj | undefined {
  return isObj(v) ? v : undefined;
}

// ---- lenient JSON (JSON.swift parse, ActionParser.parseLenient) ------------------------------

function strictParse(text: string): Parsed {
  try {
    return { v: JSON.parse(text) as JSONValue };
  } catch {
    return null;
  }
}

/** JSON.parse first, then the string-aware repairs, each tried in turn (ActionParser.parseLenient). */
function parseLenient(s: string, repair = true): Parsed {
  const direct = strictParse(s);
  if (direct) return direct;
  const t = normalizeJSON(s);
  const normalized = strictParse(t);
  if (normalized) return normalized;
  const balanced = strictParse(balancedPrefix(t));
  if (balanced) return balanced;
  if (repair) {
    const structural = strictParse(repairStructure(t));
    if (structural) return structural;
  }
  return null;
}

/**
 * Outside strings: smart quotes become quotes, trailing commas and // comments go, Python literals become JSON.
 * Inside strings: raw newlines, carriage returns and tabs are escaped. String contents are otherwise untouched.
 */
export function normalizeJSON(s: string): string {
  const chars = Array.from(s);
  const out: string[] = [];
  let i = 0;
  let inString = false;
  let escaped = false;
  let smart = false;
  while (i < chars.length) {
    const c = chars[i]!;
    if (inString) {
      if (escaped) {
        escaped = false;
        out.push(c);
      } else if (c === "\\") {
        escaped = true;
        out.push(c);
      } else if ((!smart && c === '"') || (smart && c === "”")) {
        inString = false;
        out.push('"');
      } else if (smart && c === '"') {
        out.push('\\"');
      } else if (c === "\n") {
        out.push("\\n");
      } else if (c === "\r") {
        out.push("\\r");
      } else if (c === "\t") {
        out.push("\\t");
      } else {
        out.push(c);
      }
      i++;
      continue;
    }
    switch (c) {
      case '"':
        inString = true;
        smart = false;
        out.push(c);
        break;
      case "“":
      case "”":
        inString = true;
        smart = true;
        out.push('"');
        break;
      case ",": {
        // Trailing comma: the next non-space character closes the container.
        let k = i + 1;
        while (k < chars.length && /\p{White_Space}/u.test(chars[k]!)) k++;
        if (k < chars.length && (chars[k] === "}" || chars[k] === "]")) {
          i++;
          continue;
        }
        out.push(c);
        break;
      }
      case "/":
        if (i + 1 < chars.length && chars[i + 1] === "/") {
          while (i < chars.length && chars[i] !== "\n") i++;
          continue;
        }
        out.push(c);
        break;
      default: {
        if (/\p{L}/u.test(c) && (i === 0 || !isWordChar(chars[i - 1]!))) {
          let k = i;
          while (k < chars.length && isWordChar(chars[k]!)) k++;
          const word = chars.slice(i, k).join("");
          out.push(Object.hasOwn(PYTHON_LITERALS, word) ? PYTHON_LITERALS[word]! : word);
          i = k;
          continue;
        }
        out.push(c);
      }
    }
    i++;
  }
  return out.join("");
}

function isWordChar(c: string): boolean {
  return /\p{L}|\p{N}/u.test(c) || c === "_";
}

/** The first balanced {...} or [...] at the start of `s` (string-aware). */
function balancedPrefix(s: string): string {
  let depth = 0;
  let inString = false;
  let escaped = false;
  let out = "";
  for (const c of s) {
    out += c;
    if (inString) {
      if (escaped) escaped = false;
      else if (c === "\\") escaped = true;
      else if (c === '"') inString = false;
      continue;
    }
    if (c === '"') {
      inString = true;
    } else if (c === "{" || c === "[") {
      depth++;
    } else if (c === "}" || c === "]") {
      depth--;
      if (depth === 0) return out;
    }
  }
  return s;
}

/**
 * Fixes structural slips: a "{" where an object key is expected means the previous object was never closed,
 * a closer of the wrong kind means one is missing, and unclosed containers at the end are closed.
 */
function repairStructure(s: string): string {
  const out: string[] = [];
  const stack: string[] = [];
  let expectKey = false;
  let inString = false;
  let escaped = false;
  for (const c of s) {
    if (inString) {
      out.push(c);
      if (escaped) escaped = false;
      else if (c === "\\") escaped = true;
      else if (c === '"') inString = false;
      continue;
    }
    switch (c) {
      case '"':
        inString = true;
        if (stack.at(-1) === "{" && expectKey) expectKey = false;
        out.push(c);
        break;
      case "{": {
        if (stack.at(-1) === "{" && expectKey) {
          // `{"tool": "a", "args": {...}, {"tool": "b"...`: close the first object before the comma.
          const comma = out.lastIndexOf(",");
          if (comma >= 0) {
            out.splice(comma, 0, "}");
            stack.pop();
          }
        }
        stack.push("{");
        expectKey = true;
        out.push(c);
        break;
      }
      case "[":
        stack.push("[");
        expectKey = false;
        out.push(c);
        break;
      case "}":
        while (stack.at(-1) === "[") {
          out.push("]");
          stack.pop();
        }
        if (stack.length > 0) stack.pop();
        expectKey = false;
        out.push(c);
        break;
      case "]":
        while (stack.at(-1) === "{") {
          out.push("}");
          stack.pop();
        }
        if (stack.length > 0) stack.pop();
        expectKey = false;
        out.push(c);
        break;
      case ",":
        expectKey = stack.at(-1) === "{";
        out.push(c);
        break;
      case ":":
        expectKey = false;
        out.push(c);
        break;
      default:
        out.push(c);
    }
  }
  if (inString) out.push('"');
  for (const open of [...stack].reverse()) out.push(open === "{" ? "}" : "]");
  return out.join("");
}

/** Where the JSON broke, for the retry message. Returns "" when the text is valid. */
function diagnose(s: string): string {
  let message: string;
  try {
    JSON.parse(s);
    return "";
  } catch (e) {
    message = e instanceof Error ? e.message : String(e);
  }
  const m = /position (\d+)/.exec(message);
  if (!m) return message;
  const n = Number(m[1]);
  if (n >= s.length) return message;
  const before = Array.from(s.slice(0, n)).slice(-80).join("");
  const after = Array.from(s.slice(n)).slice(0, 40).join("");
  return `${message} Near: …${before}⟦HERE⟧${after}…`;
}

// ---- shape (ActionParser.action / isReply / isPointer) ---------------------------------------

/** A JSON value shaped like a reply (SPEC 6.2). */
function isReply(j: JSONValue): boolean {
  if (Array.isArray(j)) return j.some((x) => actionFrom(x) !== null);
  if (!isObj(j)) return false;
  return REPLY_KEYS.some((k) => Object.hasOwn(j, k));
}

/** An action object: a name key whose value has text, plus its arguments (SPEC 6.4). */
function actionFrom(j: JSONValue): Action | null {
  if (!isObj(j)) return null;
  let nameKey: string | undefined;
  let name = "";
  for (const k of NAME_KEYS) {
    const text = asString(field(j, k));
    if (text !== null) {
      nameKey = k;
      name = text;
      break;
    }
  }
  if (nameKey === undefined) return null;
  let args: JSONValue;
  const argKey = ARG_KEYS.find((k) => Object.hasOwn(j, k));
  if (argKey !== undefined) {
    const a = j[argKey]!;
    const inner = typeof a === "string" ? parseLenient(a) : null;
    args = inner && isObj(inner.v) ? inner.v : a;
  } else {
    const flat: Obj = {};
    for (const k of Object.keys(j)) {
      if (k === nameKey || META_KEYS.has(k)) continue;
      flat[k] = j[k]!;
    }
    args = flat;
  }
  if (!isObj(args)) args = { value: args };
  return { tool: normalizeToolName(name), args: args as Obj };
}

/** A `say` that is empty or just points elsewhere (SPEC 6.6). */
function isPointer(say: string | null): boolean {
  const t = trimAll(say ?? "").toLowerCase();
  if (t === "") return true;
  if (characterCount(t) > 40) return false;
  return POINTERS.some((p) => t.startsWith(p) || t === `${p}.` || t === `${p}:`);
}

// ---- extraction (ActionParser.extractJSON) ---------------------------------------------------

interface Extracted {
  text: string;
  before: string;
  after: string;
  ignoredBlocks: number;
}

/**
 * A fallback candidate is taken when it does not parse (so the error is reported), or when it parses to a
 * reply. Parseable JSON that is not reply-shaped is skipped, so the search goes on (SPEC 6.1).
 */
function usable(text: string): boolean {
  const p = parseLenient(text);
  return p === null || isReply(p.v);
}

function extractJSON(raw: string): Extracted | null {
  const matches = [...raw.matchAll(FENCE)];

  // 1. The first fence whose body is valid JSON and shaped like a reply.
  const valid: { body: string; index: number; length: number }[] = [];
  for (const m of matches) {
    const body = trimAll(m[1] ?? "");
    if (body.startsWith("{") || body.startsWith("[")) {
      const p = parseLenient(body, false);
      if (p !== null && isReply(p.v)) valid.push({ body, index: m.index, length: m[0].length });
    }
  }
  const first = valid[0];
  if (first !== undefined) {
    return {
      text: first.body,
      before: trimAll(raw.slice(0, first.index)),
      after: trimAll(raw.slice(first.index + first.length)),
      ignoredBlocks: valid.length - 1,
    };
  }

  // 2. A "```json" opener to the last closing fence, with nested fences inside (for example Markdown content).
  const opener = raw.includes("```json") ? "```json" : raw.includes("```JSON") ? "```JSON" : null;
  if (opener !== null) {
    const at = raw.indexOf(opener);
    let body = raw.slice(at + opener.length);
    const close = body.lastIndexOf("\n```") >= 0 ? body.lastIndexOf("\n```") : body.lastIndexOf("```");
    if (close >= 0) body = body.slice(0, close);
    body = trimAll(body);
    if ((body.startsWith("{") || body.startsWith("[")) && usable(body)) {
      return { text: body, before: trimAll(raw.slice(0, at)), after: "", ignoredBlocks: 0 };
    }
  }

  // 3. A single fence whose body starts with "{".
  if (matches.length === 1) {
    const m = matches[0]!;
    const body = trimAll(m[1] ?? "");
    if (body.startsWith("{") && usable(body)) {
      return { text: body, before: trimAll(raw.slice(0, m.index)), after: "", ignoredBlocks: 0 };
    }
  }

  // 4. The outermost {...} in the text.
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start >= 0 && end >= 0 && start < end) {
    const text = raw.slice(start, end + 1);
    if (usable(text)) return { text, before: trimAll(raw.slice(0, start)), after: "", ignoredBlocks: 0 };
  }

  // 5. Text from the first "{" to the end (a reply cut off before its closing brace).
  if (start >= 0) {
    const text = raw.slice(start);
    if (usable(text)) return { text, before: trimAll(raw.slice(0, start)), after: "", ignoredBlocks: 0 };
  }
  return null;
}

// ---- public parse ----------------------------------------------------------------------------

function invalid(message: string): ParseResult {
  return { ok: false, error: { kind: "invalid_json", message } };
}

/**
 * Reads a TAP reply (SPEC 6, lenient level). Never throws on model text: any internal failure is reported
 * as invalid_json.
 */
export function parse(raw: string): ParseResult {
  try {
    return parseReply(raw);
  } catch (e) {
    return invalid(e instanceof Error ? e.message : String(e));
  }
}

function parseReply(raw: string): ParseResult {
  const extracted = extractJSON(raw);
  if (extracted === null) return { ok: false, error: { kind: "no_json", message: "" } satisfies ParseErrorInfo };

  const parsed = parseLenient(extracted.text);
  if (parsed === null) return invalid(diagnose(normalizeJSON(extracted.text)));
  const json = parsed.v;

  const reply: Reply = {
    thought: extracted.before,
    say: null,
    actions: [],
    done: false,
    explicitDone: false,
    plan: [],
    milestone: null,
    ignoredBlocks: extracted.ignoredBlocks,
  };
  const obj = asObj(json);
  reply.explicitDone = obj !== undefined && (Object.hasOwn(obj, "done") || Object.hasOwn(obj, "status"));

  if (Array.isArray(json)) {
    reply.actions = compact(json.map(actionFrom));
  } else if (obj !== undefined) {
    reply.say = asString(firstPresent(obj, ["say", "message", "answer", "reply", "response"]));
    const done = asBool(field(obj, "done"));
    if (done !== null) {
      reply.done = done;
    } else {
      const status = asString(field(obj, "status"));
      reply.done = status === null ? false : ["done", "complete", "finished"].includes(status.toLowerCase());
    }
    const planList = Array.isArray(field(obj, "plan"))
      ? (field(obj, "plan") as JSONValue[])
      : Array.isArray(field(obj, "milestones"))
        ? (field(obj, "milestones") as JSONValue[])
        : [];
    reply.plan = compact(
      planList.map((entry) => {
        const text = asString(entry);
        if (text !== null) return text;
        const e = asObj(entry);
        if (e === undefined) return null;
        return asString(field(e, "title")) ?? asString(field(e, "step"));
      }),
    )
      .map((s) => trimAll(s))
      .filter((s) => s !== "");
    reply.milestone = asInt(field(obj, "milestone"));

    const list = firstPresent(obj, ["actions", "steps", "tool_calls"]);
    const single = asObj(field(obj, "action")) ?? asObj(field(obj, "tool"));
    if (list !== undefined) {
      if (Array.isArray(list)) reply.actions = compact(list.map(actionFrom));
    } else if (single !== undefined) {
      const a = actionFrom(single);
      reply.actions = a ? [a] : [];
    } else {
      const a = actionFrom(obj);
      if (a) reply.actions = [a];
    }
  } else {
    return invalid("top level must be an object");
  }

  // A "done" action is a completion signal, not a tool.
  const ci = reply.actions.findIndex((a) => COMPLETION_NAMES.has(a.tool));
  if (ci >= 0) {
    const a = reply.actions[ci]!;
    const msg =
      firstString(a.args, ["message", "answer", "text", "say", "result"]);
    if (msg !== null && msg !== "") reply.say = msg;
    reply.actions = reply.actions.slice(0, ci);
    reply.done = true;
    reply.explicitDone = true;
  }

  const hasDoneKey = obj !== undefined && Object.hasOwn(obj, "done");
  if (reply.actions.length === 0 && reply.say !== null && !hasDoneKey && reply.plan.length === 0) {
    reply.done = true;
  }

  // The model wrote its answer as prose after the JSON block; keep it instead of a pointer.
  if (reply.actions.length === 0 && extracted.after !== "" && characterCount(extracted.after) > 40 && isPointer(reply.say)) {
    reply.say = extracted.after;
    if (!hasDoneKey) reply.done = true;
  }

  return { ok: true, reply };
}

function firstString(o: Obj, keys: readonly string[]): string | null {
  for (const k of keys) {
    const s = asString(field(o, k));
    if (s !== null) return s;
  }
  return null;
}

function compact<T>(xs: readonly (T | null)[]): T[] {
  return xs.filter((x): x is T => x !== null);
}
