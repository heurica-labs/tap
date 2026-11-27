/** A JSON value, as produced by parsing a model reply. */
export type JSONValue = null | boolean | number | string | JSONValue[] | { [key: string]: JSONValue };

/** One action from a reply: a tool name and its arguments (always a JSON object). */
export interface Action {
  tool: string;
  args: { [key: string]: JSONValue };
}

/** A parsed reply (SPEC 6.8). */
export interface Reply {
  /** Text before the JSON block. */
  thought: string;
  say: string | null;
  actions: Action[];
  done: boolean;
  /** True when the reply stated done (a `done` or `status` key, or a completion action). */
  explicitDone: boolean;
  plan: string[];
  /** 1-based milestone just finished, or null. */
  milestone: number | null;
  /** Further JSON blocks that were ignored. */
  ignoredBlocks: number;
}

export type ParseErrorKind = "no_json" | "invalid_json";

export interface ParseErrorInfo {
  kind: ParseErrorKind;
  /** Diagnosis for invalid_json (may be empty). Empty for no_json. */
  message: string;
}

export type ParseResult = { ok: true; reply: Reply } | { ok: false; error: ParseErrorInfo };

export type ToolArgType = "string" | "integer" | "number" | "boolean" | "array" | "object";

/** An argument of a tool in the catalog (schema/tools.schema.json, `$defs.arg`). */
export interface ToolArg {
  type?: ToolArgType;
  required?: boolean;
  description?: string;
}

/** A tool in the catalog (schema/tools.schema.json, `$defs.tool`). */
export interface ToolDef {
  name: string;
  description: string;
  args?: { [argName: string]: ToolArg };
  readonly?: boolean;
  aliases?: string[];
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatOptions {
  /** Stop sequences (AGENT_STOPS). */
  stop: readonly string[];
}

/** The caller's model call. Returns the model's raw reply text. */
export type ChatFn = (messages: ChatMessage[], options: ChatOptions) => string | Promise<string>;

export type HandlerResult = string | { ok: boolean; output: string };

/** Runs one tool. A string is a successful result. */
export type Handler = (args: { [key: string]: JSONValue }) => HandlerResult | Promise<HandlerResult>;

export type ResultStatus = "ok" | "FAILED" | "DECLINED";

export interface RunOptions {
  chat: ChatFn;
  tools: readonly ToolDef[];
  handlers: { readonly [toolName: string]: Handler };
  task: string;
  /** Default 20. */
  maxSteps?: number;
  /** Extra instructions placed in the briefing. */
  instructions?: string;
  /** How the assistant is named in the briefing. Default "the assistant". */
  name?: string;
  /** Host veto. Returning false reports the action as DECLINED and stops the batch. */
  approve?: (action: Action) => boolean | Promise<boolean>;
}

export interface RunResult {
  ok: boolean;
  /** The final answer (`say` of the done reply), or null when maxSteps ran out. */
  answer: string | null;
  steps: number;
  messages: ChatMessage[];
}
