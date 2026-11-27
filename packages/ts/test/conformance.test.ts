// Runs every conformance vector (conformance/vectors.json, copied to test/fixtures) against parse().
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parse } from "../src/index.ts";
import type { ParseResult } from "../src/index.ts";

interface Vector {
  id: string;
  description: string;
  section: string;
  input: string;
  result: unknown;
  divergesFromAnvil?: boolean;
  anvilResult?: unknown;
}

const vectors: Vector[] = JSON.parse(
  readFileSync(new URL("./fixtures/vectors.json", import.meta.url), "utf8"),
);

/** Structural equality where key order does not matter and numbers compare by value. */
function same(a: unknown, b: unknown, path = "$"): string | null {
  if (typeof a !== typeof b) return `${path}: type ${typeof a} vs ${typeof b}`;
  if (a === null || b === null || typeof a !== "object") {
    return Object.is(a, b) || a === b ? null : `${path}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`;
  }
  if (Array.isArray(a) !== Array.isArray(b)) return `${path}: array mismatch`;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return `${path}: length ${a.length} vs ${b.length}`;
    for (let i = 0; i < a.length; i++) {
      const d = same(a[i], b[i], `${path}[${i}]`);
      if (d) return d;
    }
    return null;
  }
  const ao = a as Record<string, unknown>;
  const bo = b as Record<string, unknown>;
  const keys = new Set([...Object.keys(ao), ...Object.keys(bo)]);
  for (const k of keys) {
    if (!Object.hasOwn(ao, k) || !Object.hasOwn(bo, k)) return `${path}.${k}: missing on one side`;
    const d = same(ao[k], bo[k], `${path}.${k}`);
    if (d) return d;
  }
  return null;
}

/** Compares a parse result with an expected vector result (SPEC 6.8 shape). Invalid_json compares kind only. */
function compareResult(actual: ParseResult, expected: Record<string, unknown>): string | null {
  const exp = expected as { ok: boolean; reply?: Record<string, unknown>; error?: { kind: string; message?: string } };
  if (actual.ok !== exp.ok) return `ok: ${actual.ok} vs ${exp.ok}`;
  if (!actual.ok) {
    const e = exp.error!;
    if (actual.error.kind !== e.kind) return `error.kind: ${actual.error.kind} vs ${e.kind}`;
    return null;
  }
  const r = actual.reply;
  const want = exp.reply!;
  const got = {
    thought: r.thought,
    say: r.say,
    actions: r.actions,
    done: r.done,
    explicitDone: r.explicitDone,
    plan: r.plan,
    milestone: r.milestone,
    ignoredBlocks: r.ignoredBlocks,
  };
  return same(got, want, "reply");
}

// Vectors marked divergesFromAnvil check the spec result (`result`), not the oracle output (`anvilResult`).
for (const v of vectors) {
  test(`${v.section} ${v.id}`, () => {
    const actual = parse(v.input);
    const diff = compareResult(actual, v.result as Record<string, unknown>);
    assert.equal(diff, null, `${v.id} (${v.description})\ninput: ${JSON.stringify(v.input)}\nactual: ${JSON.stringify(actual)}`);
  });
}

test("vector count is 150 and every id is unique", () => {
  assert.equal(vectors.length, 150);
  assert.equal(new Set(vectors.map((v) => v.id)).size, 150);
});
