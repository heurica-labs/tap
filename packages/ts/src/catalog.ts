// Tool catalog: validation against schema/tools.schema.json and the compact text rendering (SPEC 8).

import type { ToolArg, ToolDef } from "./types.ts";

const NAME_PATTERN = /^[a-z][a-z0-9_]*$/;
const ARG_TYPES = ["string", "integer", "number", "boolean", "array", "object"];
const TOOL_KEYS = new Set(["name", "description", "args", "readonly", "aliases"]);
const ARG_KEYS = new Set(["type", "required", "description"]);

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * Checks a tool catalog against schema/tools.schema.json. Throws an Error that names the first problem found.
 */
export function validateTools(tools: unknown): asserts tools is readonly ToolDef[] {
  if (!Array.isArray(tools)) throw new Error("tools must be an array");
  const seen = new Set<string>();
  tools.forEach((tool: unknown, i) => {
    const where = `tools[${i}]`;
    if (!isPlainObject(tool)) throw new Error(`${where} must be an object`);
    for (const key of Object.keys(tool)) {
      if (!TOOL_KEYS.has(key)) throw new Error(`${where} has an unknown key "${key}"`);
    }
    const name = tool["name"];
    if (typeof name !== "string" || !NAME_PATTERN.test(name)) {
      throw new Error(`${where}.name must match ${NAME_PATTERN.source} (got ${JSON.stringify(name)})`);
    }
    if (seen.has(name)) throw new Error(`${where}.name "${name}" is defined twice`);
    seen.add(name);
    const at = `tool "${name}"`;
    if (typeof tool["description"] !== "string") throw new Error(`${at}: description must be a string`);
    if (tool["readonly"] !== undefined && typeof tool["readonly"] !== "boolean") {
      throw new Error(`${at}: readonly must be a boolean`);
    }
    if (tool["aliases"] !== undefined) {
      const aliases = tool["aliases"];
      if (!Array.isArray(aliases) || aliases.some((a) => typeof a !== "string")) {
        throw new Error(`${at}: aliases must be an array of strings`);
      }
    }
    if (tool["args"] !== undefined) {
      if (!isPlainObject(tool["args"])) throw new Error(`${at}: args must be an object`);
      for (const [argName, arg] of Object.entries(tool["args"])) {
        const argAt = `${at}, argument "${argName}"`;
        if (!isPlainObject(arg)) throw new Error(`${argAt} must be an object`);
        for (const key of Object.keys(arg)) {
          if (!ARG_KEYS.has(key)) throw new Error(`${argAt} has an unknown key "${key}"`);
        }
        if (arg["type"] !== undefined && !ARG_TYPES.includes(arg["type"] as string)) {
          throw new Error(`${argAt}: type must be one of ${ARG_TYPES.join(", ")}`);
        }
        if (arg["required"] !== undefined && typeof arg["required"] !== "boolean") {
          throw new Error(`${argAt}: required must be a boolean`);
        }
        if (arg["description"] !== undefined && typeof arg["description"] !== "string") {
          throw new Error(`${argAt}: description must be a string`);
        }
      }
    }
  });
}

/** One line per tool, in the order given: `[~]name(required, optional?) - description`. */
export function renderCatalog(tools: readonly ToolDef[]): string {
  return tools.map(renderTool).join("\n");
}

function renderTool(tool: ToolDef): string {
  const args = Object.entries(tool.args ?? {}) as [string, ToolArg][];
  const list = args.map(([name, arg]) => (arg.required ? name : `${name}?`)).join(", ");
  const marker = tool.readonly ? "~" : "";
  const description = tool.description.replace(/\r\n|\r|\n/g, " ");
  return `${marker}${tool.name}(${list}) - ${description}`;
}
